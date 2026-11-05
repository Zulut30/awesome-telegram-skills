"""Platega durable callback→GET→invoice ledger composition; payment stays closed.

The published GET/callback lacks native paid_at. No synthetic paid event or time
is inserted to bypass that gap. Fake provider/host files are separate SQLite DBs.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from telegram_patterns import Money, PaymentBinding, SQLitePaymentLedger
from telegram_patterns.errors import PermissionDenied, UnsupportedCapability
from telegram_patterns.payment_ledger import PaymentConflict, PaymentLeaseLost
from telegram_patterns.providers import (
    InvoiceRequest,
    PlategaAdapter,
    ProviderHttpResponse,
    ProviderWriteUnknown,
    RefundRequest,
    binding_reference,
)

HEADERS = {'X-MerchantId': 'synthetic-native-merchant', 'X-Secret': 'synthetic-platega-secret'}
NOW = 1793880000
OPERATION = 'invoice:original'


def binding():
    return PaymentBinding(
        'durable-fixture', 100, 200, 'platega-order-1', 'platega', Money(2500, 'RUB', 2), allow_partial_refunds=True
    )


def allow(db, operation, replayed):
    return db.in_transaction and operation.actor_id == 200


def apply_verified(ledger, event, *, revision=None):
    capability = object()

    def verify(raw):
        if raw is not capability:
            raise PermissionDenied('Untrusted fixture handoff')
        return event

    if revision is None:
        return ledger.apply_event(capability, verify=verify, now=NOW + 10)
    return ledger.reconcile_operation(capability, verify=verify, expected_revision=revision, now=NOW + 10)


def adapter(transport):
    return PlategaAdapter(
        transport,
        merchant_id='durable-fixture',
        native_merchant_id=HEADERS['X-MerchantId'],
        secret=HEADERS['X-Secret'],
        payment_method=2,
    )


class DurablePlategaProvider:
    def __init__(self, path, *, lose_create=False):
        self.path, self.lose_create = path, lose_create
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS transactions(id TEXT PRIMARY KEY,wire TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS calls(method TEXT NOT NULL,path TEXT NOT NULL)')

    async def send(self, request):
        url = urlsplit(request.url)
        if url.scheme != 'https' or url.netloc != 'app.platega.io':
            raise AssertionError('Unexpected provider origin')
        if (
            request.headers.get('x-merchantid') != HEADERS['X-MerchantId']
            or request.headers.get('x-secret') != HEADERS['X-Secret']
        ):
            raise AssertionError('Missing merchant authentication')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO calls VALUES(?,?)', (request.method, url.path))
            if request.method == 'POST' and url.path == '/transaction/process':
                if 'idempotency-key' in request.headers:
                    raise AssertionError('Create must not invent provider idempotency')
                body = json.loads(request.body, parse_float=Decimal)
                if body['paymentDetails']['amount'] != Decimal('25.00'):
                    raise AssertionError('Unexpected fixture order amount')
                sequence = db.execute('SELECT count(*)+1 FROM transactions').fetchone()[0]
                native = f'00000000-0000-4000-8000-{sequence:012d}'
                wire = {
                    'id': native,
                    'status': 'PENDING',
                    'mechantId': HEADERS['X-MerchantId'],
                    'paymentDetails': {'amount': 25, 'currency': 'RUB'},
                    'payload': body['payload'],
                }
                db.execute('INSERT INTO transactions VALUES(?,?)', (native, json.dumps(wire)))
                db.commit()
                if self.lose_create:
                    raise TimeoutError('Synthetic reply lost after committed transaction')
                result = {
                    'transactionId': native,
                    'merchantId': HEADERS['X-MerchantId'],
                    'status': 'PENDING',
                    'redirect': 'https://fixture.invalid/platega-checkout',
                }
            elif request.method == 'GET' and url.path.startswith('/transaction/'):
                native = url.path.rsplit('/', 1)[1]
                row = db.execute('SELECT wire FROM transactions WHERE id=?', (native,)).fetchone()
                if row is None:
                    return ProviderHttpResponse(404, b'{}')
                result = json.loads(row[0])
            else:
                raise AssertionError('Unexpected provider operation')
        return ProviderHttpResponse(200, json.dumps(result).encode())

    def native_ids(self):
        # Closed fixture operator evidence, NOT a provider search-by-operation endpoint.
        with closing(sqlite3.connect(self.path)) as db:
            return [row[0] for row in db.execute('SELECT id FROM transactions ORDER BY id')]

    def change(self, native, **changes):
        with closing(sqlite3.connect(self.path)) as db, db:
            wire = json.loads(db.execute('SELECT wire FROM transactions WHERE id=?', (native,)).fetchone()[0])
            wire.update(changes)
            db.execute('UPDATE transactions SET wire=? WHERE id=?', (json.dumps(wire), native))

    def calls(self, method):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT count(*) FROM calls WHERE method=?', (method,)).fetchone()[0]


def callback(native, **changes):
    value = {
        'id': native,
        'status': 'CONFIRMED',
        'amount': 25,
        'currency': 'RUB',
        'paymentMethod': 2,
        'payload': binding_reference(binding(), OPERATION),
    }
    value.update(changes)
    return json.dumps(value, separators=(',', ':')).encode()


class PlategaHost:
    def __init__(self, path):
        self.path = path
        self.ledger = SQLitePaymentLedger(path)
        self.ledger.initialize()
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS fixture_links(native TEXT PRIMARY KEY,order_id TEXT NOT NULL)')
            db.execute(
                'CREATE TABLE IF NOT EXISTS fixture_callbacks('
                'digest TEXT PRIMARY KEY,body BLOB NOT NULL,decision TEXT NOT NULL DEFAULT \'pending\')'
            )

    def link(self, native, order):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO fixture_links VALUES(?,?)', (native, order.order_id))

    def accept(self, client, order, body, headers):
        hint = client.verify_event(body, headers)
        if hint is None:
            raise PermissionDenied('Callback authentication refused')
        data = json.loads(body, parse_float=Decimal)
        if (
            type(data.get('amount')) not in (int, Decimal)
            or Decimal(data['amount']) != Decimal(order.amount.to_decimal())
            or data.get('currency') != order.amount.currency
            or data.get('payload') != binding_reference(order, OPERATION)
        ):
            raise PermissionDenied('Callback differs from the server order')
        with closing(sqlite3.connect(self.path)) as db, db:
            linked = db.execute('SELECT order_id FROM fixture_links WHERE native=?', (hint.provider_id,)).fetchone()
            if linked != (order.order_id,):
                raise PermissionDenied('Unknown or differently bound transaction')
            digest = hashlib.sha256(body).hexdigest()
            # Shared secret is NOT copied to the journal. Receipt is accepted only after auth.
            db.execute('INSERT OR IGNORE INTO fixture_callbacks(digest,body) VALUES(?,?)', (digest, body))
        return digest  # Durable receipt is the boundary before any HTTP ACK.

    async def process(self, client, order, digest, *, fail_after_ledger=False):
        with closing(sqlite3.connect(self.path)) as db:
            body = db.execute('SELECT body FROM fixture_callbacks WHERE digest=?', (digest,)).fetchone()[0]
            native = json.loads(body)['id']
            linked = db.execute('SELECT order_id FROM fixture_links WHERE native=?', (native,)).fetchone()
        if linked != (order.order_id,):
            raise PermissionDenied('Durable callback binding differs')
        # GET verifies CURRENT merchant, original transaction, amount, currency and payload.
        event = await client.invoice_event(
            order, native, invoice_operation_id=OPERATION, evidence_ref='fixture:independent-get'
        )
        receipt = apply_verified(self.ledger, event)
        if fail_after_ledger:
            raise OSError('Synthetic failure after invoice ledger commit')
        try:
            await client.payment_event(
                order, native, invoice_operation_id=OPERATION, evidence_ref='fixture:unsupported-payment-boundary'
            )
        except UnsupportedCapability:
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("UPDATE fixture_callbacks SET decision='payment-unsupported' WHERE digest=?", (digest,))
            return receipt
        raise AssertionError('Platega must not invent native paid_at or grant payment access')


class PlategaDurableTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='platega-durable-')
        self.addCleanup(self.temporary.cleanup)
        self.host_path, self.provider_path = (
            Path(self.temporary.name) / name for name in ('host.sqlite', 'provider.sqlite')
        )
        self.host, self.remote = PlategaHost(self.host_path), DurablePlategaProvider(self.provider_path)
        self.order = binding()
        self.host.ledger.create_order(self.order, OPERATION, now=NOW)

    async def create(self):
        created = await adapter(self.remote).create(
            InvoiceRequest(self.order, 'Synthetic order', 'https://fixture.invalid/'),
            operation_id=OPERATION,
            customer_email='synthetic@example.invalid',
        )
        self.host.link(created.provider_id, self.order)
        return created.provider_id

    async def test_authenticated_callback_get_reopen_and_duplicate_record_invoice_without_paid_time_or_access(self):
        native = await self.create()
        self.remote.change(native, status='CONFIRMED')
        body = callback(native)
        digest = self.host.accept(adapter(self.remote), self.order, body, HEADERS)
        self.host = PlategaHost(self.host_path)
        with self.assertRaises(OSError):
            await self.host.process(adapter(self.remote), self.order, digest, fail_after_ledger=True)
        self.host = PlategaHost(self.host_path)
        self.assertTrue(
            (await self.host.process(adapter(DurablePlategaProvider(self.provider_path)), self.order, digest)).duplicate
        )
        self.assertEqual(self.host.accept(adapter(self.remote), self.order, body, HEADERS), digest)
        self.assertTrue((await self.host.process(adapter(self.remote), self.order, digest)).duplicate)
        invoice = self.host.ledger.get_operation(self.order, OPERATION)
        self.assertEqual(
            (invoice.provider_ref, invoice.state, invoice.provider_state), (native, 'confirmed', 'CONFIRMED')
        )
        self.assertEqual(self.host.ledger.get_order(self.order).confirmed_charges, 0)
        self.assertFalse(self.host.ledger.has_access(self.order, now=NOW + 10).active)
        self.assertEqual(self.remote.calls('POST'), 1)
        self.assertEqual(self.remote.calls('GET'), 3)
        with closing(sqlite3.connect(self.host_path)) as db:
            self.assertEqual(
                db.execute('SELECT count(*),min(decision) FROM fixture_callbacks').fetchone(),
                (1, 'payment-unsupported'),
            )
            self.assertEqual(db.execute('SELECT count(*) FROM payment_charges').fetchone()[0], 0)

    async def test_wrong_callback_and_independent_status_bindings_do_not_change_financial_facts(self):
        native = await self.create()
        for body, headers in (
            (callback(native), {**HEADERS, 'X-Secret': 'wrong'}),
            (callback(native, amount=26), HEADERS),
            (callback(native, currency='USD'), HEADERS),
            (callback(native, payload='other-order'), HEADERS),
            (callback('unknown-transaction'), HEADERS),
        ):
            with self.assertRaises(PermissionDenied):
                self.host.accept(adapter(self.remote), self.order, body, headers)
        self.assertEqual(self.remote.calls('GET'), 0)
        digest = self.host.accept(adapter(self.remote), self.order, callback(native), HEADERS)
        for fields in (
            {'mechantId': 'other-merchant'},
            {'mechantId': HEADERS['X-MerchantId'], 'paymentDetails': {'amount': 26, 'currency': 'RUB'}},
            {'paymentDetails': {'amount': 25, 'currency': 'RUB'}, 'payload': 'wrong-binding'},
        ):
            self.remote.change(native, **fields)
            with self.assertRaises(PermissionDenied):
                await PlategaHost(self.host_path).process(adapter(self.remote), self.order, digest)
        self.assertEqual(self.host.ledger.get_operation(self.order, OPERATION).state, 'pending')
        self.assertFalse(self.host.ledger.has_access(self.order, now=NOW + 10).active)

    async def test_callback_confirmed_does_not_override_current_pending_status_or_enable_refund(self):
        native = await self.create()  # GET remains PENDING although callback says CONFIRMED.
        digest = self.host.accept(adapter(self.remote), self.order, callback(native), HEADERS)
        self.assertFalse((await self.host.process(adapter(self.remote), self.order, digest)).duplicate)
        invoice = PlategaHost(self.host_path).ledger.get_operation(self.order, OPERATION)
        self.assertEqual(invoice.provider_state, 'PENDING')
        with self.assertRaises(PaymentConflict):
            self.host.ledger.request_refund(
                self.order, native, 'refund:blocked', Money(500, 'RUB', 2), 200, check=allow, now=NOW + 10
            )
        # Even an authenticated final refund callback cannot fabricate the absent paid charge.
        self.remote.change(native, status='PARTIALLY_REFUNDED')
        refund_id = '00000000-0000-4000-8000-000000000099'
        refund_body = callback(
            native, status='PARTIALLY_REFUNDED', refundId=refund_id, refundAmount=5, refundStatus='Succeeded'
        )
        event = await adapter(self.remote).refund_event(
            RefundRequest(self.order, native, Money(500, 'RUB', 2), OPERATION),
            refund_id,
            refund_body,
            HEADERS,
            operation_id='refund:blocked',
            evidence_ref='fixture:bound-get',
        )
        with self.assertRaises(PaymentConflict):
            apply_verified(self.host.ledger, event)
        self.assertEqual(self.host.ledger.get_order(self.order).confirmed_charges, 0)

    async def test_lost_create_unknown_blocks_second_create_and_reconciles_original_native_identity_only(self):
        claim = self.host.ledger.start_operation(
            self.order, OPERATION, 'first-worker', check=allow, now=NOW, lease_seconds=30
        )
        with self.assertRaises(ProviderWriteUnknown):
            await adapter(DurablePlategaProvider(self.provider_path, lose_create=True)).create(
                InvoiceRequest(self.order, 'Synthetic order', 'https://fixture.invalid/'),
                operation_id=OPERATION,
                customer_email='synthetic@example.invalid',
            )
        self.host.ledger.mark_unknown(claim, now=NOW + 1)
        reopened = PlategaHost(self.host_path)
        before = reopened.ledger.get_operation(self.order, OPERATION)
        self.assertEqual(before.state, 'unknown')
        with self.assertRaises(PaymentLeaseLost):
            reopened.ledger.start_operation(self.order, OPERATION, 'second-worker', check=allow, now=NOW + 2)
        with self.assertRaises(PaymentConflict):
            reopened.ledger.create_order(self.order, 'invoice:unsafe-new-id', now=NOW + 2)
        self.assertEqual((self.remote.calls('POST'), self.remote.calls('GET')), (1, 0))
        native = self.remote.native_ids()[0]  # Separate closed-fixture operator discovery.
        event = await adapter(self.remote).invoice_event(
            self.order,
            native,
            invoice_operation_id=OPERATION,
            evidence_ref='fixture:operator-id-then-authenticated-get',
        )
        self.assertFalse(apply_verified(reopened.ledger, event, revision=before.revision).duplicate)
        self.assertTrue(apply_verified(PlategaHost(self.host_path).ledger, event).duplicate)
        after = reopened.ledger.get_operation(self.order, OPERATION)
        self.assertEqual((after.operation_id, after.provider_ref, after.state), (OPERATION, native, 'confirmed'))
        self.assertEqual(self.remote.calls('POST'), 1)
        self.assertFalse(reopened.ledger.has_access(self.order, now=NOW + 10).active)
        with self.assertRaises(UnsupportedCapability):
            await adapter(self.remote).payment_event(
                self.order, native, invoice_operation_id=OPERATION, evidence_ref='fixture:no-native-paid-time'
            )


if __name__ == '__main__':
    unittest.main()
