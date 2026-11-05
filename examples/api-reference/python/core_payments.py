"""Exact money and trusted local receipt fixture; not a real provider authentication protocol."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from telegram_patterns import (
    MAX_MINOR_UNITS, AccessDecision, Money, PaymentBinding, PaymentCheck, PaymentClaim,
    PaymentConflict, PaymentKind, PaymentLeaseLost, PaymentOperation, PaymentOrder,
    PaymentReceipt, PaymentRoute, PaymentState, PaymentVerifier, ProviderEvent,
    ProviderEventKind, SQLitePaymentLedger,
)

assert Money(MAX_MINOR_UNITS, 'USD', 2).minor_units == MAX_MINOR_UNITS
price = Money.from_decimal('10.00', 'USD', 2)
assert price.to_decimal() == '10.00' and (price - Money(1, 'USD', 2)).minor_units == 999
route: PaymentRoute = 'external'
binding = PaymentBinding('fixture-merchant', 100, 200, 'order-one', 'fictional-provider', price, route=route)
with TemporaryDirectory() as directory:
    ledger = SQLitePaymentLedger(Path(directory) / 'payments.sqlite')
    ledger.initialize()
    operation: PaymentOperation = ledger.create_order(binding, 'invoice-one', now=100)
    kind: PaymentKind = operation.kind
    state: PaymentState = operation.state
    assert kind == 'invoice' and state == 'pending'

    def current_access(db: Any, current: PaymentOperation, replayed: bool) -> bool:
        # A production check reads current operator/object ACL in this writer transaction.
        assert db.in_transaction and type(replayed) is bool
        return current.binding == binding and current.actor_id == (200 if current.kind == 'invoice' else 900)

    check: PaymentCheck = current_access
    claim: PaymentClaim = ledger.start_operation(binding, 'invoice-one', 'worker', check=check, now=100)
    assert claim.operation_id == 'invoice-one'
    events = {
        'invoice': ProviderEvent(binding, 'invoice-event', 'invoice-created', 'created', 'fixture-invoice-proof',
                                 operation_id='invoice-one', provider_ref='invoice-native'),
        'paid': ProviderEvent(binding, 'paid-event', 'paid', 'captured', 'fixture-paid-proof',
                              charge_id='charge-native', amount=price, paid_at=102),
        'refund': ProviderEvent(binding, 'refund-event', 'refunded', 'refunded', 'fixture-refund-proof',
                                operation_id='refund-one', charge_id='charge-native',
                                refund_id='refund-native', amount=price),
    }

    def trusted_fixture(raw: Any) -> ProviderEvent:
        # Only this closed local fixture maps labels to receipts. Production must verify provider auth/status.
        if not isinstance(raw, str) or raw not in events:
            raise ValueError('Unknown local fixture')
        return events[raw]

    verify: PaymentVerifier = trusted_fixture
    invoice: PaymentReceipt = ledger.apply_event('invoice', verify=verify, now=101)
    assert invoice.kind == 'invoice-created' and not ledger.has_access(binding, now=101).active
    receipt: PaymentReceipt = ledger.apply_event('paid', verify=verify, now=102)
    event_kind: ProviderEventKind = receipt.kind
    assert event_kind == 'paid'
    assert ledger.apply_event('paid', verify=verify, now=102).duplicate
    order: PaymentOrder = ledger.get_order(binding)
    access: AccessDecision = ledger.has_access(binding, now=102)
    assert order.confirmed_charges == 1 and access.active
    try:
        ledger.create_order(replace(binding, amount=Money(1001, 'USD', 2)), 'invoice-one', now=102)
    except PaymentConflict:
        pass
    else:
        raise AssertionError('Changed server binding accepted')
    ledger.request_refund(binding, 'charge-native', 'refund-one', price, 900, check=check, now=103)
    ledger.start_operation(binding, 'refund-one', 'worker', check=check, lease_seconds=1, now=103)
    # A lost sender may already have refunded remotely. Expiry alone never permits another refund.
    ledger.recover_expired(binding, now=104)
    unknown = ledger.get_operation(binding, 'refund-one')
    assert unknown.state == 'unknown'
    try:
        ledger.start_operation(binding, 'refund-one', 'other-worker', check=check, now=104)
    except PaymentLeaseLost:
        pass
    else:
        raise AssertionError('Unknown refund sent again')
    ledger.reconcile_operation('refund', verify=verify, expected_revision=unknown.revision, now=104)
    assert not ledger.has_access(binding, now=104).active
    assert ledger.get_order(binding).fully_refunded_charges == 1
print(json.dumps({'passed': True, 'case': 'core_payments', 'network': False}))
