"""Serialized allowlist, context isolation, finite labels and harmless sink failures."""

import asyncio
import gc
import json
import unittest
import warnings
from dataclasses import FrozenInstanceError, asdict

from telegram_patterns import InvalidType, PermissionDenied, ValidationFailure
from telegram_patterns.telemetry import Telemetry

KEY = b'telemetry-test-key-at-least-32-bytes'
CANARY = 'PRIVATE_TOKEN_CANARY'


class TelemetryTests(unittest.IsolatedAsyncioTestCase):
    def test_serialized_events_contain_only_allowlisted_fields_and_hashed_refs(self):
        lines = []
        telemetry = Telemetry(KEY, lines.append)
        secrets = [
            'https://api.telegram.org/bot100:' + CANARY + '/sendMessage',
            'initData=' + CANARY,
            'Authorization: Bearer ' + CANARY,
            'Cookie=' + CANARY,
            '%50%52%49%56%41%54%45_' + CANARY,
        ]
        with telemetry.bind(
            bot_id=100, update_id=secrets[0], action_id=secrets[1], operation_id=secrets[2], job_id=secrets[3]
        ):
            telemetry.emit('operation', 'unknown', error=TimeoutError(str({'nested': secrets})), operation='write')
        output = '\n'.join(lines) + repr(telemetry.snapshot()) + repr(telemetry)
        for secret in secrets + [CANARY, KEY.decode()]:
            self.assertNotIn(secret, output)
        event = json.loads(lines[0])
        self.assertEqual(
            set(event),
            {'stage', 'outcome', 'duration_ms', 'attempt', 'error_code', 'error_category', 'error_outcome', 'context'},
        )
        self.assertEqual((event['error_code'], event['error_outcome']), ('timeout', 'unknown'))
        self.assertTrue(all(value is None or len(value) == 32 for value in event['context'].values()))
        with self.assertRaises(TypeError):
            telemetry.emit('job', 'failed', payload={'nested': secrets})

    def test_domains_bot_scope_and_identity_types_are_separate_and_references_are_stable(self):
        telemetry = Telemetry(KEY)
        with telemetry.bind(bot_id=100, update_id=1, action_id=1, operation_id=1, job_id=1) as first:
            self.assertEqual(len(set(asdict(first).values())), 6)
        with telemetry.bind(bot_id=100, update_id=1) as same:
            self.assertEqual(first.update_ref, same.update_ref)
            self.assertNotEqual(first.trace_id, same.trace_id)
        with telemetry.bind(bot_id=101, update_id=1) as another_bot:
            self.assertNotEqual(first.update_ref, another_bot.update_ref)
        with telemetry.bind(bot_id=100, update_id='1') as another_type:
            self.assertNotEqual(first.update_ref, another_type.update_ref)
        with Telemetry(b'x' * 32).bind(bot_id=100, update_id=1) as another_key:
            self.assertNotEqual(first.update_ref, another_key.update_ref)

    def test_nested_context_resets_after_error_and_inheritance_is_explicit_and_scoped(self):
        telemetry = Telemetry(KEY)
        other = Telemetry(KEY)
        with telemetry.bind(bot_id=100, update_id=7) as outer:
            self.assertIsNone(other.current())
            with telemetry.bind(bot_id=100, action_id='confirm', inherit=True) as nested:
                self.assertEqual((outer.trace_id, outer.update_ref), (nested.trace_id, nested.update_ref))
                self.assertIsNotNone(nested.action_ref)
            self.assertEqual(telemetry.current(), outer)
            with self.assertRaises(ValueError):
                with telemetry.bind(bot_id=100, job_id=8) as root:
                    self.assertIsNone(root.update_ref)
                    raise ValueError('fixture')
            self.assertEqual(telemetry.current(), outer)
            with self.assertRaises(ValidationFailure):
                with telemetry.bind(bot_id=101, inherit=True):
                    self.fail('Inherited a different bot')
        self.assertIsNone(telemetry.current())

    async def test_concurrent_tasks_keep_independent_update_action_operation_and_job_context(self):
        lines = []
        telemetry = Telemetry(KEY, lines.append)
        entered, release = asyncio.Event(), asyncio.Event()
        count = 0

        async def operation(identity):
            nonlocal count
            with telemetry.bind(
                bot_id=100, update_id=identity, action_id=identity, operation_id=identity, job_id=identity
            ) as own:
                count += 1
                if count == 2:
                    entered.set()
                await release.wait()
                self.assertEqual(telemetry.current(), own)
                telemetry.emit('job', 'succeeded', duration_ms=3)
                return own

        tasks = [asyncio.create_task(operation(identity)) for identity in (7, 8)]
        await entered.wait()
        self.assertIsNone(telemetry.current())
        release.set()
        first, second = await asyncio.gather(*tasks)
        self.assertNotEqual(first.trace_id, second.trace_id)
        self.assertNotEqual(first.operation_ref, second.operation_ref)
        self.assertEqual({json.loads(line)['context']['trace_id'] for line in lines}, {first.trace_id, second.trace_id})

    def test_metrics_have_finite_labels_without_ids_and_measure_duration_retries_and_failures(self):
        telemetry = Telemetry(KEY)
        for identity in range(1000):
            with telemetry.bind(bot_id=100, operation_id=identity):
                telemetry.emit('operation', 'replayed', duration_ms=5, attempt=2)
        telemetry.emit('action', 'rejected', duration_ms=7, error=PermissionDenied(CANARY))
        snapshot = telemetry.snapshot()
        self.assertEqual(len(snapshot.metrics), 2)
        replay = next(metric for metric in snapshot.metrics if metric.outcome == 'replayed')
        self.assertEqual(
            (replay.count, replay.duration_ms_sum, replay.duration_ms_max, replay.retries), (1000, 5000, 5, 1000)
        )
        refusal = next(metric for metric in snapshot.metrics if metric.outcome == 'rejected')
        self.assertEqual(refusal.error_category, 'permission')
        self.assertNotIn('operation_ref', repr(snapshot))
        with self.assertRaises(FrozenInstanceError):
            replay.count = 0

    def test_failing_sink_does_not_break_business_or_leak_exception_details(self):
        def broken(_line):
            raise RuntimeError(CANARY)

        telemetry = Telemetry(KEY, broken)
        self.assertIsNone(telemetry.emit('operation', 'succeeded', duration_ms=1))
        self.assertEqual(telemetry.snapshot().sink_failures, 1)
        self.assertEqual(telemetry.snapshot().metrics[0].count, 1)
        self.assertNotIn(CANARY, repr(telemetry.snapshot()))

    def test_async_sink_is_refused_and_wrapped_coroutine_is_closed_without_warning(self):
        async def asynchronous(_line):
            self.fail('Async sink executed')

        class AsyncSink:
            async def __call__(self, _line):
                raise AssertionError('Async callable executed')

        for sink in (asynchronous, AsyncSink(), 7):
            with self.subTest(sink=type(sink).__name__), self.assertRaises(InvalidType):
                Telemetry(KEY, sink)
        telemetry = Telemetry(KEY, lambda line: asynchronous(line))
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            telemetry.emit('job', 'succeeded')
            gc.collect()
        self.assertEqual(observed, [])
        self.assertEqual(telemetry.snapshot().sink_failures, 1)

    def test_invalid_fields_never_become_metric_labels_or_serialized_events(self):
        lines = []
        telemetry = Telemetry(KEY, lines.append)
        for changes in (
            {'stage': CANARY},
            {'outcome': CANARY},
            {'duration_ms': float('nan')},
            {'duration_ms': -1},
            {'duration_ms': True},
            {'duration_ms': 10**1000},
            {'attempt': True},
            {'attempt': 1001},
            {'operation': 'other'},
            {'error': object()},
        ):
            with self.subTest(changes=repr(changes)), self.assertRaises(ValidationFailure):
                telemetry.emit(**{'stage': 'job', 'outcome': 'failed', **changes})
        self.assertEqual((lines, telemetry.snapshot().metrics), ([], ()))
        for changes in (
            {'bot_id': True},
            {'bot_id': 0},
            {'update_id': []},
            {'update_id': '\ud800'},
            {'job_id': 'x' * 513},
            {'inherit': 'yes'},
        ):
            with self.subTest(changes=repr(changes)), self.assertRaises(ValidationFailure):
                with telemetry.bind(**{'bot_id': 100, **changes}):
                    self.fail('Invalid reference accepted')
        for key in (b'short', b'x' * 1025, 'x' * 32):
            with self.assertRaises(ValidationFailure):
                Telemetry(key)


if __name__ == '__main__':
    unittest.main()
