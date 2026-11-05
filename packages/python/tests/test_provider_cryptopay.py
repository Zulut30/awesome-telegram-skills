"""Official Crypto Pay wire-shape fixtures, not a live application/account acceptance."""

import hashlib
import hmac
import json
import unittest

from test_provider_http import ScriptedTransport, binding, response

from telegram_patterns.errors import PermissionDenied, UnsupportedCapability, ValidationFailure
from telegram_patterns.money import Money
from telegram_patterns.providers import (
    CryptoPayAdapter,
    InvoiceRequest,
    ProviderReadFailure,
    ProviderWriteUnknown,
    RefundRequest,
    binding_reference,
)


def invoice(order=None, **changes):
    order = order or binding('cryptopay')
    data = dict(
        invoice_id=123,
        status='paid',
        currency_type='fiat',
        fiat=order.amount.currency,
        amount=order.amount.to_decimal(),
        payload=binding_reference(order, 'invoice:1'),
        paid_at='2026-11-05T12:00:00Z',
        bot_invoice_url='https://t.me/CryptoBot?start=IV123',
        paid_asset='TON',
        paid_amount='0.123',
        fee_asset='TON',
        fee_amount='0.001',
    )
    data.update(changes)
    return data


def signed(body, token='fixture-token'):
    return {
        'crypto-pay-api-signature': hmac.new(hashlib.sha256(token.encode()).digest(), body, hashlib.sha256).hexdigest()
    }


class CryptoPayTests(unittest.IsolatedAsyncioTestCase):
    async def test_crypto_asset_keeps_its_exact_exponent_and_testnet_asset_scope(self):
        order = binding('cryptopay', amount=Money(1000001, 'USDT', 6))
        native = invoice(order, currency_type='crypto', asset='USDT', status='active')
        native.pop('fiat')
        transport = ScriptedTransport(response({'ok': True, 'result': native}))
        adapter = CryptoPayAdapter(
            transport, merchant_id=order.merchant_id, token='fixture-token', currency_type='crypto'
        )
        created = await adapter.create(
            InvoiceRequest(order, 'Order', 'https://shop.example.com/'), operation_id='invoice:1'
        )
        self.assertEqual(created.amount, Money(1000001, 'USDT', 6))
        wire = json.loads(transport.requests[0].body)
        self.assertEqual((wire['asset'], wire['amount']), ('USDT', '1.000001'))
        self.assertNotIn('fiat', wire)
        no_http = ScriptedTransport()
        mainnet = CryptoPayAdapter(
            no_http, merchant_id=order.merchant_id, token='fixture-token', currency_type='crypto', environment='mainnet'
        )
        with self.assertRaises(UnsupportedCapability):
            await mainnet.get(
                '123', binding=binding('cryptopay', amount=Money(1, 'JET', 0)), invoice_operation_id='invoice:1'
            )
        self.assertEqual(no_http.requests, [])

    async def test_invoice_reconciliation_preserves_state_without_claiming_payment(self):
        adapter = CryptoPayAdapter(
            ScriptedTransport(response({'ok': True, 'result': [invoice(status='future-state')]})),
            merchant_id='merchant:test',
            token='fixture-token',
        )
        event = await adapter.invoice_event(
            binding('cryptopay'), '123', invoice_operation_id='invoice:1', evidence_ref='proof:created'
        )
        self.assertEqual(
            (event.kind, event.provider_state, event.provider_ref, event.operation_id),
            ('invoice-created', 'future-state', '123', 'invoice:1'),
        )
        self.assertIsNone(event.charge_id)

    async def test_create_exact_nominal_wire_and_fixed_environment(self):
        order = binding('cryptopay', amount=Money(9007199254740991, 'USD', 2))
        transport = ScriptedTransport(response({'ok': True, 'result': invoice(order, status='active')}))
        adapter = CryptoPayAdapter(transport, merchant_id=order.merchant_id, token='fixture-token')
        created = await adapter.create(
            InvoiceRequest(order, 'Order', 'https://shop.example.com/return'), operation_id='invoice:1'
        )
        self.assertEqual(created.amount, order.amount)
        request = transport.requests[0]
        self.assertEqual(request.url, 'https://testnet-pay.crypt.bot/api/createInvoice')
        wire = json.loads(request.body)
        self.assertEqual(wire['amount'], '90071992547409.91')
        self.assertEqual(wire['payload'], binding_reference(order, 'invoice:1'))
        self.assertFalse(wire['allow_comments'])
        self.assertNotIn('idempotence-key', request.headers)
        self.assertNotIn('fixture-token', repr(adapter))
        main = ScriptedTransport(response({'ok': True, 'result': [invoice()]}))
        await CryptoPayAdapter(main, merchant_id=order.merchant_id, token='main-token', environment='mainnet').get(
            '123', binding=binding('cryptopay'), invoice_operation_id='invoice:1'
        )
        self.assertEqual(main.requests[0].url, 'https://pay.crypt.bot/api/getInvoices?invoice_ids=123')

    async def test_paid_mapping_uses_native_invoice_not_notification_update_or_settled_coin(self):
        order = binding('cryptopay')
        transport = ScriptedTransport(response({'ok': True, 'result': {'items': [invoice()]}}))
        adapter = CryptoPayAdapter(transport, merchant_id=order.merchant_id, token='fixture-token')
        event = await adapter.payment_event(order, '123', invoice_operation_id='invoice:1', evidence_ref='proof:1')
        self.assertEqual(
            (event.kind, event.charge_id, event.amount, event.paid_at), ('paid', '123', order.amount, 1793880000)
        )
        self.assertEqual(len(transport.requests), 1)

    def test_exact_raw_hmac_and_nonunique_update_id(self):
        adapter = CryptoPayAdapter(ScriptedTransport(), merchant_id='merchant:test', token='fixture-token')
        body = json.dumps(
            dict(update_id=7, update_type='invoice_paid', request_date='2026-11-05T12:00:00Z', payload=invoice())
        ).encode()
        hint = adapter.verify_event(body, signed(body))
        self.assertEqual((hint.provider_id, hint.native_state), ('123', 'paid'))
        self.assertIsNone(adapter.verify_event(body + b' ', signed(body)))
        self.assertIsNone(adapter.verify_event(body, signed(body, 'wrong-token')))
        self.assertIsNone(adapter.verify_event(body, {'crypto-pay-api-signature': 'a' * 63}))
        second = body.replace(b'"invoice_id": 123', b'"invoice_id": 124')
        self.assertEqual(adapter.verify_event(second, signed(second)).provider_id, '124')
        # Valid signature never substitutes for required schema checks.
        duplicate = b'{"update_type":"invoice_paid","update_type":"invoice_paid"}'
        with self.assertRaises(ValidationFailure):
            adapter.verify_event(duplicate, signed(duplicate))

    async def test_wrong_binding_amount_currency_mode_and_native_id_never_grant(self):
        for changes in [
            {'amount': '123.46'},
            {'fiat': 'USD'},
            {'payload': 'wrong-order'},
            {'currency_type': 'crypto'},
            {'invoice_id': 124},
            {'invoice_id': True},
        ]:
            order = binding('cryptopay')
            adapter = CryptoPayAdapter(
                ScriptedTransport(response({'ok': True, 'result': [invoice(**changes)]})),
                merchant_id=order.merchant_id,
                token='fixture-token',
            )
            with self.subTest(changes=changes), self.assertRaises((PermissionDenied, ValidationFailure)):
                await adapter.payment_event(order, '123', invoice_operation_id='invoice:1', evidence_ref='proof:1')

    async def test_nonpaid_unknown_and_absent_invoice_do_not_prove_no_late_payment(self):
        for state in ('active', 'expired', 'future-state'):
            adapter = CryptoPayAdapter(
                ScriptedTransport(response({'ok': True, 'result': [invoice(status=state)]})),
                merchant_id='merchant:test',
                token='fixture-token',
            )
            with self.assertRaises(UnsupportedCapability):
                await adapter.payment_event(
                    binding('cryptopay'), '123', invoice_operation_id='invoice:1', evidence_ref='proof:1'
                )
        adapter = CryptoPayAdapter(
            ScriptedTransport(response({'ok': True, 'result': {'items': []}})),
            merchant_id='merchant:test',
            token='fixture-token',
        )
        with self.assertRaises(ProviderReadFailure):
            await adapter.get('123', binding=binding('cryptopay'), invoice_operation_id='invoice:1')

    async def test_write_api_error_invalid_envelope_and_wrong_success_are_unknown(self):
        for data in [
            {'ok': False, 'error': {'name': 'private-provider-detail'}},
            [],
            {'ok': True, 'result': invoice(amount='1.00')},
        ]:
            transport = ScriptedTransport(response(data))
            adapter = CryptoPayAdapter(transport, merchant_id='merchant:test', token='fixture-token')
            with self.assertRaises(ProviderWriteUnknown):
                await adapter.create(
                    InvoiceRequest(binding('cryptopay'), 'Order', 'https://shop.example.com/'), operation_id='invoice:1'
                )
            self.assertEqual(len(transport.requests), 1)

    async def test_unsupported_refunds_subscription_and_cross_merchant_do_no_http(self):
        transport = ScriptedTransport()
        adapter = CryptoPayAdapter(transport, merchant_id='merchant:test', token='fixture-token')
        with self.assertRaises(UnsupportedCapability):
            await adapter.refund(
                RefundRequest(binding('cryptopay'), '123', Money(12345, 'RUB', 2), 'invoice:1'), operation_id='refund:1'
            )
        with self.assertRaises(UnsupportedCapability):
            await adapter.get(
                '123', binding=binding('cryptopay', subscription_id='sub:1'), invoice_operation_id='invoice:1'
            )
        with self.assertRaises(PermissionDenied):
            await adapter.get(
                '123', binding=binding('cryptopay', merchant_id='other'), invoice_operation_id='invoice:1'
            )
        self.assertEqual(transport.requests, [])
