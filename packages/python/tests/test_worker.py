"""Owned local threads, real inbox transitions and session cleanup after drain."""

import asyncio
import gc
import json
import sqlite3
import tempfile
import threading
import time
import unittest
import warnings
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from telegram_patterns import InvalidType, UnsupportedCapability, ValidationFailure
from telegram_patterns.inbox import SQLiteInbox
from telegram_patterns.telemetry import Telemetry
from telegram_patterns.webhook import WebhookReceiver
from telegram_patterns.worker import InboxWorker, settled_to_thread


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='worker lifecycle ')
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'project.sqlite'
        self.inbox = SQLiteInbox(self.database)
        self.inbox.initialize()
        self.lines = []
        self.telemetry = Telemetry(b'worker-test-telemetry-key-32-bytes', self.lines.append)

    def receive(self, update_id=1, payload=None):
        return self.inbox.receive(
            100, update_id, payload or {'update_id': update_id, 'message': {'text': 'PRIVATE_CANARY'}}
        )

    def worker(self, handle, decode=lambda payload: payload['message'], **options):
        return InboxWorker(self.inbox, 100, 'worker-1', decode, handle, telemetry=self.telemetry, **options)

    async def test_success_marks_done_only_after_handler_returns_true_and_idle_is_read_only(self):
        self.receive()
        seen = []

        async def handle(decoded, claim):
            self.assertEqual(self.inbox.get(100, 1).state, 'processing')
            seen.append((decoded['text'], claim.update_id))
            with self.telemetry.bind(bot_id=100, action_id='confirm', operation_id='order-7', inherit=True):
                self.telemetry.emit('operation', 'succeeded', duration_ms=2)
            return True

        worker = self.worker(handle)
        self.assertEqual(await worker.run_one(), 'done')
        self.assertEqual(self.inbox.get(100, 1).state, 'done')
        self.assertEqual(await worker.run_one(), 'idle')
        self.assertEqual(seen, [('PRIVATE_CANARY', 1)])
        events = [json.loads(line) for line in self.lines]
        self.assertEqual(events[0]['context']['update_ref'], events[1]['context']['update_ref'])
        self.assertEqual(events[0]['context']['trace_id'], events[1]['context']['trace_id'])
        self.assertNotIn('PRIVATE_CANARY', ''.join(self.lines))
        self.assertIsNone(self.telemetry.current())

    async def test_handler_non_true_and_exceptions_quarantine_original_without_complete(self):
        for identity, answer in enumerate((False, None, 1, ValueError('PRIVATE_CANARY')), 1):
            self.receive(identity)

            async def handle(decoded, claim):
                if isinstance(answer, Exception):
                    raise answer
                return answer

            self.assertEqual(await self.worker(handle).run_one(), 'quarantined')
            record = self.inbox.get(100, identity)
            expected = 'processing-failed' if isinstance(answer, Exception) else 'handler-rejected'
            self.assertEqual((record.state, record.reason), ('quarantined', expected))
            self.assertEqual(record.payload['message']['text'], 'PRIVATE_CANARY')
        self.assertNotIn('PRIVATE_CANARY', ''.join(self.lines))

    async def test_decode_failure_and_unknown_envelope_are_retained_with_fixed_reason(self):
        self.receive(payload={'update_id': 1, 'future_kind': {'secret': 'PRIVATE_CANARY'}})

        def decode(payload):
            raise UnsupportedCapability('PRIVATE_CANARY: unsupported SDK event')

        async def handle(decoded, claim):
            self.fail('Undecodable event handled')

        self.assertEqual(await self.worker(handle, decode).run_one(), 'quarantined')
        record = SQLiteInbox(self.database).get(100, 1)
        self.assertEqual((record.state, record.reason), ('quarantined', 'decode-failed'))
        self.assertIn('future_kind', record.payload)
        receiver = WebhookReceiver(self.inbox, bot_id=100, secret_token='test-secret')
        response = receiver.receive(b'{"update_id":2,"future_kind":{"secret":"PRIVATE_CANARY"}}', 'test-secret')
        self.assertEqual(response.status, 200)
        self.assertEqual(await self.worker(handle, decode).run_one(), 'idle')
        self.assertEqual(self.inbox.get(100, 2).reason, 'unknown-update-kind')

    async def test_decoder_cancellation_is_not_mislabeled_as_decode_failure(self):
        self.receive()

        def decode(payload):
            raise asyncio.CancelledError()

        async def handle(decoded, claim):
            self.fail('Cancelled decode handled')

        with self.assertRaises(asyncio.CancelledError):
            await self.worker(handle, decode).run_one()
        self.assertEqual(self.inbox.get(100, 1).reason, 'processing-failed')

    async def test_wrapped_async_decoder_closes_coroutine_and_quarantines_without_warning(self):
        self.receive()

        async def decode(payload):
            self.fail('Async decode body ran')

        async def handle(decoded, claim):
            self.fail('Invalid decoder reached handler')

        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            self.assertEqual(await self.worker(handle, lambda payload: decode(payload)).run_one(), 'quarantined')
            gc.collect()
        self.assertEqual(observed, [])
        self.assertEqual(self.inbox.get(100, 1).reason, 'decode-failed')

    async def test_stop_event_stops_admission_then_drains_job_before_resource_closure(self):
        self.receive(1)
        self.receive(2)
        started, release, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()
        closed = []

        async def handle(decoded, claim):
            started.set()
            await release.wait()
            self.assertFalse(closed)
            return True

        async def owner():
            try:
                await self.worker(handle).serve(stop)
            finally:
                closed.append('session-closed')

        task = asyncio.create_task(owner())
        await started.wait()
        stop.set()
        self.assertFalse(task.done())
        release.set()
        await asyncio.wait_for(task, 5)
        self.assertEqual(closed, ['session-closed'])
        self.assertEqual((self.inbox.get(100, 1).state, self.inbox.get(100, 2).state), ('done', 'pending'))

    async def test_concurrent_run_one_cannot_claim_a_second_job_and_guard_resets_after_drain(self):
        self.receive(1)
        self.receive(2)
        started, release = asyncio.Event(), asyncio.Event()

        async def handle(decoded, claim):
            started.set()
            await release.wait()
            return True

        worker = self.worker(handle)
        first = asyncio.create_task(worker.run_one())
        try:
            await started.wait()
            with self.assertRaises(ValidationFailure):
                await worker.run_one()
            record = self.inbox.get(100, 2)
            self.assertEqual((record.state, record.attempts), ('pending', 0))
        finally:
            release.set()
            self.assertEqual(await first, 'done')
        self.assertEqual(await worker.run_one(), 'done')

    async def test_cancelled_handler_never_completes_and_resource_owner_closes_after_quarantine(self):
        self.receive()
        started, blocked, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()
        states_when_closed = []

        async def handle(decoded, claim):
            started.set()
            await blocked.wait()
            return True

        async def owner():
            try:
                await self.worker(handle).serve(stop)
            finally:
                states_when_closed.append(self.inbox.get(100, 1).state)

        task = asyncio.create_task(owner())
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(states_when_closed, ['quarantined'])
        self.assertEqual(self.inbox.get(100, 1).reason, 'processing-failed')

    async def test_cancelled_thread_is_joined_even_after_second_cancel_before_owner_closes(self):
        started, release = threading.Event(), threading.Event()
        order = []
        self.addCleanup(release.set)

        def write():
            with closing(sqlite3.connect(self.database)) as connection, connection:
                connection.execute('CREATE TABLE committed(value INTEGER)')
                started.set()
                if not release.wait(5):
                    raise AssertionError('Test did not release writer')
                connection.execute('INSERT INTO committed VALUES(7)')
            order.append('committed')
            return 7

        async def owner():
            try:
                await settled_to_thread(write)
            finally:
                order.append('session-closed')

        task = asyncio.create_task(owner())
        self.assertTrue(await asyncio.to_thread(started.wait, 2))
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        self.assertEqual(order, [])
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        self.assertEqual(order, ['committed', 'session-closed'])
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute('SELECT value FROM committed').fetchone(), (7,))

    async def test_cancellation_while_claim_thread_returns_keeps_durable_unfinished_job(self):
        self.receive()
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original_claim = self.inbox.claim

        def delayed_claim(*args, **kwargs):
            result = original_claim(*args, **kwargs)
            started.set()
            if not release.wait(5):
                raise AssertionError('Test did not release claim')
            return result

        async def handle(decoded, claim):
            self.fail('Cancelled admission ran a handler')

        with patch.object(self.inbox, 'claim', delayed_claim):
            task = asyncio.create_task(self.worker(handle).run_one())
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        record = self.inbox.get(100, 1)
        self.assertEqual(record.state, 'processing')
        claim = self.inbox.claim(100, 'restart', now=record.lease_until + 1)
        self.assertEqual((claim.update_id, claim.attempt), (1, 2))

    async def test_lost_lease_cannot_complete_a_reclaimed_event(self):
        self.receive()

        async def handle(decoded, claim):
            replacement = await settled_to_thread(self.inbox.claim, 100, 'replacement', now=time.time() + 100)
            self.assertEqual(replacement.update_id, claim.update_id)
            return True

        self.assertEqual(await self.worker(handle).run_one(), 'lease-lost')
        self.assertEqual(self.inbox.get(100, 1).state, 'processing')
        event = json.loads(self.lines[-1])
        self.assertEqual((event['outcome'], event['error_outcome']), ('unknown', 'unknown'))

    async def test_local_thread_result_and_exception_and_async_contract(self):
        self.assertEqual(await settled_to_thread(lambda a, *, b: a + b, 2, b=3), 5)

        def failing():
            raise ValueError('fixture')

        with self.assertRaises(ValueError):
            await settled_to_thread(failing)

        async def asynchronous():
            self.fail('Async local thread body executed')

        with self.assertRaises(InvalidType):
            await settled_to_thread(asynchronous)
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            with self.assertRaises(InvalidType):
                await settled_to_thread(lambda: asynchronous())
            gc.collect()
        self.assertEqual(observed, [])

    async def test_cancelled_failed_thread_rolls_back_before_propagating_original_cancel(self):
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def failing_transaction():
            with closing(sqlite3.connect(self.database)) as connection, connection:
                connection.execute('CREATE TABLE failure_test(value INTEGER)')
                connection.execute('INSERT INTO failure_test VALUES(7)')
                started.set()
                if not release.wait(5):
                    raise AssertionError('Writer not released')
                raise ValueError('PRIVATE_CANARY')

        task = asyncio.create_task(settled_to_thread(failing_transaction))
        self.assertTrue(await asyncio.to_thread(started.wait, 2))
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM failure_test').fetchone()[0], 0)

    async def test_idle_worker_waits_for_stop_and_refuses_a_second_serve_owner(self):
        stop, second_claim = asyncio.Event(), asyncio.Event()
        original = self.inbox.claim
        loop = asyncio.get_running_loop()
        calls = 0

        def observed_claim(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls >= 2:
                loop.call_soon_threadsafe(second_claim.set)
            return original(*args, **kwargs)

        async def handle(decoded, claim):
            self.fail('Empty inbox handled a job')

        worker = self.worker(handle, idle_seconds=0.01)
        with patch.object(self.inbox, 'claim', observed_claim):
            task = asyncio.create_task(worker.serve(stop))
            try:
                await asyncio.wait_for(second_claim.wait(), 5)
                with self.assertRaises(ValidationFailure):
                    await worker.serve(stop)
            finally:
                stop.set()
                await asyncio.wait_for(task, 5)
        self.assertGreaterEqual(calls, 2)

    async def test_worker_needs_no_telemetry_and_sync_handler_cannot_complete_a_job(self):
        self.receive(1)
        worker = InboxWorker(self.inbox, 100, 'worker', lambda payload: payload, lambda decoded, claim: True)
        self.assertEqual(await worker.run_one(), 'quarantined')
        self.assertEqual(self.inbox.get(100, 1).reason, 'processing-failed')
        self.receive(2)

        async def handle(decoded, claim):
            return True

        worker = InboxWorker(self.inbox, 100, 'worker', lambda payload: payload, handle)
        self.assertEqual(await worker.run_one(), 'done')

    async def test_invalid_contract_and_pre_set_stop_do_not_claim_or_complete(self):
        self.receive()

        async def handle(decoded, claim):
            self.fail('Stopped worker admitted a job')

        stop = asyncio.Event()
        stop.set()
        await self.worker(handle).serve(stop)
        self.assertEqual(self.inbox.get(100, 1).state, 'pending')
        with self.assertRaises(InvalidType):
            await self.worker(handle).serve(None)
        for changes in (
            {'bot_id': True},
            {'worker_id': ''},
            {'lease_seconds': 0},
            {'idle_seconds': 0},
            {'telemetry': object()},
            {'handle': None},
        ):
            with self.subTest(changes=repr(changes)), self.assertRaises((ValidationFailure, InvalidType)):
                InboxWorker(
                    **{
                        'inbox': self.inbox,
                        'bot_id': 100,
                        'worker_id': 'worker',
                        'decode': lambda payload: payload,
                        'handle': handle,
                        **changes,
                    }
                )


if __name__ == '__main__':
    unittest.main()
