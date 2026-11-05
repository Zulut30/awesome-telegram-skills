"""Persisted recipient consent, pacing, cancellation and no automatic retry of unknown delivery."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from telegram_patterns import (
    JobClaim, JobConflict, JobLeaseLost, JobOutcome, JobQueueFull, JobReason,
    JobRecord, JobState, SQLiteJobQueue,
)

with TemporaryDirectory() as directory:
    queue = SQLiteJobQueue(Path(directory) / 'jobs.sqlite', max_active_jobs=1)
    queue.initialize()
    queue.set_recipient(100, 42, subscribed=True, reachable=True)
    queued: JobRecord = queue.schedule(100, 'reminder-one', 42, {'order': 'one'}, due_at=10, deadline_at=100, now=10)
    state: JobState = queued.state
    assert state == 'scheduled'
    try:
        queue.schedule(100, 'reminder-two', 42, {}, due_at=10, deadline_at=100, now=10)
    except JobQueueFull:
        pass
    else:
        raise AssertionError('Queue capacity was ignored')
    claimed = queue.claim(100, 'worker', now=10)
    assert isinstance(claimed, JobClaim)
    sending = queue.start(claimed, now=10)
    assert sending.state == 'sending'  # Only this state authorizes host transport.
    outcome: JobOutcome = 'unknown'
    unknown = queue.finish(claimed, outcome=outcome, now=11)
    reason: JobReason | None = unknown.reason
    assert unknown.state == 'unknown' and reason == 'send-outcome-unknown'
    assert queue.claim(100, 'other-worker', now=20) is None
    try:
        queue.finish(claimed, outcome='sent', message_id=1, now=12)
    except JobLeaseLost:
        pass
    else:
        raise AssertionError('Old sender changed unknown delivery')
    final = queue.reconcile(100, 'reminder-one', expected_revision=unknown.revision,
                             evidence_ref='verified-fake-receipt', outcome='sent', message_id=1)
    assert final.state == 'sent'
    try:
        queue.reconcile(100, 'reminder-one', expected_revision=unknown.revision,
                         evidence_ref='stale-review', outcome='failed')
    except JobConflict:
        pass
    else:
        raise AssertionError('Stale reconciliation changed delivery')
print(json.dumps({'passed': True, 'case': 'core_jobs', 'network': False}))
