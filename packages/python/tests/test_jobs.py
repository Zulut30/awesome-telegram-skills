"""Real durable job state, dispatch boundaries, worker races and crash ambiguity."""

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

from telegram_patterns.errors import UnsupportedCapability, ValidationFailure, safe_error_report
from telegram_patterns.jobs import JobConflict, JobLeaseLost, JobQueueFull, SQLiteJobQueue


def _race_dispatch(database, claim_gate, start_gate, results):
    queue = SQLiteJobQueue(database)
    claim_gate.wait(10)
    claim = queue.claim(100, 'worker:' + str(os.getpid()), now=100)
    results.put(('claim', None if claim is None else claim.job_id))
    start_gate.wait(10)
    if claim is not None:
        results.put(('start', queue.start(claim, now=100).state))


def _crash_worker(database, started):
    queue = SQLiteJobQueue(database)
    claim = queue.claim(100, 'crash-worker', lease_seconds=10, now=100)
    if claim is None:
        raise AssertionError('Expected a claimed job')
    if started:
        if queue.start(claim, now=100).state != 'sending':
            raise AssertionError('Expected dispatch admission')
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('INSERT INTO remote_effect VALUES (1)')
    os._exit(22 if started else 21)


def _race_reconcile(database, revision, gate, results):
    queue = SQLiteJobQueue(database)
    gate.wait(10)
    try:
        queue.reconcile(
            100, 'job:1', expected_revision=revision, evidence_ref='review:' + str(os.getpid()), outcome='sent'
        )
    except JobConflict:
        results.put('conflict')
    else:
        results.put('sent')


class JobsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='jobs-test-')
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'jobs.sqlite'
        self.queue = SQLiteJobQueue(self.database)
        self.queue.initialize()
        self.queue.set_recipient(100, 200, subscribed=True, reachable=True)

    def schedule(self, job_id='job:1', recipient=200, **kwargs):
        return self.queue.schedule(
            100, job_id, recipient, {'text': 'PRIVATE_CANARY'}, due_at=100, deadline_at=1000, now=90, **kwargs
        )

    def sending(self, **kwargs):
        self.schedule(**kwargs)
        claim = self.queue.claim(100, 'worker', lease_seconds=10, now=100)
        self.assertEqual(self.queue.start(claim, now=100).state, 'sending')
        return claim

    def test_intent_is_durable_deduplicated_scoped_and_conflicting_changes_rejected(self):
        initial = self.schedule()
        self.assertEqual((initial.state, initial.attempts, initial.revision), ('scheduled', 0, 1))
        reopened = SQLiteJobQueue(self.database)
        duplicate = reopened.schedule(
            100, 'job:1', 200, {'text': 'PRIVATE_CANARY'}, due_at=100, deadline_at=1000, now=2000
        )
        self.assertEqual(duplicate, initial)
        for payload, recipient, due, deadline, attempts in [
            ({'text': 'changed'}, 200, 100, 1000, 3),
            ({'text': 'PRIVATE_CANARY'}, 201, 100, 1000, 3),
            ({'text': 'PRIVATE_CANARY'}, 200, 101, 1000, 3),
            ({'text': 'PRIVATE_CANARY'}, 200, 100, 1001, 3),
            ({'text': 'PRIVATE_CANARY'}, 200, 100, 1000, 4),
        ]:
            with self.assertRaises(JobConflict):
                reopened.schedule(
                    100, 'job:1', recipient, payload, due_at=due, deadline_at=deadline, max_attempts=attempts, now=90
                )
        reopened.schedule(101, 'job:1', 200, {}, due_at=100, deadline_at=1000, now=90)
        self.assertIsNone(reopened.claim(101, 'worker', now=100))
        self.assertEqual(reopened.get(101, 'job:1').reason, 'missing-recipient')
        self.assertNotIn('PRIVATE_CANARY', repr(initial))
        decoded = initial.payload
        decoded['text'] = 'changed'
        self.assertEqual(initial.payload['text'], 'PRIVATE_CANARY')

    def test_due_time_and_deadline_boundaries_survive_reopen(self):
        self.schedule()
        self.assertIsNone(self.queue.claim(100, 'worker', now=99.999))
        claim = self.queue.claim(100, 'worker', lease_seconds=3600, now=100)
        result = SQLiteJobQueue(self.database).start(claim, now=1000)
        self.assertEqual((result.state, result.reason), ('expired', 'deadline'))
        self.assertEqual(self.queue.counts(100)['expired'], 1)
        with self.assertRaises(JobLeaseLost):
            self.queue.finish(claim, outcome='sent', now=1000)

    def test_policy_missing_optout_and_unreachable_suppress_before_new_claim(self):
        for index, policy in enumerate([None, (False, True), (True, False)], start=1):
            recipient = 200 + index
            if policy is not None:
                self.queue.set_recipient(100, recipient, subscribed=policy[0], reachable=policy[1])
            self.schedule('job:' + str(index), recipient)
        self.assertIsNone(self.queue.claim(100, 'worker', now=100))
        self.assertEqual(
            [self.queue.get(100, 'job:' + str(index)).reason for index in range(1, 4)],
            ['missing-recipient', 'opted-out', 'recipient-unreachable'],
        )
        self.queue.set_recipient(100, 202, subscribed=True, reachable=True)
        self.assertIsNone(self.queue.claim(100, 'worker', now=101))

    def test_optout_after_claim_fences_start_and_does_not_reactivate_on_optin(self):
        self.schedule()
        claim = self.queue.claim(100, 'worker', now=100)
        self.queue.set_recipient(100, 200, subscribed=False, reachable=True)
        with self.assertRaises(JobLeaseLost):
            self.queue.start(claim, now=101)
        self.queue.set_recipient(100, 200, subscribed=True, reachable=True)
        self.assertEqual(self.queue.get(100, 'job:1').state, 'skipped')
        self.assertIsNone(self.queue.claim(100, 'worker', now=101))

    def test_start_rechecks_current_policy_in_same_dispatch_transaction(self):
        self.schedule()
        claim = self.queue.claim(100, 'worker', now=100)
        # Model a host-owned policy update without the convenience method's eager suppression.
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('UPDATE telegram_pattern_job_recipients SET subscribed=0')
        result = self.queue.start(claim, now=101)
        self.assertEqual((result.state, result.reason), ('skipped', 'opted-out'))

    def test_cancellation_before_start_is_terminal_and_idempotent(self):
        self.schedule()
        claim = self.queue.claim(100, 'worker', now=100)
        record = self.queue.cancel(100, 'job:1')
        self.assertEqual((record.state, record.cancel_requested), ('cancelled', True))
        self.assertEqual(record, self.queue.cancel(100, 'job:1'))
        with self.assertRaises(JobLeaseLost):
            self.queue.start(claim, now=101)
        self.assertIsNone(self.queue.claim(100, 'worker', now=102))

    def test_cancel_after_start_does_not_claim_remote_cancellation(self):
        claim = self.sending()
        result = self.queue.cancel(100, 'job:1')
        self.assertEqual((result.state, result.cancel_requested), ('sending', True))
        sent = self.queue.finish(claim, outcome='sent', message_id=11, now=101)
        self.assertEqual((sent.state, sent.message_id, sent.cancel_requested), ('sent', 11, True))
        self.assertEqual(self.queue.cancel(100, 'job:1'), sent)

    def test_optout_after_start_preserves_success_and_stops_other_jobs(self):
        claim = self.sending()
        self.schedule('job:2')
        self.queue.set_recipient(100, 200, subscribed=False, reachable=True)
        self.assertTrue(self.queue.get(100, 'job:1').cancel_requested)
        self.assertEqual(self.queue.finish(claim, outcome='sent', message_id=12, now=101).state, 'sent')
        self.assertIsNone(self.queue.claim(100, 'worker', now=200))
        self.assertEqual(self.queue.get(100, 'job:2').state, 'skipped')

    def test_cancelled_started_attempt_with_confirmed_flood_has_no_effect_or_retry(self):
        claim = self.sending()
        self.queue.cancel(100, 'job:1')
        result = self.queue.finish(claim, outcome='flood', retry_after=5, now=101)
        self.assertEqual((result.state, result.reason, result.cancel_requested), ('cancelled', 'cancelled', True))
        self.assertIsNone(self.queue.claim(100, 'worker', now=200))

    def test_permanent_refusal_stops_recipient_and_future_jobs(self):
        claim = self.sending()
        self.schedule('job:2')
        failed = self.queue.finish(claim, outcome='permanent-failure', now=101)
        self.assertEqual((failed.state, failed.reason), ('failed', 'recipient-unreachable'))
        self.schedule('job:3')
        self.assertIsNone(self.queue.claim(100, 'worker', now=200))
        self.assertEqual(self.queue.get(100, 'job:2').reason, 'recipient-unreachable')
        self.assertEqual(self.queue.get(100, 'job:3').reason, 'recipient-unreachable')

    def test_flood_wait_is_durable_bot_wide_and_attempts_are_bounded(self):
        claim = self.sending(max_attempts=2)
        self.queue.set_recipient(100, 201, subscribed=True, reachable=True)
        self.schedule('job:2', 201)
        result = self.queue.finish(claim, outcome='flood', retry_after=10, now=101)
        self.assertEqual((result.state, result.reason, result.due_at), ('scheduled', 'flood-rejected', 111))
        reopened = SQLiteJobQueue(self.database, bot_interval=0.001, recipient_interval=0.001)
        self.assertIsNone(reopened.claim(100, 'other', now=110.999))
        self.queue.cancel(100, 'job:2')
        again = reopened.claim(100, 'other', now=111)
        self.assertEqual(again.attempt, 2)
        self.assertEqual(reopened.start(again, now=111).state, 'sending')
        terminal = reopened.finish(again, outcome='flood', retry_after=1, now=112)
        self.assertEqual((terminal.state, terminal.reason), ('failed', 'attempts-exhausted'))
        self.assertIsNone(reopened.claim(100, 'other', now=200))

    def test_flood_beyond_deadline_or_wait_budget_has_no_automatic_retry(self):
        claim = self.sending()
        expired = self.queue.finish(claim, outcome='flood', retry_after=899, now=101)
        self.assertEqual((expired.state, expired.reason), ('expired', 'deadline'))
        self.queue.set_recipient(101, 200, subscribed=True, reachable=True)
        self.queue.schedule(101, 'large-wait', 200, {}, due_at=100, deadline_at=200000, now=90)
        claim = self.queue.claim(101, 'worker', now=100)
        self.queue.start(claim, now=100)
        failed = self.queue.finish(claim, outcome='flood', retry_after=86401, now=101)
        self.assertEqual((failed.state, failed.reason), ('failed', 'retry-window-exceeded'))
        self.queue.schedule(101, 'other', 200, {}, due_at=100, deadline_at=200000, now=102)
        self.assertIsNone(self.queue.claim(101, 'worker', now=86501))

    def test_recipient_and_bot_pacing_are_persisted_and_independent(self):
        queue = SQLiteJobQueue(self.database, bot_interval=1, recipient_interval=5)
        queue.schedule(100, 'job:1', 200, {}, due_at=100, deadline_at=1000, now=90)
        queue.schedule(100, 'job:2', 200, {}, due_at=100, deadline_at=1000, now=90)
        queue.set_recipient(100, 201, subscribed=True, reachable=True)
        queue.schedule(100, 'job:3', 201, {}, due_at=100, deadline_at=1000, now=90)
        first = queue.claim(100, 'worker', now=100)
        queue.start(first, now=100)
        queue.finish(first, outcome='sent', message_id=1, now=100)
        reopened = SQLiteJobQueue(self.database, bot_interval=0.001, recipient_interval=0.001)
        self.assertIsNone(reopened.claim(100, 'worker', now=100.5))
        other = reopened.claim(100, 'worker', now=101)
        self.assertEqual(other.recipient_id, 201)
        reopened.start(other, now=101)
        reopened.finish(other, outcome='sent', message_id=2, now=101)
        self.assertIsNone(reopened.claim(100, 'worker', now=104.999))
        self.assertEqual(reopened.claim(100, 'worker', now=105).recipient_id, 200)

    def test_sending_expiry_and_unknown_feedback_never_requeue(self):
        claim = self.sending()
        self.queue.cancel(100, 'job:1')
        self.assertEqual(self.queue.recover(100, now=110), 1)
        unknown = self.queue.get(100, 'job:1')
        self.assertEqual(
            (unknown.state, unknown.reason, unknown.cancel_requested), ('unknown', 'send-outcome-unknown', True)
        )
        for action in [
            lambda: self.queue.finish(claim, outcome='sent', message_id=1, now=110),
            lambda: self.queue.renew(claim, now=110),
        ]:
            with self.assertRaises(JobLeaseLost):
                action()
        self.assertIsNone(self.queue.claim(100, 'other', now=10000))
        self.assertEqual(self.queue.get(100, 'job:1').state, 'unknown')

    def test_claimed_expiry_requeues_only_before_dispatch_and_budget_survives_restart(self):
        self.schedule(max_attempts=2)
        first = self.queue.claim(100, 'old', lease_seconds=10, now=100)
        self.assertIsNone(self.queue.claim(100, 'new', now=109.999))
        second = SQLiteJobQueue(self.database).claim(100, 'new', lease_seconds=10, now=110)
        self.assertEqual(second.attempt, 2)
        self.assertNotEqual(first.token, second.token)
        for forged in [
            first,
            replace(second, token='0' * 32),
            replace(second, worker_id='forged'),
            replace(second, attempt=1),
        ]:
            with self.assertRaises(JobLeaseLost):
                self.queue.start(forged, now=111)
        self.assertIsNone(self.queue.claim(100, 'third', now=120))
        result = self.queue.get(100, 'job:1')
        self.assertEqual((result.state, result.reason, result.attempts), ('failed', 'attempts-exhausted', 2))

    def test_lost_delivery_lease_reports_unknown_reconcile_instead_of_rejected(self):
        claim = self.sending()
        with self.assertRaises(JobLeaseLost) as raised:
            self.queue.finish(claim, outcome='sent', message_id=1, now=110)
        report = safe_error_report(raised.exception, operation='write')
        self.assertEqual((report.code, report.outcome, report.recovery), ('unknown-outcome', 'unknown', 'reconcile'))
        for error in [JobConflict('fixture'), JobQueueFull('fixture')]:
            self.assertEqual(safe_error_report(error, operation='write').outcome, 'rejected')

    def test_live_renewal_does_not_shorten_lease_and_finish_requires_start(self):
        self.schedule()
        claim = self.queue.claim(100, 'worker', lease_seconds=10, now=100)
        with self.assertRaises(JobLeaseLost):
            self.queue.finish(claim, outcome='sent', now=101)
        renewed = self.queue.renew(claim, lease_seconds=10, now=105)
        self.assertEqual(renewed.lease_until, 115)
        self.assertEqual(self.queue.renew(claim, lease_seconds=1, now=106).lease_until, 115)
        self.queue.start(renewed, now=114)
        self.assertEqual(self.queue.finish(renewed, outcome='unknown', now=114).state, 'unknown')
        self.assertIsNone(self.queue.claim(100, 'other', now=200))
        self.assertNotIn(claim.token, repr(claim))
        self.assertNotIn('PRIVATE_CANARY', repr(claim))

    def test_reconciliation_uses_revision_and_evidence_without_resending(self):
        claim = self.sending()
        unknown = self.queue.finish(claim, outcome='unknown', now=101)
        changed = self.queue.cancel(100, 'job:1')
        with self.assertRaises(JobConflict):
            self.queue.reconcile(
                100, 'job:1', expected_revision=unknown.revision, evidence_ref='review:1', outcome='sent'
            )
        reviewed = self.queue.reconcile(
            100, 'job:1', expected_revision=changed.revision, evidence_ref='review:2', outcome='failed'
        )
        self.assertEqual(
            (reviewed.state, reviewed.reason, reviewed.evidence_ref), ('failed', 'reconciled-failed', 'review:2')
        )
        self.assertIsNone(self.queue.claim(100, 'worker', now=200))
        with self.assertRaises(JobConflict):
            self.queue.reconcile(
                100, 'job:1', expected_revision=changed.revision, evidence_ref='review:3', outcome='sent'
            )

    def test_active_capacity_persists_and_unknown_occupies_capacity_until_review(self):
        queue = SQLiteJobQueue(self.database, max_active_jobs=1)
        queue.schedule(100, 'job:1', 200, {}, due_at=100, deadline_at=1000, now=90)
        reopened = SQLiteJobQueue(self.database, max_active_jobs=1000)
        with self.assertRaises(JobQueueFull):
            reopened.schedule(100, 'job:2', 200, {}, due_at=100, deadline_at=1000, now=90)
        claim = queue.claim(100, 'worker', now=100)
        queue.start(claim, now=100)
        unknown = queue.finish(claim, outcome='unknown', now=101)
        with self.assertRaises(JobQueueFull):
            reopened.schedule(100, 'job:2', 200, {}, due_at=100, deadline_at=1000, now=102)
        queue.reconcile(100, 'job:1', expected_revision=unknown.revision, evidence_ref='review:1', outcome='sent')
        self.assertEqual(
            reopened.schedule(100, 'job:2', 200, {}, due_at=100, deadline_at=1000, now=102).state, 'scheduled'
        )

    def test_invalid_inputs_are_rejected_without_scheduling_or_raw_diagnostics(self):
        calls = [
            lambda: self.queue.schedule(True, 'job:1', 200, {}, due_at=100, deadline_at=1000),
            lambda: self.queue.schedule(2**53, 'job:1', 200, {}, due_at=100, deadline_at=1000),
            lambda: self.queue.schedule(100, 'job:1', -(2**53), {}, due_at=100, deadline_at=1000),
            lambda: self.schedule('../PRIVATE_CANARY'),
            lambda: self.schedule(max_attempts=True),
            lambda: self.schedule(max_attempts=101),
            lambda: self.queue.schedule(100, 'job:1', 200, {1: 'bad'}, due_at=100, deadline_at=1000, now=90),
            lambda: self.queue.schedule(100, 'job:1', 200, {'bad': '\ud800'}, due_at=100, deadline_at=1000, now=90),
            lambda: self.queue.schedule(100, 'job:1', 200, {'bad': float('nan')}, due_at=100, deadline_at=1000, now=90),
            lambda: self.queue.schedule(100, 'job:1', 200, {}, due_at=100, deadline_at=100, now=90),
            lambda: self.queue.schedule(100, 'job:1', 200, {}, due_at=100, deadline_at=1000, now=1000),
            lambda: self.queue.set_recipient(100, 200, subscribed=1, reachable=True),
            lambda: self.queue.claim(100, 'worker', lease_seconds=True, now=100),
            lambda: self.queue.claim(100, 'worker', lease_seconds=1e-30, now=100),
            lambda: self.queue.claim(100, 'worker', lease_seconds=3601, now=100),
            lambda: self.queue.claim(100, 'PRIVATE_CANARY\ud800', now=100),
        ]
        for case, call in enumerate(calls):
            with self.subTest(case=case), self.assertRaises(ValidationFailure) as raised:
                call()
            self.assertNotIn('PRIVATE_CANARY', str(raised.exception))
        self.assertEqual(sum(self.queue.counts(100).values()), 0)
        self.queue.set_recipient(100, -(2**53 - 1), subscribed=True, reachable=True)
        self.schedule('job:valid', -(2**53 - 1))

    def test_invalid_feedback_and_reconciliation_leave_sending_intact(self):
        claim = self.sending()
        calls = [
            lambda: self.queue.finish(claim, outcome='flood', retry_after=0, now=101),
            lambda: self.queue.finish(claim, outcome='flood', retry_after=True, now=101),
            lambda: self.queue.finish(claim, outcome='flood', retry_after=2**31, now=101),
            lambda: self.queue.finish(claim, outcome='unknown', retry_after=1, now=101),
            lambda: self.queue.finish(claim, outcome='unknown', message_id=1, now=101),
            lambda: self.queue.finish(claim, outcome='sent', message_id=True, now=101),
            lambda: self.queue.finish(claim, outcome='PRIVATE_CANARY', now=101),
            lambda: self.queue.reconcile(100, 'job:1', expected_revision=True, evidence_ref='review:1', outcome='sent'),
            lambda: self.queue.reconcile(
                100, 'job:1', expected_revision=1, evidence_ref='../PRIVATE_CANARY', outcome='sent'
            ),
        ]
        for case, call in enumerate(calls):
            with self.subTest(case=case), self.assertRaises(ValidationFailure):
                call()
        self.assertEqual(self.queue.get(100, 'job:1').state, 'sending')

    def test_schema_future_version_and_real_lock_failure_preserve_data(self):
        self.schedule()
        self.queue.initialize()
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    SQLiteJobQueue(self.database, timeout=0.01).cancel(100, 'job:1')
            finally:
                db.rollback()
        self.assertEqual(self.queue.get(100, 'job:1').state, 'scheduled')
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('UPDATE telegram_pattern_jobs_meta SET schema_version=2')
        with self.assertRaises(UnsupportedCapability):
            self.queue.initialize()
        self.assertEqual(self.queue.get(100, 'job:1').payload['text'], 'PRIVATE_CANARY')

    def test_canonical_utf8_payload_limit_is_enforced_without_partial_intent(self):
        queue = SQLiteJobQueue(self.database, max_payload_bytes=128)
        payload = {'text': 'é' * 58 + 'x'}
        record = queue.schedule(100, 'fits', 200, payload, due_at=100, deadline_at=1000, now=90)
        self.assertEqual(len(record.payload_json.encode('utf-8')), 128)
        payload['text'] += 'x'
        with self.assertRaises(ValidationFailure):
            queue.schedule(100, 'too-large', 200, payload, due_at=100, deadline_at=1000, now=90)
        self.assertIsNone(queue.get(100, 'too-large'))

    def test_constructor_rejects_unbounded_or_unsafe_policy(self):
        for options in [
            {'bot_interval': 0},
            {'recipient_interval': 0.0001},
            {'timeout': 301},
            {'timeout': float('inf')},
            {'bot_interval': 10**1000},
            {'max_active_jobs': 0},
            {'max_active_jobs': True},
            {'max_active_jobs': 100001},
            {'max_payload_bytes': 127},
        ]:
            with self.subTest(options=list(options)), self.assertRaises(ValidationFailure):
                SQLiteJobQueue(self.database, **options)
        for database in ('', ':memory:', None):
            with self.assertRaises(ValidationFailure):
                SQLiteJobQueue(database)

    @integration
    def test_competing_processes_can_only_reserve_one_dispatch_interval(self):
        self.schedule('job:1')
        self.schedule('job:2')
        context = multiprocessing.get_context('spawn')
        claim_gate, start_gate, results = context.Event(), context.Event(), context.Queue()
        processes = [
            context.Process(target=_race_dispatch, args=(str(self.database), claim_gate, start_gate, results))
            for _ in range(2)
        ]
        try:
            for process in processes:
                process.start()
            claim_gate.set()
            claims = [results.get(timeout=20) for _ in processes]
            self.assertEqual({value[1] for value in claims}, {'job:1', 'job:2'})
            start_gate.set()
            starts = [results.get(timeout=20)[1] for _ in processes]
            self.assertEqual(sorted(starts), ['scheduled', 'sending'])
            for process in processes:
                process.join(20)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(sorted(self.queue.get(100, job).attempts for job in ['job:1', 'job:2']), [0, 1])
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                process.join(10)
            results.close()

    @integration
    def test_crash_after_dispatch_records_unknown_and_never_repeats_remote_effect(self):
        self.schedule()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE remote_effect(value INTEGER)')
        context = multiprocessing.get_context('spawn')
        process = context.Process(target=_crash_worker, args=(str(self.database), True))
        process.start()
        process.join(20)
        if process.is_alive():
            process.terminate()
            process.join(10)
            self.fail('Crash worker did not finish')
        self.assertEqual(process.exitcode, 22)
        reopened = SQLiteJobQueue(self.database)
        self.assertEqual(reopened.get(100, 'job:1').state, 'sending')
        self.assertIsNone(reopened.claim(100, 'replacement', now=110))
        self.assertEqual(reopened.get(100, 'job:1').state, 'unknown')
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM remote_effect').fetchone()[0], 1)

    @integration
    def test_crash_before_dispatch_recovers_fenced_claim_without_losing_job(self):
        self.schedule()
        context = multiprocessing.get_context('spawn')
        process = context.Process(target=_crash_worker, args=(str(self.database), False))
        process.start()
        process.join(20)
        if process.is_alive():
            process.terminate()
            process.join(10)
            self.fail('Crash worker did not finish')
        self.assertEqual(process.exitcode, 21)
        reopened = SQLiteJobQueue(self.database)
        self.assertIsNone(reopened.claim(100, 'replacement', now=109.999))
        claim = reopened.claim(100, 'replacement', now=110)
        self.assertEqual((claim.job_id, claim.attempt), ('job:1', 2))
        self.assertEqual(reopened.start(claim, now=110).state, 'sending')

    @integration
    def test_reconciliation_race_cannot_overwrite_other_review(self):
        claim = self.sending()
        unknown = self.queue.finish(claim, outcome='unknown', now=101)
        context = multiprocessing.get_context('spawn')
        gate, results = context.Event(), context.Queue()
        processes = [
            context.Process(target=_race_reconcile, args=(str(self.database), unknown.revision, gate, results))
            for _ in range(2)
        ]
        try:
            for process in processes:
                process.start()
            gate.set()
            self.assertEqual(sorted(results.get(timeout=20) for _ in processes), ['conflict', 'sent'])
            for process in processes:
                process.join(20)
                self.assertEqual(process.exitcode, 0)
            reviewed = self.queue.get(100, 'job:1')
            self.assertEqual((reviewed.state, reviewed.revision), ('sent', unknown.revision + 1))
            self.assertTrue(reviewed.evidence_ref.startswith('review:'))
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                process.join(10)
            results.close()


if __name__ == '__main__':
    unittest.main()
