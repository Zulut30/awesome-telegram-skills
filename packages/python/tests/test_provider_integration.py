"""Crash/reopen against a distinct durable fake-provider DB; never a live provider claim."""

import asyncio
import json
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

from _support import integration
from test_provider_http import binding, response
from test_provider_yookassa import adapter, payment, refund

from telegram_patterns.money import Money
from telegram_patterns.outbox import SQLiteOutbox
from telegram_patterns.payment_ledger import SQLitePaymentLedger
from telegram_patterns.providers import InvoiceRequest, ProviderWriteUnknown, RefundRequest


def allow(_db, _operation, _replayed):
    return True


def apply_verified(ledger, event, *, revision=None):
    # Private host handoff: network authentication already happened in the awaited adapter call.
    # The token is scoped to this invocation, not a remotely constructible DTO authentication scheme.
    token = object()

    def verify(raw):
        if raw is not token:
            raise AssertionError('Untrusted handoff')
        return event

    if revision is None:
        return ledger.apply_event(token, verify=verify, now=1793880010)
    return ledger.reconcile_operation(token, verify=verify, expected_revision=revision, now=1793880010)


class DurableFakeTransport:
    def __init__(self, database, *, lose_reply=False):
        self.database = database
        self.lose_reply = lose_reply

    async def send(self, request):
        with closing(sqlite3.connect(self.database)) as db:
            if request.method == 'POST':
                wire = json.loads(request.body)
                if request.url.endswith('/capture'):
                    data = json.loads(db.execute('SELECT wire FROM effects WHERE kind=?', ('payment',)).fetchone()[0])
                    if data['status'] != 'waiting_for_capture' or wire['amount'] != data['amount']:
                        return response({}, status=400)
                    data['status'] = 'succeeded'
                    data['captured_at'] = '2026-11-05T12:00:00Z'
                    db.execute('UPDATE effects SET wire=? WHERE kind=?', (json.dumps(data), 'payment'))
                    db.execute(
                        'INSERT INTO effects(kind,wire) VALUES(?,?)',
                        ('capture', json.dumps({'request': wire, 'key': request.headers['idempotence-key']})),
                    )
                    db.commit()
                    if self.lose_reply:
                        raise TimeoutError('Capture committed, response lost')
                    return response(data)
                kind = 'refund' if request.url.endswith('/refunds') else 'payment'
                data = refund() if kind == 'refund' else payment()
                if kind == 'payment':
                    data['amount'], data['metadata'] = wire['amount'], wire['metadata']
                else:
                    data['amount'], data['payment_id'] = wire['amount'], wire['payment_id']
                # The external effect commits independently of the client's ledger and response receipt.
                db.execute('INSERT INTO effects(kind,wire) VALUES(?,?)', (kind, json.dumps(data)))
                db.commit()
                if self.lose_reply:
                    raise TimeoutError('Effect committed, response lost')
                return response(data)
            kind = 'refund' if '/refunds/' in request.url else 'payment'
            data = db.execute('SELECT wire FROM effects WHERE kind=?', (kind,)).fetchone()
            return response(json.loads(data[0])) if data else response({}, status=404)


def crash_after_write(local_database, remote_database, kind):
    async def run():
        ledger = SQLitePaymentLedger(local_database)
        order = binding()
        operation_id = 'invoice:1' if kind == 'payment' else 'refund:1'
        ledger.start_operation(order, operation_id, 'crashing-worker', check=allow, lease_seconds=2, now=1793880001)
        client = adapter(DurableFakeTransport(remote_database, lose_reply=True))
        try:
            if kind == 'payment':
                await client.create(
                    InvoiceRequest(order, 'Order', 'https://shop.example.com/'), operation_id=operation_id
                )
            else:
                await client.refund(
                    RefundRequest(order, 'payment-1', Money(2345, 'RUB', 2), 'invoice:1'), operation_id=operation_id
                )
        except ProviderWriteUnknown:
            os._exit(73)  # Simulate crash before writing unknown to the client ledger.
        os._exit(74)

    asyncio.run(run())


def crash_after_capture(local_database, remote_database):
    async def run():
        journal = SQLiteOutbox(local_database, max_attempts=1)
        claim = journal.claim('merchant:test:bot:100:capture', 'crashing-worker', lease_seconds=2, now=1793880001)
        if claim is None:
            os._exit(75)
        payload = claim.payload
        client = adapter(DurableFakeTransport(remote_database, lose_reply=True))
        if (
            client.capture_key(
                binding(),
                payload['provider_id'],
                invoice_operation_id=payload['invoice_operation_id'],
                operation_id=payload['capture_operation_id'],
            )
            != payload['idempotence_key']
        ):
            os._exit(76)
        try:
            await client.capture(
                binding(),
                payload['provider_id'],
                invoice_operation_id=payload['invoice_operation_id'],
                operation_id=payload['capture_operation_id'],
            )
        except ProviderWriteUnknown:
            os._exit(77)
        os._exit(78)

    asyncio.run(run())


@integration
class ProviderCrashTests(unittest.TestCase):
    def test_capture_effect_survives_crash_and_outbox_reconcile_never_resends(self):
        with tempfile.TemporaryDirectory() as directory:
            local, remote = Path(directory) / 'ledger.sqlite', Path(directory) / 'provider.sqlite'
            ledger, journal = SQLitePaymentLedger(local), SQLiteOutbox(local, max_attempts=1)
            ledger.initialize()
            journal.initialize()
            order = binding()
            ledger.create_order(order, 'invoice:1', now=1793880000)
            with closing(sqlite3.connect(remote)) as db:
                db.execute('CREATE TABLE effects(kind TEXT PRIMARY KEY,wire TEXT NOT NULL)')
                db.execute(
                    'INSERT INTO effects VALUES(?,?)',
                    ('payment', json.dumps(payment(status='waiting_for_capture', captured_at=None))),
                )
                db.commit()
            client = adapter(DurableFakeTransport(remote))
            apply_verified(
                ledger,
                asyncio.run(
                    client.invoice_event(
                        order, 'payment-1', invoice_operation_id='invoice:1', evidence_ref='verified:held'
                    )
                ),
            )
            key = client.capture_key(order, 'payment-1', invoice_operation_id='invoice:1', operation_id='capture:1')
            body = {'amount': {'value': order.amount.to_decimal(), 'currency': order.amount.currency}}
            with closing(sqlite3.connect(local, isolation_level=None)) as db:
                db.execute('BEGIN IMMEDIATE')
                journal.enqueue(
                    db,
                    'merchant:test:bot:100:capture',
                    'capture:1',
                    {
                        'binding': asdict(order),
                        'provider_id': 'payment-1',
                        'invoice_operation_id': 'invoice:1',
                        'capture_operation_id': 'capture:1',
                        'idempotence_key': key,
                        'request': body,
                    },
                    now=1793880000,
                )
                db.commit()
            self.assertFalse(ledger.has_access(order, now=1793880001).active)
            process = multiprocessing.get_context('spawn').Process(
                target=crash_after_capture, args=(str(local), str(remote))
            )
            process.start()
            process.join(20)
            if process.is_alive():
                process.terminate()
                process.join(5)
                self.fail('Capture crash fixture did not terminate')
            self.assertEqual(process.exitcode, 77)
            reopened = SQLiteOutbox(local, max_attempts=1)
            self.assertEqual(reopened.get('merchant:test:bot:100:capture', 'capture:1').state, 'sending')
            self.assertEqual(reopened.recover_expired('merchant:test:bot:100:capture', now=1793880004), 1)
            unknown = reopened.get('merchant:test:bot:100:capture', 'capture:1')
            self.assertEqual(unknown.state, 'unknown')
            self.assertIsNone(reopened.claim('merchant:test:bot:100:capture', 'another-worker', now=1793880005))
            self.assertFalse(SQLitePaymentLedger(local).has_access(order, now=1793880005).active)
            event = asyncio.run(
                client.payment_event(
                    order, 'payment-1', invoice_operation_id='invoice:1', evidence_ref='verified:capture-reconcile'
                )
            )
            reopened.reconcile(
                'merchant:test:bot:100:capture',
                'capture:1',
                expected_revision=unknown.revision,
                outcome='sent',
                evidence_ref='verified:capture-reconcile',
                result={'provider_id': event.charge_id, 'state': event.provider_state},
                now=1793880006,
            )
            self.assertFalse(apply_verified(SQLitePaymentLedger(local), event).duplicate)
            self.assertTrue(apply_verified(SQLitePaymentLedger(local), event).duplicate)
            self.assertTrue(SQLitePaymentLedger(local).has_access(order, now=1793880010).active)
            with closing(sqlite3.connect(remote)) as db:
                effects = db.execute('SELECT wire FROM effects WHERE kind=?', ('capture',)).fetchall()
                self.assertEqual(len(effects), 1)
                self.assertEqual(json.loads(effects[0][0]), {'request': body, 'key': key})

    def test_create_effect_survives_crash_and_reconcile_never_creates_second_invoice(self):
        self._crash_case('payment')

    def test_refund_effect_survives_crash_holds_budget_and_reconciles_once(self):
        self._crash_case('refund')

    def _crash_case(self, kind):
        with tempfile.TemporaryDirectory() as directory:
            local, remote = Path(directory) / 'ledger.sqlite', Path(directory) / 'provider.sqlite'
            ledger = SQLitePaymentLedger(local)
            ledger.initialize()
            order = binding()
            ledger.create_order(order, 'invoice:1', now=1793880000)
            with closing(sqlite3.connect(remote)) as db:
                db.execute('CREATE TABLE effects(kind TEXT PRIMARY KEY,wire TEXT NOT NULL)')
                if kind == 'refund':
                    db.execute('INSERT INTO effects VALUES(?,?)', ('payment', json.dumps(payment())))
                db.commit()
            if kind == 'refund':
                client = adapter(DurableFakeTransport(remote))
                event = asyncio.run(
                    client.payment_event(
                        order, 'payment-1', invoice_operation_id='invoice:1', evidence_ref='verified:initial'
                    )
                )
                apply_verified(ledger, event)
                ledger.request_refund(
                    order, 'payment-1', 'refund:1', Money(2345, 'RUB', 2), 900, check=allow, now=1793880000
                )
            process = multiprocessing.get_context('spawn').Process(
                target=crash_after_write, args=(str(local), str(remote), kind)
            )
            process.start()
            process.join(20)
            if process.is_alive():
                process.terminate()
                process.join(5)
                self.fail('Crash fixture did not terminate')
            self.assertEqual(process.exitcode, 73)
            operation_id = 'invoice:1' if kind == 'payment' else 'refund:1'
            reopened = SQLitePaymentLedger(local)
            self.assertEqual(reopened.get_operation(order, operation_id).state, 'sending')
            self.assertEqual(reopened.recover_expired(order, now=1793880004), 1)
            unknown = reopened.get_operation(order, operation_id)
            self.assertEqual(unknown.state, 'unknown')
            if kind == 'refund':
                self.assertEqual(reopened.get_charge(order, 'payment-1')['reserved'], Money(2345, 'RUB', 2))
            client = adapter(DurableFakeTransport(remote))
            if kind == 'payment':
                # In a real lost-create case this ID must come from an authenticated lookup/operator evidence.
                # This fixture knows it from the separate provider DB; it does not invent a discovery API.
                event = asyncio.run(
                    client.invoice_event(
                        order, 'payment-1', invoice_operation_id='invoice:1', evidence_ref='verified:reconcile'
                    )
                )
            else:
                request = RefundRequest(order, 'payment-1', Money(2345, 'RUB', 2), 'invoice:1')
                event = asyncio.run(
                    client.refund_event(request, 'refund-1', operation_id='refund:1', evidence_ref='verified:reconcile')
                )
            self.assertFalse(apply_verified(reopened, event, revision=unknown.revision).duplicate)
            self.assertTrue(apply_verified(reopened, event).duplicate)
            self.assertEqual(reopened.get_operation(order, operation_id).state, 'confirmed')
            if kind == 'payment':
                event = asyncio.run(
                    client.payment_event(
                        order, 'payment-1', invoice_operation_id='invoice:1', evidence_ref='verified:paid'
                    )
                )
                self.assertFalse(apply_verified(reopened, event).duplicate)
                self.assertTrue(apply_verified(reopened, event).duplicate)
                self.assertEqual(reopened.get_order(order).confirmed_charges, 1)
            else:
                charge = reopened.get_charge(order, 'payment-1')
                self.assertEqual((charge['refunded'], charge['reserved']), (Money(2345, 'RUB', 2), Money(0, 'RUB', 2)))
            with closing(sqlite3.connect(remote)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM effects WHERE kind=?', (kind,)).fetchone()[0], 1)
