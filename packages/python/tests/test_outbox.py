"""Observable transaction, process failure and external-outcome boundaries."""

from __future__ import annotations

import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from _support import integration

from telegram_patterns import SQLiteOnce, UnsupportedCapability, ValidationFailure, safe_error_report
from telegram_patterns.outbox import OutboxConflict, OutboxLeaseLost, SQLiteOutbox

SCOPE = 'bot:100:notification'
PAYLOAD = {'method': 'sendMessage', 'chat_id': 42, 'text': 'Order accepted'}


def business_operation(database, mode='normal', barrier=None, queue=None):
    outbox, once = SQLiteOutbox(database), SQLiteOnce(database)

    def apply(connection):
        connection.execute("INSERT INTO business VALUES('order-1')")
        outbox.enqueue(connection, SCOPE, 'order-1:accepted', PAYLOAD, now=100)
        if mode == 'before-commit':
            os._exit(81)
        return {'order_id': 'order-1'}

    if barrier is not None:
        barrier.wait(timeout=10)
    result = once.run('actor:42:order', 'order-1', {'product': 7}, apply)
    if mode == 'after-commit':
        os._exit(82)
    if queue is not None:
        queue.put({'replayed': result.replayed, 'value': result.value})
    return result


def sending_process(database, provider, mode):
    outbox = SQLiteOutbox(database)
    claim = outbox.claim(SCOPE, 'sender', lease_seconds=10, now=100)
    if claim is None:
        raise AssertionError('No pending intent')
    if mode == 'before-send':
        os._exit(83)
    # Durable local stand-in for a remote service. No unique operation key:
    # a blind retry would visibly create a second external row.
    with closing(sqlite3.connect(provider)) as connection, connection:
        cursor = connection.execute('INSERT INTO external_effects(intent) VALUES(?)', (claim.operation_key,))
        receipt = {'message_id': cursor.lastrowid}
    if mode == 'lost-response':
        os._exit(84)
    outbox.confirm(claim, receipt, now=101)
    if mode == 'after-confirm':
        os._exit(85)


def claim_process(database, barrier, queue):
    barrier.wait(timeout=10)
    claim = SQLiteOutbox(database).claim(SCOPE, str(os.getpid()), now=100)
    queue.put(None if claim is None else claim.token)


class OutboxTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='transactional outbox ')
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'project.sqlite'
        self.provider = Path(temporary.name) / 'provider.sqlite'
        self.store = SQLiteOutbox(self.database, max_attempts=2)
        self.store.initialize()
        SQLiteOnce(self.database).initialize()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('CREATE TABLE business(id TEXT PRIMARY KEY)')
        with closing(sqlite3.connect(self.provider)) as connection, connection:
            connection.execute('CREATE TABLE external_effects(id INTEGER PRIMARY KEY,intent TEXT)')

    def enqueue(self, key='order-1:accepted', payload=PAYLOAD, scope=SCOPE):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            return self.store.enqueue(connection, scope, key, payload, now=100)

    def counts(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return tuple(
                connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in ('business', 'telegram_pattern_outbox')
            )

    def external_count(self):
        with closing(sqlite3.connect(self.provider)) as connection:
            return connection.execute('SELECT count(*) FROM external_effects').fetchone()[0]

    def unknown(self):
        self.enqueue()
        claim = self.store.claim(SCOPE, 'worker-a', lease_seconds=10, now=100)
        return claim, self.store.mark_unknown(claim, now=101)

    def test_business_and_intent_commit_once_and_duplicate_replays_business_receipt(self):
        first = business_operation(self.database)
        replay = business_operation(self.database)
        self.assertEqual((first.replayed, replay.replayed), (False, True))
        self.assertEqual(first.value, replay.value)
        self.assertEqual(self.counts(), (1, 1))
        self.assertEqual(self.store.get(SCOPE, 'order-1:accepted').state, 'pending')

    def test_enqueue_never_commits_business_and_rollback_removes_both(self):
        with closing(sqlite3.connect(self.database, isolation_level=None)) as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute("INSERT INTO business VALUES('rollback')")
            receipt = self.store.enqueue(connection, SCOPE, 'rollback', PAYLOAD, now=100)
            self.assertFalse(receipt.duplicate)
            self.assertTrue(connection.in_transaction)
            self.assertEqual(self.counts(), (0, 0))
            connection.rollback()
        self.assertEqual(self.counts(), (0, 0))

    def test_duplicate_intent_is_read_only_and_changed_payload_conflict_rolls_back_business(self):
        first = self.enqueue()
        duplicate = self.enqueue()
        self.assertEqual((first.duplicate, duplicate.duplicate), (False, True))
        with self.assertRaises(OutboxConflict):
            with closing(sqlite3.connect(self.database)) as connection, connection:
                connection.execute("INSERT INTO business VALUES('must-rollback')")
                self.store.enqueue(connection, SCOPE, 'order-1:accepted', {**PAYLOAD, 'text': 'Changed'})
        self.assertEqual(self.counts(), (0, 1))
        self.assertEqual(self.store.get(SCOPE, 'order-1:accepted').payload, PAYLOAD)

    def test_enqueue_refuses_autocommit_memory_and_different_main_database(self):
        with closing(sqlite3.connect(self.database, isolation_level=None)) as connection:
            with self.assertRaises(ValidationFailure):
                self.store.enqueue(connection, SCOPE, 'key', PAYLOAD)
        for database in (':memory:', str(self.provider)):
            with self.subTest(database=database), closing(sqlite3.connect(database)) as connection:
                connection.execute('BEGIN')
                with self.assertRaises(ValidationFailure):
                    self.store.enqueue(connection, SCOPE, 'key', PAYLOAD)
                self.assertTrue(connection.in_transaction)
        with self.assertRaises(ValidationFailure):
            self.store.enqueue(object(), SCOPE, 'key', PAYLOAD)
        self.assertEqual(self.counts(), (0, 0))

    def test_pending_claim_is_durable_scoped_and_returns_detached_payload(self):
        self.enqueue(scope='other')
        self.assertIsNone(self.store.claim(SCOPE, 'worker', now=100))
        self.enqueue()
        self.assertIsNone(self.store.claim(SCOPE, 'worker', now=99))
        claim = self.store.claim(SCOPE, 'worker', now=100)
        claim.payload['text'] = 'Caller mutation'
        self.assertEqual(claim.payload, PAYLOAD)
        record = SQLiteOutbox(self.database).get(SCOPE, claim.operation_key)
        self.assertEqual((record.state, record.attempts, record.revision), ('sending', 1, 1))
        self.assertIsNone(self.store.claim(SCOPE, 'another-worker', now=101))
        self.assertNotIn('Order accepted', repr(claim))
        self.assertNotIn(claim.token, repr(claim))

    def test_confirm_persists_receipt_and_idempotent_confirmation_refuses_changed_result(self):
        self.enqueue()
        claim = self.store.claim(SCOPE, 'worker', now=100)
        first = self.store.confirm(claim, {'message_id': 55}, now=101)
        repeated = self.store.confirm(claim, {'message_id': 55}, now=150)
        self.assertEqual(first, repeated)
        self.assertEqual(self.enqueue().state, 'sent')
        first.result['message_id'] = 99
        self.assertEqual(self.store.get(SCOPE, claim.operation_key).result, {'message_id': 55})
        with self.assertRaises(OutboxConflict):
            self.store.confirm(claim, {'message_id': 56}, now=102)
        self.assertIsNone(self.store.claim(SCOPE, 'worker-b', now=1000))

    def test_lease_boundary_expires_to_unknown_without_automatic_retry(self):
        self.enqueue()
        claim = self.store.claim(SCOPE, 'worker', lease_seconds=10, now=100)
        self.assertEqual(self.store.recover_expired(SCOPE, now=109.9), 0)
        with self.assertRaises(OutboxLeaseLost):
            self.store.confirm(claim, {'message_id': 5}, now=110)
        self.assertEqual(self.store.recover_expired(SCOPE, now=110), 1)
        self.assertEqual(self.store.recover_expired(SCOPE, now=111), 0)
        record = self.store.get(SCOPE, claim.operation_key)
        self.assertEqual((record.state, record.reason, record.attempts), ('unknown', 'lease-expired', 1))
        self.assertEqual(self.enqueue().state, 'unknown')
        self.assertIsNone(self.store.claim(SCOPE, 'replacement', now=10000))
        with self.assertRaises(OutboxLeaseLost):
            self.store.confirm(claim, {'message_id': 5}, now=111)

    def test_lost_lease_error_report_never_implies_absence_of_external_effect(self):
        report = safe_error_report(OutboxLeaseLost('Secret remote details'), operation='write')
        self.assertEqual((report.outcome, report.recovery), ('unknown', 'reconcile'))
        self.assertNotIn('Secret', report.message)

    def test_timeout_can_mark_expired_claim_unknown_and_repeated_mark_is_read_only(self):
        self.enqueue()
        claim = self.store.claim(SCOPE, 'worker', lease_seconds=1, now=100)
        first = self.store.mark_unknown(claim, now=102)
        self.assertEqual(first, self.store.mark_unknown(claim, now=103))
        self.assertEqual((first.state, first.reason), ('unknown', 'worker-unknown'))

    def test_foreign_and_stale_claim_cannot_confirm_or_change_new_attempt(self):
        claim, unknown = self.unknown()
        for forged in (replace(claim, token='foreign'), replace(claim, worker_id='foreign'), replace(claim, attempt=2)):
            with self.subTest(forged=repr(forged)), self.assertRaises(OutboxLeaseLost):
                self.store.confirm(forged, {}, now=102)
        self.store.reconcile(
            SCOPE,
            claim.operation_key,
            expected_revision=unknown.revision,
            outcome='absent',
            evidence_ref='final-rejection:1',
            now=102,
        )
        current = self.store.claim(SCOPE, 'worker-b', now=103)
        self.assertNotEqual(claim.token, current.token)
        for action in (lambda: self.store.confirm(claim, {}, now=104), lambda: self.store.mark_unknown(claim, now=104)):
            with self.assertRaises(OutboxLeaseLost):
                action()
        self.assertEqual(self.store.get(SCOPE, claim.operation_key).state, 'sending')

    def test_unresolved_reconciliation_stays_unknown_and_fences_stale_evidence(self):
        claim, record = self.unknown()
        current = self.store.reconcile(
            SCOPE,
            claim.operation_key,
            expected_revision=record.revision,
            outcome='unresolved',
            evidence_ref='review:1',
            now=102,
        )
        self.assertEqual((current.state, current.evidence_ref), ('unknown', 'review:1'))
        self.assertIsNone(self.store.claim(SCOPE, 'other', now=103))
        with self.assertRaises(OutboxConflict):
            self.store.reconcile(
                SCOPE,
                claim.operation_key,
                expected_revision=record.revision,
                outcome='absent',
                evidence_ref='stale-review',
                now=104,
            )

    def test_confirmed_reconciliation_saves_known_result_without_another_send(self):
        claim, record = self.unknown()
        result = self.store.reconcile(
            SCOPE,
            claim.operation_key,
            expected_revision=record.revision,
            outcome='sent',
            evidence_ref='provider:message-9',
            result={'message_id': 9},
            now=102,
        )
        self.assertEqual((result.state, result.result), ('sent', {'message_id': 9}))
        self.assertIsNone(self.store.claim(SCOPE, 'other', now=1000))
        with self.assertRaises(OutboxLeaseLost):
            self.store.confirm(claim, {'message_id': 9}, now=103)

    def test_proven_absence_delays_retry_and_exhausted_attempts_become_failed(self):
        claim, record = self.unknown()
        pending = self.store.reconcile(
            SCOPE,
            claim.operation_key,
            expected_revision=record.revision,
            outcome='absent',
            evidence_ref='final-rejection:1',
            retry_after=5,
            now=102,
        )
        self.assertEqual((pending.state, pending.available_at), ('pending', 107))
        self.assertIsNone(self.store.claim(SCOPE, 'worker-b', now=106))
        second = self.store.claim(SCOPE, 'worker-b', now=107)
        self.assertEqual(second.attempt, 2)
        record = self.store.mark_unknown(second, now=108)
        failed = self.store.reconcile(
            SCOPE,
            claim.operation_key,
            expected_revision=record.revision,
            outcome='absent',
            evidence_ref='final-rejection:2',
            now=109,
        )
        self.assertEqual((failed.state, failed.reason, failed.attempts), ('failed', 'attempts-exhausted', 2))
        self.assertEqual(self.enqueue().state, 'failed')
        self.assertIsNone(self.store.claim(SCOPE, 'worker-c', now=1000))

    def test_invalid_json_and_oversized_payload_do_not_create_intent(self):
        for payload in ({1: 'x'}, {'value': float('nan')}, {'value': object()}, {'value': (1, 2)}, []):
            with self.subTest(payload=repr(payload)), self.assertRaises(ValidationFailure):
                self.enqueue(payload=payload)
        limited = SQLiteOutbox(self.database, max_payload_bytes=128)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('BEGIN')
            with self.assertRaises(ValidationFailure):
                limited.enqueue(connection, SCOPE, 'big', {'text': 'Ж' * 100})
        self.assertEqual(self.counts(), (0, 0))

    def test_invalid_success_receipt_keeps_sending_until_explicit_unknown_recovery(self):
        self.enqueue()
        claim = self.store.claim(SCOPE, 'worker', lease_seconds=1, now=100)
        with self.assertRaises(ValidationFailure):
            self.store.confirm(claim, {'value': float('inf')}, now=100)
        self.assertEqual(self.store.get(SCOPE, claim.operation_key).state, 'sending')
        self.store.recover_expired(SCOPE, now=101)
        self.assertEqual(self.store.get(SCOPE, claim.operation_key).state, 'unknown')

    def test_reconciliation_requires_unknown_current_revision_and_bounded_evidence(self):
        self.assertIsNone(self.store.get(SCOPE, 'missing'))
        with self.assertRaises(OutboxConflict):
            self.store.reconcile(SCOPE, 'missing', expected_revision=0, outcome='sent', evidence_ref='audit:1')
        self.enqueue()
        with self.assertRaises(OutboxConflict):
            self.store.reconcile(
                SCOPE, 'order-1:accepted', expected_revision=0, outcome='absent', evidence_ref='audit:1'
            )
        for changes in (
            {'outcome': 'retry'},
            {'outcome': []},
            {'evidence_ref': ''},
            {'evidence_ref': 'x' * 513},
            {'expected_revision': True},
            {'retry_after': -1},
            {'retry_after': float('nan')},
            {'outcome': 'sent', 'retry_after': 1},
            {'outcome': 'absent', 'result': {'id': 1}},
        ):
            arguments = {'expected_revision': 0, 'outcome': 'unresolved', 'evidence_ref': 'audit:1', **changes}
            with self.subTest(changes=repr(changes)), self.assertRaises(ValidationFailure):
                self.store.reconcile(SCOPE, 'order-1:accepted', **arguments)

    def test_constructor_identity_and_time_validation_precedes_work(self):
        for changes in (
            {'database': ''},
            {'database': ':memory:'},
            {'max_attempts': True},
            {'max_attempts': 0},
            {'max_attempts': 1001},
            {'max_payload_bytes': 127},
            {'timeout': float('inf')},
        ):
            with self.subTest(changes=repr(changes)), self.assertRaises(ValidationFailure):
                SQLiteOutbox(**{'database': self.database, **changes})
        for scope in ('', 'x' * 257, '\ud800', None):
            with self.subTest(scope=repr(scope)), self.assertRaises(ValidationFailure):
                self.store.claim(scope, 'worker', now=100)
        for changes in (
            {'worker_id': ''},
            {'worker_id': 'x' * 129},
            {'lease_seconds': 0},
            {'now': True},
            {'now': float('nan')},
            {'now': 10**1000},
            {'now': 2**53, 'lease_seconds': 0.1},
        ):
            with self.subTest(changes=repr(changes)), self.assertRaises(ValidationFailure):
                self.store.claim(SCOPE, **{'worker_id': 'worker', 'now': 100, **changes})
        self.assertEqual(self.counts(), (0, 0))

    def test_initialize_is_idempotent_and_refuses_unsupported_schema(self):
        self.enqueue()
        self.store.initialize()
        self.assertEqual(self.counts(), (0, 1))
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('UPDATE telegram_pattern_outbox_meta SET schema_version=2')
        with self.assertRaises(UnsupportedCapability):
            self.store.initialize()

    def spawn(self, target, *arguments):
        process = multiprocessing.get_context('spawn').Process(target=target, args=arguments)
        process.start()

        def cleanup():
            if process.is_alive():
                process.terminate()
            process.join(timeout=10)
            process.close()

        self.addCleanup(cleanup)
        return process

    @integration
    def test_two_processes_same_business_operation_commit_one_state_and_one_intent(self):
        context = multiprocessing.get_context('spawn')
        barrier, queue = context.Barrier(2), context.Queue()
        self.addCleanup(queue.close)
        workers = [self.spawn(business_operation, self.database, 'normal', barrier, queue) for _ in range(2)]
        results = [queue.get(timeout=15) for _ in workers]
        for worker in workers:
            worker.join(timeout=10)
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual(sorted(result['replayed'] for result in results), [False, True])
        self.assertEqual(self.counts(), (1, 1))

    @integration
    def test_two_processes_cannot_claim_the_same_external_attempt(self):
        self.enqueue()
        context = multiprocessing.get_context('spawn')
        barrier, queue = context.Barrier(2), context.Queue()
        self.addCleanup(queue.close)
        workers = [self.spawn(claim_process, self.database, barrier, queue) for _ in range(2)]
        results = [queue.get(timeout=15) for _ in workers]
        for worker in workers:
            worker.join(timeout=10)
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(self.store.get(SCOPE, 'order-1:accepted').attempts, 1)

    @integration
    def test_process_crash_before_business_commit_rolls_back_state_and_intent(self):
        worker = self.spawn(business_operation, self.database, 'before-commit')
        worker.join(timeout=10)
        self.assertEqual(worker.exitcode, 81)
        self.assertEqual(self.counts(), (0, 0))
        business_operation(self.database)
        self.assertEqual(self.counts(), (1, 1))

    @integration
    def test_process_crash_after_business_commit_keeps_intent_and_replays_business(self):
        worker = self.spawn(business_operation, self.database, 'after-commit')
        worker.join(timeout=10)
        self.assertEqual(worker.exitcode, 82)
        self.assertEqual(self.counts(), (1, 1))
        self.assertTrue(business_operation(self.database).replayed)
        self.assertEqual(self.store.get(SCOPE, 'order-1:accepted').state, 'pending')

    @integration
    def test_sender_crash_before_send_needs_proven_absence_before_retry(self):
        self.enqueue()
        worker = self.spawn(sending_process, self.database, self.provider, 'before-send')
        worker.join(timeout=10)
        self.assertEqual(worker.exitcode, 83)
        self.assertEqual(self.external_count(), 0)
        self.assertIsNone(self.store.claim(SCOPE, 'restarted', now=111))
        record = self.store.get(SCOPE, 'order-1:accepted')
        self.assertEqual(record.state, 'unknown')
        # In this fixture the old process is dead, its only sender never ran,
        # and the provider is fully observable: no late effect is possible.
        self.store.reconcile(
            SCOPE,
            record.operation_key,
            expected_revision=record.revision,
            outcome='absent',
            evidence_ref='dead-process:no-provider-call',
            now=112,
        )
        claim = self.store.claim(SCOPE, 'restarted', now=113)
        self.assertEqual(claim.attempt, 2)

    @integration
    def test_lost_external_response_remains_unknown_and_reconciles_without_duplicate_send(self):
        self.enqueue()
        worker = self.spawn(sending_process, self.database, self.provider, 'lost-response')
        worker.join(timeout=10)
        self.assertEqual(worker.exitcode, 84)
        self.assertEqual(self.external_count(), 1)
        self.assertIsNone(self.store.claim(SCOPE, 'restarted', now=111))
        record = self.store.get(SCOPE, 'order-1:accepted')
        self.assertEqual(record.state, 'unknown')
        self.store.reconcile(
            SCOPE,
            record.operation_key,
            expected_revision=record.revision,
            outcome='sent',
            evidence_ref='provider:message-1',
            result={'message_id': 1},
            now=112,
        )
        self.assertIsNone(self.store.claim(SCOPE, 'restarted', now=1000))
        self.assertEqual(self.external_count(), 1)
        self.assertEqual(self.store.get(SCOPE, record.operation_key).result, {'message_id': 1})

    @integration
    def test_sender_crash_after_confirmation_preserves_sent_receipt(self):
        self.enqueue()
        worker = self.spawn(sending_process, self.database, self.provider, 'after-confirm')
        worker.join(timeout=10)
        self.assertEqual(worker.exitcode, 85)
        restarted = SQLiteOutbox(self.database)
        record = restarted.get(SCOPE, 'order-1:accepted')
        self.assertEqual((record.state, record.result), ('sent', {'message_id': 1}))
        self.assertIsNone(restarted.claim(SCOPE, 'restarted', now=1000))
        self.assertEqual(self.external_count(), 1)


if __name__ == '__main__':
    unittest.main()
