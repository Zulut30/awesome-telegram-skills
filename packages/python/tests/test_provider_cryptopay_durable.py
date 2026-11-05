"""Crypto Pay: durable authenticated hints, independent GET and ledger replay.

Synthetic application/provider SQLite files; no Crypto Pay account or live payment.
The host journal below is a test composition, not a new library webhook service.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from telegram_patterns import Money, PaymentBinding, SQLitePaymentLedger
from telegram_patterns.errors import PermissionDenied, UnsupportedCapability
from telegram_patterns.payment_ledger import PaymentConflict, PaymentLeaseLost
from telegram_patterns.providers import (
    CryptoPayAdapter,
    InvoiceRequest,
    ProviderHttpResponse,
    ProviderReadFailure,
    ProviderWriteUnknown,
    binding_reference,
)

TOKEN = 'synthetic-crypto-application-token'
NOW = 1793880000
OPERATION = 'invoice:original'


def binding(order='crypto-order-1'):
    return PaymentBinding('durable-fixture', 100, 200, order, 'cryptopay', Money(2500, 'USD', 2))


def apply_verified(ledger, event, *, revision=None):
    # Capability exists only after awaited authenticated adapter GET. No public DTO proof.
    capability = object()

    def verify(raw):
        if raw is not capability:
            raise PermissionDenied('Untrusted fixture handoff')
        return event

    if revision is None:
        return ledger.apply_event(capability, verify=verify, now=NOW + 10)
    return ledger.reconcile_operation(capability, verify=verify, expected_revision=revision, now=NOW + 10)


def allow(db, operation, replayed):
    return db.in_transaction and operation.actor_id == 200


class DurableCryptoProvider:
    """Distinct fake provider storage survives reopening the host and transport."""

    def __init__(self, path, *, lose_create=False, fail_get=False):
        self.path, self.lose_create, self.fail_get = path, lose_create, fail_get
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY,wire TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS calls(method TEXT NOT NULL,path TEXT NOT NULL)')

    async def send(self, request):
        url = urlsplit(request.url)
        if url.scheme != 'https' or url.netloc != 'testnet-pay.crypt.bot':
            raise AssertionError('Unexpected provider origin')
        if request.headers.get('crypto-pay-api-token') != TOKEN:
            raise AssertionError('Missing authenticated API header')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO calls VALUES(?,?)', (request.method, url.path))
            if request.method == 'POST' and url.path == '/api/createInvoice':
                body = json.loads(request.body)
                identifier = db.execute('SELECT COALESCE(max(id),200)+1 FROM invoices').fetchone()[0]
                wire = {
                    'invoice_id': identifier,
                    'status': 'active',
                    'currency_type': body['currency_type'],
                    'fiat': body['fiat'],
                    'amount': body['amount'],
                    'payload': body['payload'],
                    'bot_invoice_url': 'https://t.me/CryptoBot?start=fixture',
                }
                db.execute('INSERT INTO invoices VALUES(?,?)', (identifier, json.dumps(wire)))
                # Effect is committed before the reply is deliberately lost.
                db.commit()
                if self.lose_create:
                    raise TimeoutError('Synthetic reply lost after provider commit')
                result = wire
            elif request.method == 'GET' and url.path == '/api/getInvoices':
                if self.fail_get:
                    return ProviderHttpResponse(503, b'{}')
                native = parse_qs(url.query)['invoice_ids'][0]
                row = db.execute('SELECT wire FROM invoices WHERE id=?', (native,)).fetchone()
                result = [] if row is None else [json.loads(row[0])]
            else:
                raise AssertionError('Unexpected provider method; no search-by-operation API')
        return ProviderHttpResponse(200, json.dumps({'ok': True, 'result': result}).encode())

    def native_ids(self):
        # Operator discovery in a CLOSED fixture, never an advertised Crypto Pay API.
        with closing(sqlite3.connect(self.path)) as db:
            return [str(row[0]) for row in db.execute('SELECT id FROM invoices ORDER BY id')]

    def change(self, native, **fields):
        with closing(sqlite3.connect(self.path)) as db, db:
            wire = json.loads(db.execute('SELECT wire FROM invoices WHERE id=?', (native,)).fetchone()[0])
            wire.update(fields)
            db.execute('UPDATE invoices SET wire=? WHERE id=?', (json.dumps(wire), native))

    def calls(self, method):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT count(*) FROM calls WHERE method=?', (method,)).fetchone()[0]


def adapter(transport):
    return CryptoPayAdapter(transport, merchant_id='durable-fixture', token=TOKEN, environment='testnet')


def signed_callback(native, *, update_id=7, order=None, operation_id=OPERATION):
    # Independent stdlib implementation of the published raw-body HMAC formula.
    order = order or binding()
    invoice = {
        'invoice_id': int(native),
        'hash': 'synthetic-invoice-hash-' + native,
        'status': 'paid',
        'currency_type': 'fiat',
        'fiat': order.amount.currency,
        'amount': order.amount.to_decimal(),
        'payload': binding_reference(order, operation_id),
        'bot_invoice_url': 'https://t.me/CryptoBot?start=fixture',
        'created_at': '2026-11-05T11:59:00Z',
        'paid_at': '2026-11-05T12:00:00Z',
        'allow_comments': False,
        'allow_anonymous': True,
        'paid_anonymously': True,
    }
    body = json.dumps(
        {
            'update_id': update_id,
            'update_type': 'invoice_paid',
            'request_date': '2026-11-05T12:00:00Z',
            'payload': invoice,
        },
        separators=(',', ':'),
    ).encode()
    signature = hmac.new(hashlib.sha256(TOKEN.encode()).digest(), body, hashlib.sha256).hexdigest()
    return body, {'crypto-pay-api-signature': signature}


class CryptoHost:
    def __init__(self, path):
        self.path = path
        self.ledger = SQLitePaymentLedger(path)
        self.ledger.initialize()
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(
                'CREATE TABLE IF NOT EXISTS fixture_links('
                'native TEXT PRIMARY KEY,order_id TEXT NOT NULL,operation_id TEXT NOT NULL)'
            )
            db.execute(
                'CREATE TABLE IF NOT EXISTS fixture_callbacks('
                'digest TEXT PRIMARY KEY,body BLOB NOT NULL,signature TEXT NOT NULL,done INTEGER NOT NULL DEFAULT 0)'
            )

    def link(self, native, order, operation_id=OPERATION):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO fixture_links VALUES(?,?,?)', (native, order.order_id, operation_id))

    def accept(self, client, order, body, headers):
        hint = client.verify_event(body, headers)
        if hint is None:
            raise PermissionDenied('Callback authentication refused')
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute('SELECT order_id FROM fixture_links WHERE native=?', (hint.provider_id,)).fetchone()
            if row != (order.order_id,):
                raise PermissionDenied('Unknown or differently bound native invoice')
            digest = hashlib.sha256(body).hexdigest()
            db.execute(
                'INSERT OR IGNORE INTO fixture_callbacks(digest,body,signature) VALUES(?,?,?)',
                (digest, body, headers['crypto-pay-api-signature']),
            )
        return digest  # An HTTP host may ACK only after this durable receipt commit.

    async def process(self, client, order, digest, *, fail_after_ledger=False):
        with closing(sqlite3.connect(self.path)) as db:
            body, signature = db.execute(
                'SELECT body,signature FROM fixture_callbacks WHERE digest=?', (digest,)
            ).fetchone()
        hint = client.verify_event(body, {'crypto-pay-api-signature': signature})
        if hint is None:
            raise PermissionDenied('Stored callback authentication refused')
        with closing(sqlite3.connect(self.path)) as db:
            linked = db.execute(
                'SELECT operation_id FROM fixture_links WHERE native=? AND order_id=?',
                (hint.provider_id, order.order_id),
            ).fetchone()
        if linked is None:
            raise PermissionDenied('Stored callback belongs to another server order')
        event = await client.payment_event(
            order, hint.provider_id, invoice_operation_id=linked[0], evidence_ref='fixture:independent-get'
        )
        receipt = apply_verified(self.ledger, event)
        if fail_after_ledger:
            raise OSError('Synthetic host failure after ledger commit, before receipt completion')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE fixture_callbacks SET done=1 WHERE digest=?', (digest,))
        return receipt


class CryptoPayDurableTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='cryptopay-durable-')
        self.addCleanup(self.temporary.cleanup)
        self.host_path, self.provider_path = (
            Path(self.temporary.name) / name for name in ('host.sqlite', 'provider.sqlite')
        )
        self.host, self.remote = CryptoHost(self.host_path), DurableCryptoProvider(self.provider_path)
        self.order = binding()
        self.host.ledger.create_order(self.order, OPERATION, now=NOW)

    async def create(self, order=None, *, operation_id=OPERATION):
        order = order or self.order
        created = await adapter(self.remote).create(
            InvoiceRequest(order, 'Synthetic order', 'https://fixture.invalid/'), operation_id=operation_id
        )
        self.host.link(created.provider_id, order, operation_id)
        self.remote.change(created.provider_id, status='paid', paid_at='2026-11-05T12:00:00Z')
        return created.provider_id

    async def test_authenticated_callback_independent_get_reopen_and_post_commit_replay_grant_once(self):
        native = await self.create()
        body, headers = signed_callback(native)
        digest = self.host.accept(adapter(self.remote), self.order, body, headers)
        self.assertFalse(self.host.ledger.has_access(self.order, now=NOW + 10).active)
        self.host = CryptoHost(self.host_path)  # Receipt survives reopen before processing.
        with self.assertRaises(OSError):
            await self.host.process(adapter(self.remote), self.order, digest, fail_after_ledger=True)
        self.host = CryptoHost(self.host_path)
        replay = await self.host.process(adapter(DurableCryptoProvider(self.provider_path)), self.order, digest)
        self.assertTrue(replay.duplicate)
        self.assertEqual(self.host.accept(adapter(self.remote), self.order, body, headers), digest)
        self.assertTrue((await self.host.process(adapter(self.remote), self.order, digest)).duplicate)
        self.assertEqual(self.host.ledger.get_order(self.order).confirmed_charges, 1)
        self.assertTrue(self.host.ledger.has_access(self.order, now=NOW + 10).active)
        self.assertEqual(self.host.ledger.get_charge(self.order, native)['amount'], self.order.amount)
        self.assertEqual(self.remote.calls('POST'), 1)
        self.assertEqual(self.remote.calls('GET'), 3)

    async def test_bad_signature_unknown_binding_and_nonpaid_or_wrong_status_never_grant(self):
        native = await self.create()
        body, headers = signed_callback(native)
        for changed in ({'crypto-pay-api-signature': '0' * 64},):
            with self.assertRaises(PermissionDenied):
                self.host.accept(adapter(self.remote), self.order, body, changed)
        other_body, other_headers = signed_callback('999')
        with self.assertRaises(PermissionDenied):
            self.host.accept(adapter(self.remote), self.order, other_body, other_headers)
        self.assertEqual(self.remote.calls('GET'), 0)
        digest = self.host.accept(adapter(self.remote), self.order, body, headers)
        for changes, error in (
            ({'status': 'active'}, UnsupportedCapability),
            ({'status': 'paid', 'amount': '25.01'}, PermissionDenied),
            ({'amount': '25.00', 'payload': 'different-order'}, PermissionDenied),
        ):
            self.remote.change(native, **changes)
            with self.assertRaises(error):
                await CryptoHost(self.host_path).process(adapter(self.remote), self.order, digest)
            self.assertEqual(self.host.ledger.get_order(self.order).confirmed_charges, 0)
        with closing(sqlite3.connect(self.host_path)) as db:
            self.assertEqual(db.execute('SELECT count(*),sum(done) FROM fixture_callbacks').fetchone(), (1, 0))

    async def test_read_failure_retains_receipt_and_nonunique_update_id_does_not_merge_invoices(self):
        first = await self.create()
        body, headers = signed_callback(first, update_id=7)
        digest = self.host.accept(adapter(self.remote), self.order, body, headers)
        with self.assertRaises(ProviderReadFailure):
            await self.host.process(
                adapter(DurableCryptoProvider(self.provider_path, fail_get=True)), self.order, digest
            )
        other = binding('crypto-order-2')
        self.host.ledger.create_order(other, OPERATION + ':second', now=NOW)
        second = await self.create(other, operation_id=OPERATION + ':second')
        second_body, second_headers = signed_callback(
            second, update_id=7, order=other, operation_id=OPERATION + ':second'
        )
        second_digest = self.host.accept(adapter(self.remote), other, second_body, second_headers)
        self.assertNotEqual(digest, second_digest)
        self.host = CryptoHost(self.host_path)
        self.assertFalse((await self.host.process(adapter(self.remote), self.order, digest)).duplicate)
        self.assertFalse((await self.host.process(adapter(self.remote), other, second_digest)).duplicate)
        self.assertEqual(self.host.ledger.get_order(self.order).confirmed_charges, 1)
        self.assertEqual(self.host.ledger.get_order(other).confirmed_charges, 1)
        self.assertNotEqual(first, second)

    async def test_lost_create_retains_original_unknown_and_never_creates_again_before_trusted_native_lookup(self):
        claim = self.host.ledger.start_operation(
            self.order, OPERATION, 'first-worker', check=allow, now=NOW, lease_seconds=30
        )
        with self.assertRaises(ProviderWriteUnknown):
            await adapter(DurableCryptoProvider(self.provider_path, lose_create=True)).create(
                InvoiceRequest(self.order, 'Synthetic order', 'https://fixture.invalid/'), operation_id=OPERATION
            )
        self.host.ledger.mark_unknown(claim, now=NOW + 1)
        reopened = CryptoHost(self.host_path)
        before = reopened.ledger.get_operation(self.order, OPERATION)
        self.assertEqual(before.state, 'unknown')
        with self.assertRaises(PaymentLeaseLost):
            reopened.ledger.start_operation(self.order, OPERATION, 'second-worker', check=allow, now=NOW + 2)
        with self.assertRaises(PaymentConflict):
            reopened.ledger.create_order(self.order, 'invoice:unsafe-new-id', now=NOW + 2)
        self.assertEqual(self.remote.calls('POST'), 1)
        self.assertEqual(self.remote.calls('GET'), 0)  # No invented operation-ID discovery endpoint.
        native = self.remote.native_ids()[0]  # Explicit trusted operator discovery, fixture only.
        event = await adapter(self.remote).invoice_event(
            self.order,
            native,
            invoice_operation_id=OPERATION,
            evidence_ref='fixture:operator-id-then-authenticated-get',
        )
        with self.assertRaises(PaymentConflict):
            apply_verified(reopened.ledger, event, revision=before.revision + 1)
        self.assertEqual(reopened.ledger.get_operation(self.order, OPERATION), before)
        self.assertFalse(apply_verified(reopened.ledger, event, revision=before.revision).duplicate)
        after = CryptoHost(self.host_path).ledger.get_operation(self.order, OPERATION)
        self.assertEqual((after.operation_id, after.provider_ref, after.state), (OPERATION, native, 'confirmed'))
        self.assertFalse(reopened.ledger.has_access(self.order, now=NOW + 10).active)
        self.assertEqual(self.remote.calls('POST'), 1)


if __name__ == '__main__':
    unittest.main()
