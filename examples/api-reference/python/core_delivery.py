"""SDK-free receipt, replay, quarantine and fenced processing; no Telegram HTTP."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from telegram_patterns import (
    InboxClaim,
    InboxConflict,
    InboxLeaseLost,
    InboxReason,
    InboxReceipt,
    InboxRecord,
    InboxState,
    SQLiteInbox,
    WebhookCode,
    WebhookReceiver,
    WebhookResponse,
    create_aiohttp_webhook_app,
)

with TemporaryDirectory() as directory:
    inbox = SQLiteInbox(Path(directory) / 'delivery.sqlite')
    inbox.initialize()
    receiver = WebhookReceiver(inbox, bot_id=100, secret_token='fixture_only')
    response: WebhookResponse = receiver.receive(b'{"update_id":1,"message":{}}', 'fixture_only')
    code: WebhookCode = response.code
    assert code == 'accepted' and response.accepted
    receipt: InboxReceipt = inbox.receive(100, 1, {'update_id': 1, 'message': {}})
    assert receipt.duplicate
    try:
        inbox.receive(100, 1, {'update_id': 1, 'message': {'text': 'different'}})
    except InboxConflict:
        pass
    else:
        raise AssertionError('Changed payload accepted')
    first = inbox.claim(100, 'worker-one', lease_seconds=1, now=10)
    # received_at defaults to real UTC, so this synthetic clock is intentionally too early.
    assert first is None
    fresh = inbox.receive(100, 2, {'update_id': 2, 'message': {}}, now=10)
    assert fresh.state == 'pending'
    claimed = inbox.claim(100, 'worker-one', lease_seconds=1, now=10)
    assert isinstance(claimed, InboxClaim)
    replacement = inbox.claim(100, 'worker-two', now=11)
    assert replacement is not None and replacement.attempt == 2
    try:
        inbox.complete(claimed, now=11)
    except InboxLeaseLost:
        pass
    else:
        raise AssertionError('Expired worker completed the event')
    # A real worker would SDK-decode; this minimal fixture models a controlled decode failure.
    reason: InboxReason = 'decode-failed'
    inbox.quarantine(replacement, reason=reason, now=11)
    record = inbox.get(100, 2)
    assert isinstance(record, InboxRecord)
    state: InboxState = record.state
    assert state == 'quarantined' and record.reason == reason
    # An explicit lane can serve urgent work while the normal lane stays pending.
    inbox.receive(100, 3, {'update_id': 3, 'message': {}}, now=12)
    urgent = inbox.receive(100, 4, {'update_id': 4, 'pre_checkout_query': {}}, priority=1, now=13)
    assert urgent.priority == 1
    duplicate = inbox.receive(100, 4, {'update_id': 4, 'pre_checkout_query': {}}, priority=0, now=900)
    stored = inbox.get(100, 4)
    assert duplicate.duplicate and duplicate.priority == 1
    assert stored is not None and stored.priority == 1 and stored.received_at == 13
    urgent_claim = inbox.claim(100, 'urgent-worker', priorities=(1,), now=14)
    assert urgent_claim is not None and urgent_claim.update_id == 4
    inbox.complete(urgent_claim, now=14)
    normal_claim = inbox.claim(100, 'normal-worker', priorities=(0,), now=14)
    assert normal_claim is not None and normal_claim.update_id == 3
    inbox.complete(normal_claim, now=14)
    # Default selection remains FIFO across all lanes, without numeric priority sorting.
    inbox.receive(100, 5, {'update_id': 5, 'message': {}}, now=15)
    inbox.receive(100, 6, {'update_id': 6, 'pre_checkout_query': {}}, priority=255, now=16)
    fifo = inbox.claim(100, 'default-worker', now=17)
    assert fifo is not None and fifo.update_id == 5
    inbox.complete(fifo, now=17)
    # Optional adapter is importable without aiohttp; actual HTTP belongs to separate extra consumer tests.
    assert callable(create_aiohttp_webhook_app)
print(json.dumps({'passed': True, 'case': 'core_delivery', 'network': False}))
