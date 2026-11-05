"""Business + intent commit together; an expired sending lease never authorizes a new send."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from telegram_patterns import (
    OutboxClaim, OutboxConflict, OutboxLeaseLost, OutboxReceipt, OutboxRecord,
    OutboxResolution, OutboxState, SQLiteOutbox,
)

with TemporaryDirectory() as directory:
    path = Path(directory) / 'business.sqlite'
    outbox = SQLiteOutbox(path)
    outbox.initialize()
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE orders(id TEXT PRIMARY KEY)')
        db.execute('INSERT INTO orders VALUES (?)', ('server-intent',))
        receipt: OutboxReceipt = outbox.enqueue(db, 'bot:100', 'server-intent', {'order': 'server-intent'}, now=10)
    assert not receipt.duplicate and receipt.state == 'pending'
    claimed = outbox.claim('bot:100', 'worker', lease_seconds=1, now=10)
    assert isinstance(claimed, OutboxClaim)
    # A crashed sender may have already delivered. Simulate lease expiry, not proof of absence.
    assert outbox.recover_expired('bot:100', now=11) == 1
    assert outbox.claim('bot:100', 'new-worker', now=11) is None
    try:
        outbox.confirm(claimed, {'message_id': 1}, now=11)
    except OutboxLeaseLost:
        pass
    else:
        raise AssertionError('Expired sender confirmed a receipt')
    observed = outbox.get('bot:100', 'server-intent')
    assert isinstance(observed, OutboxRecord)
    state: OutboxState = observed.state
    assert state == 'unknown'
    resolution: OutboxResolution = 'sent'
    # Host has independently verified this fake provider receipt before reconciliation.
    final = outbox.reconcile('bot:100', 'server-intent', expected_revision=observed.revision,
                             outcome=resolution, evidence_ref='verified-fake-receipt', result={'message_id': 1}, now=11)
    assert final.state == 'sent'
    try:
        outbox.reconcile('bot:100', 'server-intent', expected_revision=observed.revision,
                         outcome='absent', evidence_ref='stale-review', now=11)
    except OutboxConflict:
        pass
    else:
        raise AssertionError('Stale reconciliation changed the completed send')
print(json.dumps({'passed': True, 'case': 'core_outbox', 'network': False}))
