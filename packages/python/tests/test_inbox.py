"""Durable receipt, real SQLite concurrency, lease fencing and explicit quarantine."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from _support import integration

from telegram_patterns.errors import UnsupportedCapability, ValidationFailure, safe_error_report
from telegram_patterns.inbox import InboxConflict, InboxLeaseLost, SQLiteInbox
from telegram_patterns.sqlite_once import SQLiteOnce


def _receive_worker(database, ready, results):
    store = SQLiteInbox(database)
    ready.wait(10)
    receipt = store.receive(100, 1, {'update_id': 1, 'message': {'text': 'fixture'}}, now=100)
    results.put((receipt.duplicate, receipt.state))


def _claim_worker(database, ready, results):
    store = SQLiteInbox(database)
    ready.wait(10)
    claim = store.claim(100, str(os.getpid()), now=100)
    results.put(None if claim is None else (claim.update_id, claim.token))


def _effect_then_crash(database):
    store = SQLiteInbox(database)
    claim = store.claim(100, 'crashed-worker', lease_seconds=10, now=100)
    if claim is None:
        raise AssertionError('Expected a receipt')
    once = SQLiteOnce(database)

    def effect(db):
        db.execute('UPDATE business_counter SET value=value+1')
        return {'applied': True}

    once.run('bot:100', 'update:1', claim.payload, effect)
    os._exit(23)  # Durable effect happened; queue completion did not.


def _legacy_v1_database(path):
    payload = json.dumps(
        {'update_id': 1, 'pre_checkout_query': {'id': 'old-query'}}, sort_keys=True, separators=(',', ':')
    )
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(
            'CREATE TABLE telegram_pattern_inbox_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),'
            'schema_version INTEGER NOT NULL)'
        )
        db.execute('INSERT INTO telegram_pattern_inbox_meta VALUES(1,1)')
        db.execute("""CREATE TABLE telegram_pattern_inbox (
            bot_id INTEGER NOT NULL, update_id INTEGER NOT NULL, payload_version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,payload_hash TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('pending','processing','done','quarantined')),
            reason TEXT,received_at REAL NOT NULL,available_at REAL NOT NULL,
            attempts INTEGER NOT NULL,max_attempts INTEGER NOT NULL,worker_id TEXT,claim_token TEXT,lease_until REAL,
            PRIMARY KEY(bot_id,update_id))""")
        db.execute(
            "INSERT INTO telegram_pattern_inbox VALUES(100,1,1,?,?,'pending',NULL,100,100,0,5,NULL,NULL,NULL)",
            (payload, hashlib.sha256(payload.encode()).hexdigest()),
        )
        db.execute('CREATE TABLE business(value TEXT)')
        db.execute("INSERT INTO business VALUES('preserve')")
    return payload


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='inbox-test-')
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / 'inbox.sqlite'
        self.store = SQLiteInbox(self.database)
        self.store.initialize()

    def receive(self, update_id=1, **kwargs):
        return self.store.receive(
            100, update_id, {'update_id': update_id, 'message': {'text': 'fixture'}}, now=100, **kwargs
        )

    def test_duplicate_receipt_is_read_only_and_identity_is_bot_scoped(self):
        initial = self.receive()
        self.assertEqual((initial.state, initial.duplicate, initial.reason), ('pending', False, None))
        duplicate = self.store.receive(
            100, 1, {'message': {'text': 'fixture'}, 'update_id': 1}, quarantine_reason='unknown-update-kind', now=200
        )
        self.assertEqual((duplicate.state, duplicate.duplicate, duplicate.reason), ('pending', True, None))
        self.assertEqual(self.store.get(100, 1).received_at, 100)
        self.store.receive(200, 1, {'update_id': 1, 'other': 'bot'}, now=100)
        self.assertEqual(self.store.counts(100), {'pending': 1, 'processing': 0, 'done': 0, 'quarantined': 0})
        self.assertEqual(self.store.get(200, 1).payload['other'], 'bot')
        for payload, version in [
            ({'update_id': 1, 'message': {'text': 'changed'}}, 1),
            ({'update_id': 1, 'message': {'text': 'fixture'}}, 2),
        ]:
            with self.assertRaises(InboxConflict):
                self.store.receive(100, 1, payload, payload_version=version, now=201)
        self.assertEqual(SQLiteInbox(self.database).get(100, 1).payload['message']['text'], 'fixture')

    def test_future_version_and_unknown_kind_are_durable_quarantine(self):
        version = self.receive(payload_version=2)
        kind = self.store.receive(
            100,
            2,
            {'update_id': 2, 'future_kind': {'secret': 'PRIVATE_CANARY'}},
            quarantine_reason='unknown-update-kind',
            now=101,
        )
        self.assertEqual((version.state, version.reason), ('quarantined', 'unsupported-version'))
        self.assertEqual((kind.state, kind.reason), ('quarantined', 'unknown-update-kind'))
        reopened = SQLiteInbox(self.database)
        record = reopened.get(100, 2)
        self.assertEqual(record.payload['future_kind']['secret'], 'PRIVATE_CANARY')
        self.assertNotIn('PRIVATE_CANARY', repr(record))
        self.assertNotIn('PRIVATE_CANARY', repr(kind))
        self.assertEqual(reopened.counts(100)['quarantined'], 2)
        self.assertIsNone(reopened.claim(100, 'worker', now=200))
        # Installing a decoder does not silently release an existing quarantine.
        self.assertIsNone(SQLiteInbox(self.database, supported_versions=(1, 2)).claim(100, 'new-code', now=200))

    def test_invalid_admission_does_not_create_a_receipt(self):
        calls = [
            lambda: self.store.receive(True, 1, {'update_id': 1}),
            lambda: self.store.receive(0, 1, {'update_id': 1}),
            lambda: self.store.receive(2**63, 1, {'update_id': 1}),
            lambda: self.store.receive(100, -1, {'update_id': -1}),
            lambda: self.store.receive(100, True, {'update_id': True}),
            lambda: self.store.receive(100, 1, {'update_id': True}),
            lambda: self.store.receive(100, 1, {'update_id': 2}),
            lambda: self.store.receive(100, 1, {'update_id': 1, 'bad': float('nan')}),
            lambda: self.store.receive(100, 1, {'update_id': 1, 'bad': object()}),
            lambda: self.store.receive(100, 1, {'update_id': 1, 'bad': '\ud800'}),
            lambda: self.store.receive(100, 1, {'update_id': 1}, payload_version=True),
            lambda: self.store.receive(100, 1, {'update_id': 1}, payload_version=0),
            lambda: self.store.receive(100, 1, {'update_id': 1}, quarantine_reason='PRIVATE_CANARY'),
            lambda: self.store.receive(100, 1, {'update_id': 1}, now=float('nan')),
            lambda: self.store.receive(100, 1, {'update_id': 1}, now=10**1000),
        ]
        for number, call in enumerate(calls):
            with self.subTest(case=number), self.assertRaises(ValidationFailure):
                call()
        self.assertEqual(sum(self.store.counts(100).values()), 0)
        with self.assertRaises(ValidationFailure):
            self.store.get(100, None)

    def test_payload_size_is_utf8_bounded_at_the_exact_limit(self):
        store = SQLiteInbox(self.database, max_payload_bytes=128)
        overhead = len(json.dumps({'update_id': 1, 'text': ''}, separators=(',', ':'), sort_keys=True).encode())
        room = 128 - overhead
        text = 'é' * (room // 2) + ('x' if room % 2 else '')
        store.receive(100, 1, {'update_id': 1, 'text': text}, now=100)
        self.assertEqual(len(store.get(100, 1).payload_json.encode('utf-8')), 128)
        with self.assertRaises(ValidationFailure):
            store.receive(100, 2, {'update_id': 2, 'text': text + 'x'}, now=100)
        self.assertIsNone(store.get(100, 2))

    def test_claim_and_record_payload_are_detached_and_safe_to_display(self):
        payload = {'update_id': 1, 'message': {'text': 'PRIVATE_CANARY'}}
        receipt = self.store.receive(100, 1, payload, now=100)
        payload['message']['text'] = 'changed'
        claim = self.store.claim(100, 'worker', now=100)
        self.assertEqual(claim.payload['message']['text'], 'PRIVATE_CANARY')
        decoded = claim.payload
        decoded['message']['text'] = 'changed-again'
        self.assertEqual(claim.payload['message']['text'], 'PRIVATE_CANARY')
        self.assertNotIn('PRIVATE_CANARY', repr(claim))
        self.assertNotIn(claim.token, repr(claim))
        with self.assertRaises(FrozenInstanceError):
            receipt.state = 'done'

    def test_expiry_reclaim_and_fencing_reject_stale_owners(self):
        self.receive()
        first = self.store.claim(100, 'old', lease_seconds=10, now=100)
        self.assertIsNone(self.store.claim(100, 'other', now=109.999))
        with self.assertRaises(InboxLeaseLost):
            self.store.complete(first, now=110)
        second = SQLiteInbox(self.database).claim(100, 'new', lease_seconds=10, now=110)
        self.assertEqual((second.update_id, second.attempt), (1, 2))
        self.assertNotEqual(first.token, second.token)
        for old in (
            first,
            replace(second, worker_id='forged'),
            replace(second, token='0' * 32),
            replace(second, attempt=1),
        ):
            with self.subTest(worker=old.worker_id), self.assertRaises(InboxLeaseLost):
                self.store.complete(old, now=111)
        result = self.store.complete(second, now=111)
        self.assertEqual(result.state, 'done')
        self.assertEqual(self.store.complete(second, now=999).state, 'done')
        self.assertEqual(self.store.counts(100)['done'], 1)
        self.assertIsNone(self.store.claim(100, 'another', now=1000))

    def test_retry_delay_and_attempt_budget_survive_reopen(self):
        store = SQLiteInbox(self.database, max_attempts=2)
        store.receive(100, 1, {'update_id': 1}, now=100)
        first = store.claim(100, 'worker', lease_seconds=10, now=100)
        self.assertEqual(store.retry(first, delay_seconds=5, now=101).state, 'pending')
        reopened = SQLiteInbox(self.database, max_attempts=999)
        self.assertIsNone(reopened.claim(100, 'worker', now=105.999))
        second = reopened.claim(100, 'worker', now=106)
        self.assertEqual(second.attempt, 2)
        receipt = reopened.retry(second, delay_seconds=0, now=107)
        self.assertEqual((receipt.state, receipt.reason), ('quarantined', 'attempts-exhausted'))
        self.assertEqual(reopened.get(100, 1).max_attempts, 2)
        self.assertIsNone(reopened.claim(100, 'worker', now=1000))

    def test_expired_processing_claim_reports_unknown_business_outcome(self):
        self.receive()
        claim = self.store.claim(100, 'worker', lease_seconds=10, now=100)
        with self.assertRaises(InboxLeaseLost) as raised:
            self.store.complete(claim, now=110)
        report = safe_error_report(raised.exception, operation='write')
        self.assertEqual((report.code, report.outcome, report.recovery), ('unknown-outcome', 'unknown', 'reconcile'))
        self.assertEqual(self.store.get(100, 1).state, 'processing')

    def test_expired_last_attempt_is_quarantined_without_dropping_payload(self):
        store = SQLiteInbox(self.database, max_attempts=1)
        store.receive(100, 1, {'update_id': 1, 'message': {'text': 'preserved'}}, now=100)
        claim = store.claim(100, 'crashed', lease_seconds=10, now=100)
        self.assertIsNone(store.claim(100, 'replacement', now=110))
        record = store.get(100, 1)
        self.assertEqual((record.state, record.reason, record.attempts), ('quarantined', 'attempts-exhausted', 1))
        self.assertEqual(record.payload['message']['text'], 'preserved')
        with self.assertRaises(InboxLeaseLost):
            store.complete(claim, now=110)

    def test_only_supported_versions_and_requested_bot_can_be_claimed(self):
        other = SQLiteInbox(self.database, supported_versions=(2,))
        other.receive(100, 1, {'update_id': 1}, payload_version=2, now=100)
        self.store.receive(200, 1, {'update_id': 1}, now=100)
        self.assertIsNone(self.store.claim(100, 'v1-worker', now=100))
        claim = other.claim(100, 'v2-worker', now=100)
        self.assertEqual((claim.bot_id, claim.payload_version), (100, 2))
        self.assertEqual(self.store.get(200, 1).state, 'pending')

    def test_every_transition_rejects_an_expired_or_retried_claim(self):
        self.receive()
        claim = self.store.claim(100, 'worker', lease_seconds=10, now=100)
        actions = [
            lambda: self.store.complete(claim, now=110),
            lambda: self.store.retry(claim, delay_seconds=0, now=110),
            lambda: self.store.quarantine(claim, reason='decode-failed', now=110),
            lambda: self.store.renew(claim, now=110),
        ]
        for action in actions:
            with self.assertRaises(InboxLeaseLost):
                action()
        self.store.retry(claim, delay_seconds=0, now=109)
        for action in [
            lambda: self.store.complete(claim, now=109),
            lambda: self.store.renew(claim, now=109),
            lambda: self.store.retry(claim, delay_seconds=0, now=109),
        ]:
            with self.assertRaises(InboxLeaseLost):
                action()
        self.assertEqual(self.store.claim(100, 'next', now=109).attempt, 2)

    def test_renew_and_quarantine_do_not_allow_expired_or_changed_outcome(self):
        self.receive()
        claim = self.store.claim(100, 'worker', lease_seconds=10, now=100)
        renewed = self.store.renew(claim, lease_seconds=10, now=105)
        self.assertEqual(renewed.lease_until, 115)
        shortened = self.store.renew(renewed, lease_seconds=1, now=106)
        self.assertEqual(shortened.lease_until, 115)
        self.assertIsNone(self.store.claim(100, 'other', now=114))
        result = self.store.quarantine(renewed, reason='decode-failed', now=114)
        self.assertEqual((result.state, result.reason), ('quarantined', 'decode-failed'))
        self.assertEqual(self.store.quarantine(renewed, reason='decode-failed', now=200).state, 'quarantined')
        with self.assertRaises(InboxConflict):
            self.store.quarantine(renewed, reason='manual-review', now=200)
        with self.assertRaises(InboxLeaseLost):
            self.store.complete(renewed, now=114)

    def test_invalid_worker_transition_parameters_leave_claim_unchanged(self):
        self.receive()
        for worker, seconds in [
            ('', 1),
            ('\ud800', 1),
            ('x' * 129, 1),
            ('x', 0),
            ('x', 3601),
            ('x', float('inf')),
            ('x', True),
        ]:
            with self.subTest(seconds=str(seconds)), self.assertRaises(ValidationFailure):
                self.store.claim(100, worker, lease_seconds=seconds, now=100)
        with self.assertRaises(ValidationFailure):
            self.store.claim(100, 'worker', lease_seconds=1, now=float(2**53))
        with self.assertRaises(ValidationFailure):
            self.store.claim(100, 'worker', lease_seconds=1e-30, now=100)
        claim = self.store.claim(100, 'worker', now=100)
        for action in [
            lambda: self.store.retry(claim, delay_seconds=-1, now=101),
            lambda: self.store.retry(claim, delay_seconds=86401, now=101),
            lambda: self.store.quarantine(claim, reason='PRIVATE_CANARY', now=101),
            lambda: self.store.renew(claim, lease_seconds=0, now=101),
            lambda: self.store.complete(object(), now=101),
        ]:
            with self.assertRaises(ValidationFailure):
                action()
        self.assertEqual((self.store.get(100, 1).state, self.store.get(100, 1).attempts), ('processing', 1))

    def test_schema_initialization_preserves_existing_data_and_refuses_future_schema(self):
        self.receive()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE business(value TEXT)')
            db.execute("INSERT INTO business VALUES ('preserve')")
        self.store.initialize()
        with closing(sqlite3.connect(self.database)) as db, db:
            self.assertEqual(db.execute('SELECT value FROM business').fetchone()[0], 'preserve')
            db.execute('UPDATE telegram_pattern_inbox_meta SET schema_version=999')
        with self.assertRaises(UnsupportedCapability):
            self.store.initialize()
        self.assertEqual(self.store.get(100, 1).state, 'pending')

    def test_priority_lanes_are_explicit_and_default_claim_preserves_fifo(self):
        self.store.receive(100, 1, {'update_id': 1, 'message': {}}, priority=0, now=100)
        self.store.receive(100, 2, {'update_id': 2, 'pre_checkout_query': {}}, priority=1, now=101)
        self.store.receive(100, 3, {'update_id': 3, 'other': {}}, priority=2, now=102)
        ordinary = self.store.claim(100, 'default', now=103)
        self.assertEqual(
            ordinary.update_id, 1, 'None retains existing FIFO rather than silently preferring a larger priority'
        )
        critical = self.store.claim(100, 'critical', priorities=(2, 1), now=103)
        self.assertEqual(
            critical.update_id, 2, 'filter order cannot rewrite first-seen order within the selected lanes'
        )
        self.assertEqual(self.store.complete(critical, now=104).priority, 1)
        self.assertEqual(self.store.get(100, 2).received_at, 101)
        self.assertEqual(self.store.get(100, 3).received_at, 102)
        self.assertIsNone(self.store.claim(100, 'ordinary', priorities=(0,), now=104))
        self.assertEqual(self.store.claim(100, 'second-lane', priorities=(2,), now=104).update_id, 3)

    def test_replayed_priority_and_time_do_not_promote_or_refresh_an_existing_receipt(self):
        payload = {'update_id': 1, 'pre_checkout_query': {'id': 'original'}}
        original = self.store.receive(100, 1, payload, priority=0, now=100)
        replay = self.store.receive(100, 1, payload, priority=255, now=999)
        record = SQLiteInbox(self.database).get(100, 1)
        self.assertEqual((original.priority, replay.priority, record.priority), (0, 0, 0))
        self.assertTrue(replay.duplicate)
        self.assertEqual((record.received_at, record.available_at), (100, 100))
        self.assertEqual(record.payload, payload)
        self.assertIsNone(self.store.claim(100, 'urgent', priorities=(255,), now=1000))
        self.assertEqual(self.store.claim(100, 'ordinary', priorities=(0,), now=1000).update_id, 1)

    def test_invalid_priority_and_lane_filters_cannot_change_or_claim_queue_state(self):
        for priority in (True, False, -1, 256, 1.0, '1', None):
            with self.subTest(priority=priority), self.assertRaises(ValidationFailure):
                self.store.receive(100, 1, {'update_id': 1}, priority=priority, now=100)
        self.assertIsNone(self.store.get(100, 1))
        self.receive()
        for lanes in ((), [], [0], (True,), (1.0,), (-1,), (256,), ('0 OR 1=1',), (1, 1), tuple(range(17))):
            with self.subTest(lanes=repr(lanes)), self.assertRaises(ValidationFailure):
                self.store.claim(100, 'worker', priorities=lanes, now=100)
        record = self.store.get(100, 1)
        self.assertEqual((record.state, record.attempts), ('pending', 0))

    def test_version_one_reopen_migrates_zero_lane_without_freshness_or_business_changes(self):
        path = Path(self.temporary.name) / 'legacy-v1.sqlite'
        payload = _legacy_v1_database(path)
        migrated = SQLiteInbox(path)
        migrated.initialize()
        migrated.initialize()
        reopened = SQLiteInbox(path)
        record = reopened.get(100, 1)
        self.assertEqual((record.priority, record.received_at, record.available_at, record.attempts), (0, 100, 100, 0))
        self.assertEqual(record.payload_json, payload)
        replay = reopened.receive(100, 1, record.payload, priority=1, now=1000)
        self.assertEqual((replay.priority, replay.duplicate), (0, True))
        self.assertIsNone(reopened.claim(100, 'urgent', priorities=(1,), now=1000))
        self.assertEqual(reopened.claim(100, 'legacy', now=1000).update_id, 1)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT schema_version FROM telegram_pattern_inbox_meta').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT value FROM business').fetchone()[0], 'preserve')

    def test_version_one_migration_rolls_back_column_and_version_when_metadata_write_fails(self):
        path = Path(self.temporary.name) / 'rollback-v1.sqlite'
        payload = _legacy_v1_database(path)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(
                "CREATE TRIGGER fail_migration BEFORE UPDATE ON telegram_pattern_inbox_meta "
                "BEGIN SELECT RAISE(ABORT,'fixture migration failure'); END"
            )
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'fixture migration failure'):
            SQLiteInbox(path).initialize()
        with closing(sqlite3.connect(path)) as db, db:
            self.assertEqual(db.execute('SELECT schema_version FROM telegram_pattern_inbox_meta').fetchone()[0], 1)
            self.assertNotIn('priority', {row[1] for row in db.execute('PRAGMA table_info(telegram_pattern_inbox)')})
            self.assertEqual(db.execute('SELECT payload_json FROM telegram_pattern_inbox').fetchone()[0], payload)
            db.execute('DROP TRIGGER fail_migration')
        SQLiteInbox(path).initialize()
        self.assertEqual(SQLiteInbox(path).get(100, 1).priority, 0)

    def test_storage_failure_is_not_reported_as_receipt(self):
        with patch.object(self.store, '_connect', side_effect=sqlite3.OperationalError('fixture unavailable')):
            with self.assertRaises(sqlite3.OperationalError):
                self.receive()
        self.assertEqual(sum(self.store.counts(100).values()), 0)

    def test_real_sqlite_lock_timeout_leaves_no_accepted_event(self):
        locked = SQLiteInbox(self.database, timeout=0.01)
        with closing(sqlite3.connect(self.database)) as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    locked.receive(100, 1, {'update_id': 1}, now=100)
            finally:
                blocker.rollback()
        self.assertIsNone(SQLiteInbox(self.database).get(100, 1))
        self.assertEqual(locked.receive(100, 1, {'update_id': 1}, now=101).state, 'pending')

    def test_constructor_rejects_unsafe_or_unbounded_policy(self):
        for options in [
            {'supported_versions': ()},
            {'supported_versions': (1, 1)},
            {'supported_versions': (True,)},
            {'supported_versions': tuple(range(1, 34))},
            {'max_attempts': 0},
            {'max_attempts': 1001},
            {'max_attempts': True},
            {'max_payload_bytes': 127},
            {'max_payload_bytes': 8 * 1024 * 1024 + 1},
            {'timeout': 0},
            {'timeout': float('nan')},
            {'timeout': 10**1000},
        ]:
            with self.subTest(options=list(options)), self.assertRaises(ValidationFailure):
                SQLiteInbox(self.database, **options)
        for database in ('', ':memory:', None):
            with self.subTest(database=str(database)), self.assertRaises(ValidationFailure):
                SQLiteInbox(database)

    @integration
    def test_simultaneous_process_receipts_and_claims_are_serialized(self):
        context = multiprocessing.get_context('spawn')
        for target in (_receive_worker, _claim_worker):
            gate, results = context.Event(), context.Queue()
            processes = [context.Process(target=target, args=(str(self.database), gate, results)) for _ in range(2)]
            try:
                for process in processes:
                    process.start()
                gate.set()
                output = [results.get(timeout=20) for _ in processes]
                for process in processes:
                    process.join(20)
                    self.assertEqual(process.exitcode, 0)
                if target == _receive_worker:
                    self.assertEqual(sorted(output), [(False, 'pending'), (True, 'pending')])
                else:
                    self.assertEqual(sum(value is None for value in output), 1)
                    self.assertEqual(self.store.get(100, 1).attempts, 1)
            finally:
                for process in processes:
                    if process.is_alive():
                        process.terminate()
                    process.join(10)
                results.close()

    @integration
    def test_crash_after_business_commit_replays_same_operation_before_completion(self):
        self.receive()
        once = SQLiteOnce(self.database)
        once.initialize()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE business_counter(value INTEGER)')
            db.execute('INSERT INTO business_counter VALUES (0)')
        context = multiprocessing.get_context('spawn')
        process = context.Process(target=_effect_then_crash, args=(str(self.database),))
        process.start()
        process.join(20)
        if process.is_alive():
            process.terminate()
            process.join(10)
            self.fail('Crash worker did not finish')
        self.assertEqual(process.exitcode, 23)
        restarted = SQLiteInbox(self.database)
        self.assertEqual(restarted.get(100, 1).state, 'processing')
        self.assertIsNone(restarted.claim(100, 'replacement', now=109))
        claim = restarted.claim(100, 'replacement', now=110)

        def effect(db):
            db.execute('UPDATE business_counter SET value=value+1')
            return {'applied': True}

        result = once.run('bot:100', 'update:1', claim.payload, effect)
        self.assertTrue(result.replayed)
        restarted.complete(claim, now=111)
        with closing(sqlite3.connect(self.database)) as db, db:
            self.assertEqual(db.execute('SELECT value FROM business_counter').fetchone()[0], 1)
        self.assertEqual(restarted.counts(100)['done'], 1)


if __name__ == '__main__':
    unittest.main()
