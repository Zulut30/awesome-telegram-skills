"""Local financial proofs; fake authentication is explicitly not any provider's protocol."""

from __future__ import annotations

import hashlib
import hmac
import json
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path

from _support import integration

from telegram_patterns.errors import (
    InvalidType,
    PermissionDenied,
    UnsupportedCapability,
    ValidationFailure,
    safe_error_report,
)
from telegram_patterns.money import Money
from telegram_patterns.payment_ledger import (
    PaymentBinding,
    PaymentConflict,
    PaymentLeaseLost,
    ProviderEvent,
    SQLitePaymentLedger,
)

_FIXTURE_KEY = b'fixture-only-authentication-key'


def _binding(**changes):
    values = dict(
        merchant_id='merchant:test',
        bot_id=100,
        user_id=200,
        order_id='order:1',
        provider='fixture',
        amount=Money(1000, 'USD', 2),
        allow_partial_refunds=True,
    )
    values.update(changes)
    return PaymentBinding(**values)


def _wire(event):
    body = json.dumps(asdict(event), separators=(',', ':'), sort_keys=True).encode()
    return body, hmac.new(_FIXTURE_KEY, body, hashlib.sha256).hexdigest()


def _verify(raw):
    if (
        not isinstance(raw, tuple)
        or len(raw) != 2
        or not isinstance(raw[0], bytes)
        or not isinstance(raw[1], str)
        or not hmac.compare_digest(hmac.new(_FIXTURE_KEY, raw[0], hashlib.sha256).hexdigest(), raw[1])
    ):
        raise PermissionDenied('Fixture provider authentication failed')
    data = json.loads(raw[0])
    binding = data.pop('binding')
    binding['amount'] = Money(**binding['amount'])
    data['binding'] = PaymentBinding(**binding)
    if data['amount'] is not None:
        data['amount'] = Money(**data['amount'])
    return ProviderEvent(**data)


def _allow(_db, _operation, _replayed):
    return True


def _operator(db, operation, _replayed):
    return db.execute('SELECT enabled FROM operators WHERE actor_id=?', (operation.actor_id,)).fetchone()[0] == 1


def _paid(binding, **changes):
    values = dict(
        binding=binding,
        event_id='payment:event:1',
        kind='paid',
        provider_state='captured',
        evidence_ref='verification:1',
        charge_id='charge:1',
        amount=binding.amount,
        paid_at=100,
    )
    values.update(changes)
    return ProviderEvent(**values)


def _refund(binding, **changes):
    values = dict(
        binding=binding,
        event_id='refund:event:1',
        kind='refunded',
        provider_state='refund_succeeded',
        evidence_ref='verification:refund',
        charge_id='charge:1',
        refund_id='refund:native:1',
        amount=Money(300, binding.amount.currency, binding.amount.exponent),
    )
    values.update(changes)
    return ProviderEvent(**values)


def _race_payment(database, binding, raw, gate, results):
    ledger = SQLitePaymentLedger(database)
    gate.wait(10)
    results.put(ledger.apply_event(raw, verify=_verify, now=100).duplicate)


def _race_refund(database, binding, gate, results):
    ledger = SQLitePaymentLedger(database)
    gate.wait(10)
    try:
        ledger.request_refund(
            binding, 'charge:1', 'refund:' + str(os.getpid()), Money(700, 'USD', 2), 900, check=_operator, now=101
        )
    except PaymentConflict:
        results.put('conflict')
    else:
        results.put('reserved')


def _race_start(database, binding, gate, results):
    ledger = SQLitePaymentLedger(database)
    gate.wait(10)
    try:
        ledger.start_operation(binding, 'invoice:1', 'worker:' + str(os.getpid()), check=_allow, now=100)
    except PaymentLeaseLost:
        results.put('blocked')
    else:
        results.put('claimed')


def _race_reconcile(database, _binding_value, proof, gate, results):
    ledger = SQLitePaymentLedger(database)
    raw, revision = proof
    gate.wait(10)
    try:
        ledger.reconcile_operation(raw, verify=_verify, expected_revision=revision, now=111)
    except PaymentConflict:
        results.put('stale')
    else:
        results.put('accepted')


def _crash_after_remote_refund(database, remote, binding):
    ledger = SQLitePaymentLedger(database)
    ledger.start_operation(binding, 'refund:full', 'crash-worker', check=_operator, lease_seconds=10, now=100)
    with closing(sqlite3.connect(remote)) as db, db:
        db.execute('INSERT INTO remote_refunds(operation_id,amount) VALUES (?,?)', ('refund:full', 1000))
    os._exit(27)


class PaymentLedgerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='payment-ledger-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / 'ledger.sqlite'
        self.ledger = SQLitePaymentLedger(self.database)
        self.ledger.initialize()
        self.binding = _binding()
        self.ledger.create_order(self.binding, 'invoice:1', now=90)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('CREATE TABLE operators(actor_id INTEGER PRIMARY KEY,enabled INTEGER)')
            db.execute('INSERT INTO operators VALUES (900,1)')

    def accept(self, event, **kwargs):
        return self.ledger.apply_event(_wire(event), verify=_verify, now=100, **kwargs)

    def pay(self, binding=None, **kwargs):
        event = _paid(binding or self.binding, **kwargs)
        self.accept(event)
        return event

    def reserve(self, operation='refund:1', amount=300):
        return self.ledger.request_refund(
            self.binding, 'charge:1', operation, Money(amount, 'USD', 2), 900, check=_operator, now=101
        )

    def test_invoice_confirmation_and_client_callbacks_never_grant_access(self):
        event = ProviderEvent(
            self.binding,
            'invoice:event',
            'invoice-created',
            'waiting_for_capture',
            'proof:invoice',
            operation_id='invoice:1',
            provider_ref='invoice:native:1',
        )
        self.accept(event)
        order = self.ledger.get_order(self.binding)
        self.assertEqual(
            (order.invoice_state, order.provider_state, order.confirmed_charges),
            ('confirmed', 'waiting_for_capture', 0),
        )
        self.assertFalse(self.ledger.has_access(self.binding, now=100).active)
        for raw in [_paid(self.binding), {'callback': 'paid'}, (_wire(_paid(self.binding))[0], '0' * 64)]:
            with self.assertRaises(PermissionDenied):
                self.ledger.apply_event(raw, verify=_verify, now=100)
        with self.assertRaises(TypeError):
            self.ledger.apply_event(_paid(self.binding))
        self.assertFalse(self.ledger.has_access(self.binding, now=100).active)

    def test_access_starts_after_authoritative_payment_time_and_bad_verifier_result_is_not_proof(self):
        for callback in [lambda _: True, lambda _: {'paid': True}, lambda _: None]:
            with self.assertRaises(InvalidType):
                self.ledger.apply_event(_wire(_paid(self.binding)), verify=callback, now=100)
        self.pay()
        self.assertFalse(self.ledger.has_access(self.binding, now=99).active)
        self.assertTrue(self.ledger.has_access(self.binding, now=100).active)

    def test_verifier_always_runs_outside_writer_transaction_including_duplicates(self):
        raw, called = _wire(_paid(self.binding)), []

        def verify(receipt):
            with closing(sqlite3.connect(self.database, timeout=0.01)) as independent:
                independent.execute('BEGIN IMMEDIATE')
                independent.rollback()
            called.append(True)
            return _verify(receipt)

        self.assertFalse(self.ledger.apply_event(raw, verify=verify, now=100).duplicate)
        self.assertTrue(self.ledger.apply_event(raw, verify=verify, now=101).duplicate)
        self.assertEqual(len(called), 2)
        self.assertEqual(self.ledger.get_order(self.binding).confirmed_charges, 1)

    def test_authenticated_binding_and_amount_mismatches_do_not_grant_or_mutate_order(self):
        changes = [
            dict(merchant_id='other'),
            dict(bot_id=101),
            dict(user_id=201),
            dict(order_id='other'),
            dict(provider='other'),
            dict(amount=Money(1001, 'USD', 2)),
        ]
        for case, change in enumerate(changes):
            with self.subTest(case=case), self.assertRaises(PaymentConflict):
                self.accept(_paid(replace(self.binding, **change)))
        for case, amount in enumerate([Money(1000, 'EUR', 2), Money(1000, 'USD', 3), Money(999, 'USD', 2)]):
            with self.subTest(case=case), self.assertRaises((PaymentConflict, ValidationFailure)):
                self.accept(_paid(self.binding, amount=amount))
        self.assertEqual(self.ledger.get_order(self.binding).confirmed_charges, 0)
        self.assertFalse(self.ledger.has_access(self.binding, now=100).active)

    def test_duplicates_conflicts_and_provider_native_status_survive_reopen_and_are_audited(self):
        event = self.pay()
        self.assertTrue(self.accept(replace(event, evidence_ref='verification:new')).duplicate)
        with self.assertRaises(PaymentConflict):
            self.accept(replace(event, provider_state='contradictory'))
        with self.assertRaises(PaymentConflict):
            self.accept(replace(event, event_id='payment:new', paid_at=101))
        reopened = SQLitePaymentLedger(self.database)
        self.assertEqual(reopened.get_order(self.binding).confirmed_charges, 1)
        self.assertEqual(reopened.get_order(self.binding).provider_state, 'captured')
        audit = reopened.audit(self.binding)
        self.assertEqual([entry['outcome'] for entry in audit[-4:]], ['accepted', 'duplicate', 'rejected', 'rejected'])
        self.assertEqual(audit[-2]['provider_state'], 'contradictory')
        changed = dict(audit[-1])
        changed['provider_state'] = 'changed'
        self.assertNotEqual(reopened.audit(self.binding)[-1]['provider_state'], 'changed')

    def test_scoped_charge_cannot_move_orders_and_one_time_order_rejects_second_charge(self):
        self.pay()
        other = replace(self.binding, order_id='order:2')
        self.ledger.create_order(other, 'invoice:2', now=90)
        with self.assertRaises(PaymentConflict):
            self.accept(_paid(other, event_id='other:paid'))
        with self.assertRaises(PaymentConflict):
            self.accept(_paid(self.binding, event_id='second:paid', charge_id='charge:2'))
        scoped = replace(self.binding, merchant_id='other:merchant')
        self.ledger.create_order(scoped, 'invoice:1', now=90)
        self.accept(_paid(scoped))
        self.assertTrue(self.ledger.has_access(scoped, now=100).active)
        self.assertFalse(self.ledger.has_access(other, now=100).active)

    def test_refund_reservation_is_persistent_deduplicated_and_bounded(self):
        self.pay()
        pending = self.reserve(amount=700)
        self.assertEqual(self.reserve(amount=700), pending)
        with self.assertRaises(PaymentConflict):
            self.reserve(amount=600)
        with self.assertRaises(PaymentConflict):
            self.reserve('refund:2', 301)
        reopened = SQLitePaymentLedger(self.database)
        self.assertEqual(reopened.get_charge(self.binding, 'charge:1')['reserved'], Money(700, 'USD', 2))
        self.assertEqual(reopened.get_charge(self.binding, 'charge:1')['refunded'], Money(0, 'USD', 2))
        self.assertTrue(reopened.has_access(self.binding, now=100).active)

    def test_current_operator_acl_rechecks_replay_and_start_in_writer_transaction(self):
        self.pay()
        self.reserve()
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('UPDATE operators SET enabled=0')
        for action in [
            lambda: self.reserve(),
            lambda: self.ledger.start_operation(self.binding, 'refund:1', 'worker', check=_operator, now=102),
        ]:
            with self.assertRaises(PermissionDenied):
                action()
        self.assertEqual(self.ledger.get_operation(self.binding, 'refund:1').state, 'pending')
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['reserved'].minor_units, 300)

    def test_operator_check_is_read_only_exact_true_and_cannot_commit_the_ledger(self):
        self.pay()
        for check in [lambda *_: 1, lambda *_: None]:
            with self.assertRaises(PermissionDenied):
                self.ledger.request_refund(self.binding, 'charge:1', 'denied', Money(300, 'USD', 2), 900, check=check)
        for check in [lambda db, *_: db.execute('UPDATE operators SET enabled=0'), lambda db, *_: db.commit()]:
            with self.assertRaises(sqlite3.DatabaseError):
                self.ledger.request_refund(self.binding, 'charge:1', 'denied', Money(300, 'USD', 2), 900, check=check)

        async def asynchronous(*_):
            return True

        with self.assertRaises(InvalidType):
            self.ledger.request_refund(
                self.binding, 'charge:1', 'denied', Money(300, 'USD', 2), 900, check=asynchronous
            )
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['reserved'].minor_units, 0)
        with self.assertRaises(PaymentConflict):
            self.ledger.get_operation(self.binding, 'denied')

    def test_cancel_unstarted_refund_releases_reservation_and_fences_dispatch(self):
        self.pay()
        self.reserve()
        cancelled = self.ledger.cancel_operation(self.binding, 'refund:1', 900, check=_operator, now=102)
        self.assertEqual((cancelled.state, cancelled.cancel_requested), ('cancelled', True))
        self.assertEqual(self.ledger.cancel_operation(self.binding, 'refund:1', 900, check=_operator), cancelled)
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['reserved'].minor_units, 0)
        with self.assertRaises(PaymentLeaseLost):
            self.ledger.start_operation(self.binding, 'refund:1', 'worker', check=_operator, now=103)

    def test_started_cancel_and_unknown_keep_reservation_until_authenticated_refund(self):
        self.pay()
        self.reserve(amount=1000)
        claim = self.ledger.start_operation(self.binding, 'refund:1', 'worker', check=_operator, now=102)
        cancellation = self.ledger.cancel_operation(self.binding, 'refund:1', 900, check=_operator, now=103)
        self.assertEqual((cancellation.state, cancellation.cancel_requested), ('sending', True))
        unknown = self.ledger.mark_unknown(claim, now=104)
        self.assertEqual(unknown.state, 'unknown')
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['reserved'].minor_units, 1000)
        with self.assertRaises(PaymentConflict):
            self.reserve('refund:2', 1)
        self.accept(_refund(self.binding, operation_id='refund:1', amount=self.binding.amount))
        operation = self.ledger.get_operation(self.binding, 'refund:1')
        self.assertEqual((operation.state, operation.cancel_requested), ('confirmed', True))
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['reserved'].minor_units, 0)
        self.assertFalse(self.ledger.has_access(self.binding, now=105).active)

    def test_partial_refunds_preserve_access_until_full_unless_product_policy_says_otherwise(self):
        self.pay()
        self.reserve()
        self.accept(_refund(self.binding, operation_id='refund:1'))
        self.assertTrue(self.ledger.has_access(self.binding, now=101).active)
        self.reserve('refund:2', 700)
        self.accept(
            _refund(
                self.binding,
                event_id='refund:event:2',
                refund_id='refund:native:2',
                operation_id='refund:2',
                amount=Money(700, 'USD', 2),
            )
        )
        self.assertFalse(self.ledger.has_access(self.binding, now=101).active)
        self.assertEqual(self.ledger.get_order(self.binding).fully_refunded_charges, 1)
        revoked = replace(self.binding, order_id='revoked', revoke_on_partial_refund=True)
        self.ledger.create_order(revoked, 'invoice:revoked', now=90)
        self.accept(_paid(revoked, event_id='revoked:paid', charge_id='revoked:charge'))
        self.accept(_refund(revoked, event_id='revoked:refund', charge_id='revoked:charge', refund_id='revoked:refund'))
        self.assertFalse(self.ledger.has_access(revoked, now=101).active)

    def test_same_native_refund_or_operation_cannot_debit_twice_under_different_event_ids(self):
        self.pay()
        self.reserve()
        event = _refund(self.binding, operation_id='refund:1')
        self.accept(event)
        self.accept(replace(event, event_id='redelivery:2'))
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['refunded'].minor_units, 300)
        for conflicting in [
            replace(event, event_id='conflict:amount', amount=Money(301, 'USD', 2)),
            replace(event, event_id='conflict:native', refund_id='refund:native:other'),
        ]:
            with self.assertRaises(PaymentConflict):
                self.accept(conflicting)
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['refunded'].minor_units, 300)

    def test_start_rechecks_budget_after_out_of_band_authoritative_refund(self):
        self.pay()
        self.reserve(amount=700)
        self.accept(_refund(self.binding, amount=Money(500, 'USD', 2)))
        with self.assertRaises(PaymentConflict):
            self.ledger.start_operation(self.binding, 'refund:1', 'worker', check=_operator, now=102)
        self.assertEqual(self.ledger.get_operation(self.binding, 'refund:1').state, 'pending')

    def test_authoritative_terminal_rejection_releases_refund_hold_without_granting_anything(self):
        self.pay()
        self.reserve(amount=1000)
        self.ledger.start_operation(self.binding, 'refund:1', 'worker', check=_operator, now=102)
        event = ProviderEvent(
            self.binding, 'rejection:1', 'rejected', 'refund_declined', 'proof:rejection', operation_id='refund:1'
        )
        self.accept(event)
        self.assertEqual(self.ledger.get_operation(self.binding, 'refund:1').state, 'failed')
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['reserved'].minor_units, 0)
        self.assertTrue(self.ledger.has_access(self.binding, now=105).active)

    def test_subscription_periods_expire_at_boundary_and_duplicate_charge_does_not_extend(self):
        sub = replace(self.binding, order_id='sub:order', subscription_id='subscription:1')
        self.ledger.create_order(sub, 'invoice:sub', now=90)
        first = self.pay(sub, event_id='sub:paid', period_start=50, period_end=200)
        self.assertTrue(self.ledger.has_access(sub, now=199).active)
        self.assertFalse(self.ledger.has_access(sub, now=200).active)
        self.accept(replace(first, event_id='sub:redelivery'))
        self.assertEqual(self.ledger.has_access(sub, now=150).expires_at, 200)
        second = self.pay(
            sub, event_id='sub:renewal', charge_id='charge:2', paid_at=150, period_start=200, period_end=400
        )
        self.assertEqual(SQLitePaymentLedger(self.database).has_access(sub, now=150).expires_at, 400)
        with self.assertRaises(PaymentConflict):
            self.accept(replace(second, event_id='sub:conflicting-period', period_end=401))
        self.assertFalse(self.ledger.has_access(sub, now=400).active)

    def test_cancel_renewal_never_revokes_paid_period_or_grants_a_new_period(self):
        sub = replace(self.binding, order_id='sub:order', subscription_id='subscription:1')
        self.ledger.create_order(sub, 'invoice:sub', now=90)
        self.pay(sub, event_id='sub:paid', period_start=100, period_end=200)
        pending = self.ledger.request_cancel_renewal(sub, 'cancel:renewal', 900, check=_operator, now=120)
        self.assertEqual(pending.state, 'pending')
        self.ledger.start_operation(sub, 'cancel:renewal', 'worker', check=_operator, now=120)
        canceled = ProviderEvent(
            sub,
            'sub:canceled',
            'renewal-state',
            'agreement_canceled',
            'proof:cancel',
            operation_id='cancel:renewal',
            renewal='canceled',
        )
        self.accept(canceled)
        self.assertEqual(self.ledger.get_operation(sub, 'cancel:renewal').state, 'confirmed')
        decision = self.ledger.has_access(sub, now=150)
        self.assertEqual((decision.active, decision.expires_at, decision.renewal), (True, 200, 'canceled'))
        self.assertFalse(self.ledger.has_access(sub, now=200).active)
        self.accept(
            replace(
                canceled, event_id='sub:active', operation_id=None, renewal='active', provider_state='agreement_active'
            )
        )
        self.assertFalse(self.ledger.has_access(sub, now=201).active)

    def test_partial_refund_policy_only_revokes_its_own_charge_not_another_paid_period(self):
        sub = replace(
            self.binding, order_id='sub:order', subscription_id='subscription:1', revoke_on_partial_refund=True
        )
        self.ledger.create_order(sub, 'invoice:sub', now=90)
        self.pay(sub, event_id='sub:first', period_start=100, period_end=200)
        self.pay(sub, event_id='sub:second', charge_id='charge:2', paid_at=150, period_start=150, period_end=300)
        self.accept(_refund(sub, event_id='sub:first:refund'))
        self.assertFalse(self.ledger.has_access(sub, now=140).active)
        self.assertEqual(self.ledger.has_access(sub, now=160).expires_at, 300)
        with self.assertRaises(PaymentConflict):
            self.ledger.create_order(replace(sub, order_id='other:sub', user_id=201), 'other:invoice', now=90)

    def test_stars_reuses_durable_pure_model_and_full_charge_refunds_preserve_other_periods(self):
        stars = _binding(
            order_id='stars:order',
            provider='telegram',
            route='telegram-stars',
            amount=Money(100, 'XTR', 0),
            allow_partial_refunds=False,
            subscription_id='stars:sub',
        )
        self.ledger.create_order(stars, 'stars:invoice', now=90)
        self.pay(stars, event_id='stars:paid:1', period_start=100, period_end=2592100, first_recurring=True)
        self.pay(
            stars,
            event_id='stars:paid:2',
            charge_id='stars:charge:2',
            paid_at=2592100,
            period_start=2592100,
            period_end=5184100,
        )
        with self.assertRaises(ValidationFailure):
            self.ledger.request_refund(stars, 'charge:1', 'stars:partial', Money(1, 'XTR', 0), 900, check=_operator)
        self.ledger.request_refund(stars, 'charge:1', 'stars:refund', stars.amount, 900, check=_operator)
        self.accept(_refund(stars, event_id='stars:refunded', operation_id='stars:refund', amount=stars.amount))
        self.assertFalse(self.ledger.has_access(stars, now=200).active)
        self.assertTrue(SQLitePaymentLedger(self.database).has_access(stars, now=2592100).active)
        self.assertFalse(self.ledger.has_access(stars, now=5184100).active)

    def test_stars_refund_before_payment_stays_refunded_after_durable_charge_arrives(self):
        stars = _binding(
            order_id='stars:order',
            provider='telegram',
            route='telegram-stars',
            amount=Money(100, 'XTR', 0),
            allow_partial_refunds=False,
            subscription_id='stars:sub',
        )
        self.ledger.create_order(stars, 'stars:invoice', now=90)
        self.accept(_refund(stars, event_id='stars:refund:first', amount=stars.amount))
        self.pay(stars, event_id='stars:paid:later', period_start=100, period_end=2592100, first_recurring=True)
        self.assertFalse(SQLitePaymentLedger(self.database).has_access(stars, now=200).active)

    def test_provider_specific_unmapped_state_is_retained_without_grant_or_normalization(self):
        event = ProviderEvent(self.binding, 'future:state', 'observed', 'future_awaiting_capture', 'proof:future')
        self.accept(event)
        self.assertEqual(self.ledger.get_order(self.binding).provider_state, 'future_awaiting_capture')
        self.assertFalse(self.ledger.has_access(self.binding, now=100).active)
        self.assertEqual(self.ledger.audit(self.binding)[-1]['provider_state'], event.provider_state)

    def test_invalid_route_identifiers_money_and_raw_diagnostics_are_rejected(self):
        cases = [
            lambda: _binding(bot_id=True),
            lambda: _binding(user_id=0),
            lambda: _binding(merchant_id='../private'),
            lambda: _binding(amount=Money(0, 'USD', 2)),
            lambda: _binding(amount=Money(1, 'XTR', 0)),
            lambda: _binding(route='telegram-stars', amount=Money(1, 'USD', 2)),
            lambda: _binding(route='telegram-stars', amount=Money(1, 'XTR', 0)),
            lambda: _binding(
                route='telegram-stars',
                amount=Money(10001, 'XTR', 0),
                allow_partial_refunds=False,
                subscription_id='sub',
            ),
            lambda: ProviderEvent(self.binding, 'id', 'paid', 'PRIVATE_CANARY card detail', 'proof'),
            lambda: ProviderEvent(self.binding, 'id', 'paid', 'captured', 'PRIVATE_CANARY\n'),
            lambda: _paid(self.binding, paid_at=True),
            lambda: _paid(self.binding, period_start=100, period_end=100),
            lambda: _paid(self.binding, period_start=100),
            lambda: SQLitePaymentLedger(':memory:'),
            lambda: SQLitePaymentLedger(self.database, timeout=True),
        ]
        for case, action in enumerate(cases):
            with self.subTest(case=case), self.assertRaises(ValidationFailure) as raised:
                action()
            self.assertNotIn('PRIVATE_CANARY', str(raised.exception))

    def test_wrong_operation_or_refund_amount_receipt_rolls_back_its_financial_changes(self):
        self.pay()
        self.reserve()
        for event in [
            _refund(self.binding, operation_id='invoice:1'),
            _refund(self.binding, operation_id='refund:1', amount=Money(301, 'USD', 2)),
        ]:
            with self.assertRaises(PaymentConflict):
                self.accept(event)
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['refunded'].minor_units, 0)
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['reserved'].minor_units, 300)

    def test_rejected_authenticated_receipts_are_audited_without_raw_body_or_exception_text(self):
        bad = _paid(self.binding, amount=Money(999, 'USD', 2))
        with self.assertRaises(PaymentConflict):
            self.accept(bad)
        row = self.ledger.audit(self.binding)[-1]
        self.assertEqual((row['outcome'], row['kind']), ('rejected', 'paid'))
        self.assertEqual(
            set(row),
            {
                'sequence',
                'merchant',
                'bot',
                'order_id',
                'operation_id',
                'kind',
                'outcome',
                'provider_state',
                'evidence_ref',
                'actor_id',
                'recorded_at',
            },
        )
        with self.assertRaises(PaymentConflict):
            self.ledger.get_charge(self.binding, 'charge:1')

    def test_refund_before_payment_is_durable_and_never_grants_refunded_charge(self):
        self.accept(_refund(self.binding, amount=self.binding.amount))
        self.assertFalse(self.ledger.has_access(self.binding, now=100).active)
        self.assertFalse(self.ledger.get_charge(self.binding, 'charge:1')['paid'])
        self.pay()
        self.assertFalse(SQLitePaymentLedger(self.database).has_access(self.binding, now=101).active)

    def test_invoice_lost_reply_is_unknown_and_cas_reconcile_does_not_grant_access(self):
        claim = self.ledger.start_operation(
            self.binding, 'invoice:1', 'worker', check=_allow, lease_seconds=10, now=100
        )
        with self.assertRaises(PaymentLeaseLost) as raised:
            self.ledger.mark_unknown(claim, now=110)
        report = safe_error_report(raised.exception, operation='write')
        self.assertEqual((report.outcome, report.recovery), ('unknown', 'reconcile'))
        self.assertEqual(self.ledger.recover_expired(self.binding, now=110), 1)
        unknown = self.ledger.get_operation(self.binding, 'invoice:1')
        with self.assertRaises(PaymentConflict):
            self.ledger.create_order(self.binding, 'invoice:new', now=111)
        event = ProviderEvent(
            self.binding,
            'invoice:proof',
            'invoice-created',
            'created',
            'proof:lookup',
            operation_id='invoice:1',
            provider_ref='invoice:native',
        )
        self.ledger.reconcile_operation(_wire(event), verify=_verify, expected_revision=unknown.revision, now=111)
        self.assertFalse(self.ledger.has_access(self.binding, now=111).active)
        with self.assertRaises(PaymentConflict):
            self.ledger.reconcile_operation(_wire(event), verify=_verify, expected_revision=unknown.revision, now=112)

    def test_expired_or_forged_claim_cannot_mutate_current_financial_operation(self):
        claim = self.ledger.start_operation(self.binding, 'invoice:1', 'worker', check=_allow, now=100)
        for forged in [replace(claim, token='0' * 32), replace(claim, worker_id='other')]:
            with self.assertRaises(PaymentLeaseLost):
                self.ledger.mark_unknown(forged, now=101)
        self.assertEqual(self.ledger.get_operation(self.binding, 'invoice:1').state, 'sending')

    def test_audit_storage_failure_rolls_back_payment_and_access_in_same_transaction(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("""CREATE TRIGGER reject_audit BEFORE INSERT ON payment_audit
                BEGIN SELECT RAISE(ABORT,'fixture audit unavailable'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.pay()
        self.assertFalse(self.ledger.has_access(self.binding, now=101).active)
        self.assertEqual(self.ledger.get_order(self.binding).confirmed_charges, 0)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('DROP TRIGGER reject_audit')
        self.pay()
        self.assertTrue(self.ledger.has_access(self.binding, now=101).active)

    def test_future_and_unexpected_schemas_are_refused_without_destroying_business_data(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('UPDATE payment_ledger_meta SET version=2')
        with self.assertRaises(UnsupportedCapability):
            self.ledger.initialize()
        self.assertEqual(self.ledger.get_order(self.binding).invoice_state, 'pending')
        other = self.root / 'unexpected.sqlite'
        with closing(sqlite3.connect(other)) as db, db:
            db.execute('CREATE TABLE payment_orders(preserve TEXT)')
            db.execute("INSERT INTO payment_orders VALUES ('keep')")
        with self.assertRaises(UnsupportedCapability):
            SQLitePaymentLedger(other).initialize()
        with closing(sqlite3.connect(other)) as db:
            self.assertEqual(db.execute('SELECT preserve FROM payment_orders').fetchone()[0], 'keep')

    @integration
    def test_two_processes_share_one_payment_receipt_and_one_paid_charge(self):
        self.run_race(_race_payment, _wire(_paid(self.binding)), expected=[False, True])
        self.assertEqual(self.ledger.get_order(self.binding).confirmed_charges, 1)

    @integration
    def test_concurrent_operator_refunds_cannot_exceed_remaining_paid_balance(self):
        self.pay()
        self.run_race(_race_refund, expected=['conflict', 'reserved'])
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['reserved'].minor_units, 700)

    @integration
    def test_two_workers_cannot_both_start_the_same_external_invoice_intent(self):
        self.run_race(_race_start, expected=['blocked', 'claimed'])
        self.assertEqual(self.ledger.get_operation(self.binding, 'invoice:1').state, 'sending')

    @integration
    def test_concurrent_authoritative_reviews_cannot_overwrite_revision_or_double_refund(self):
        self.pay()
        self.reserve(amount=1000)
        self.ledger.start_operation(self.binding, 'refund:1', 'worker', check=_operator, lease_seconds=10, now=100)
        self.ledger.recover_expired(self.binding, now=110)
        unknown = self.ledger.get_operation(self.binding, 'refund:1')
        event = _refund(self.binding, operation_id='refund:1', amount=self.binding.amount)
        self.run_race(_race_reconcile, (_wire(event), unknown.revision), expected=['accepted', 'stale'])
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['refunded'].minor_units, 1000)
        self.assertEqual(self.ledger.get_charge(self.binding, 'charge:1')['reserved'].minor_units, 0)

    def run_race(self, target, raw=None, *, expected):
        context = multiprocessing.get_context('spawn')
        gate, results = context.Event(), context.Queue()
        args = (str(self.database), self.binding) + ((raw,) if raw is not None else ()) + (gate, results)
        processes = [context.Process(target=target, args=args) for _ in range(2)]
        try:
            for process in processes:
                process.start()
            gate.set()
            self.assertEqual(sorted(results.get(timeout=20) for _ in processes), expected)
            for process in processes:
                process.join(20)
                self.assertEqual(process.exitcode, 0)
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                process.join(10)
            results.close()

    @integration
    def test_crash_after_separate_provider_effect_holds_budget_until_authoritative_reconciliation(self):
        self.pay()
        self.reserve('refund:full', 1000)
        remote = self.root / 'remote.sqlite'
        with closing(sqlite3.connect(remote)) as db, db:
            db.execute('CREATE TABLE remote_refunds(operation_id TEXT PRIMARY KEY,amount INTEGER)')
        context = multiprocessing.get_context('spawn')
        process = context.Process(
            target=_crash_after_remote_refund, args=(str(self.database), str(remote), self.binding)
        )
        process.start()
        process.join(20)
        if process.is_alive():
            process.terminate()
            process.join(10)
            self.fail('Crash worker did not finish')
        self.assertEqual(process.exitcode, 27)
        reopened = SQLitePaymentLedger(self.database)
        self.assertEqual(reopened.get_operation(self.binding, 'refund:full').state, 'sending')
        self.assertEqual(reopened.recover_expired(self.binding, now=110), 1)
        unknown = reopened.get_operation(self.binding, 'refund:full')
        self.assertEqual(
            (unknown.state, reopened.get_charge(self.binding, 'charge:1')['reserved'].minor_units), ('unknown', 1000)
        )
        with self.assertRaises(PaymentConflict):
            self.reserve('refund:another', 1)
        with closing(sqlite3.connect(remote)) as db:
            self.assertEqual(db.execute('SELECT amount FROM remote_refunds').fetchone()[0], 1000)
        event = _refund(self.binding, operation_id='refund:full', amount=self.binding.amount)
        reopened.reconcile_operation(_wire(event), verify=_verify, expected_revision=unknown.revision, now=111)
        self.assertFalse(reopened.has_access(self.binding, now=111).active)
        self.assertEqual(reopened.get_charge(self.binding, 'charge:1')['reserved'].minor_units, 0)
        with closing(sqlite3.connect(remote)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM remote_refunds').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
