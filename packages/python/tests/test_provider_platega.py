"""Platega's current published camelCase schema and pending refund semantics."""

import json
import unittest
from decimal import Decimal, localcontext

from test_provider_http import ScriptedTransport, binding, response

from telegram_patterns.errors import PermissionDenied, UnsupportedCapability, ValidationFailure
from telegram_patterns.money import Money
from telegram_patterns.providers import (
    InvoiceRequest,
    PlategaAdapter,
    ProviderWriteUnknown,
    RefundRequest,
    binding_reference,
)


def transaction(order=None, **changes):
    order = order or binding('platega')
    data = dict(
        id='transaction-1',
        status='CONFIRMED',
        mechantId='native-merchant',
        paymentDetails={'amount': Decimal(order.amount.to_decimal()), 'currency': order.amount.currency},
        payload=binding_reference(order, 'invoice:1'),
    )
    data.update(changes)
    return data


def callback(**changes):
    data = dict(
        id='transaction-1',
        status='PARTIALLY_REFUNDED',
        amount=Decimal('123.45'),
        currency='RUB',
        payload=binding_reference(binding('platega'), 'invoice:1'),
        refundId='refund-1',
        refundAmount=Decimal('23.45'),
        refundStatus='Succeeded',
    )
    data.update(changes)
    from telegram_patterns.providers.http import encode_json

    return encode_json(data)


HEADERS = {'X-MerchantId': 'native-merchant', 'X-Secret': 'fixture-secret'}


def adapter(transport):
    return PlategaAdapter(
        transport,
        merchant_id='merchant:test',
        native_merchant_id='native-merchant',
        secret='fixture-secret',
        payment_method=2,
    )


def preflight(**changes):
    data = dict(supported=True, partialSupported=True, totalDeductUsdt=Decimal('1.23'), penaltyUsdt=Decimal('0.01'))
    data.update(changes)
    return data


def accepted(**changes):
    data = dict(transactionId='transaction-1', accepted=True, manualControlRequired=False, refundOperationId='refund-1')
    data.update(changes)
    return data


class PlategaTests(unittest.IsolatedAsyncioTestCase):
    async def test_invoice_reconciliation_is_not_payment_and_unknown_state_is_retained(self):
        event = await adapter(ScriptedTransport(response(transaction(status='FUTURE_STATE')))).invoice_event(
            binding('platega'), 'transaction-1', invoice_operation_id='invoice:1', evidence_ref='proof:created'
        )
        self.assertEqual(
            (event.kind, event.provider_state, event.provider_ref), ('invoice-created', 'FUTURE_STATE', 'transaction-1')
        )
        self.assertIsNone(event.charge_id)

    async def test_invalid_create_and_refund_success_bodies_are_unknown(self):
        for data in [[], {'transactionId': 'transaction-1', 'merchantId': 'other', 'status': 'PENDING'}]:
            with self.assertRaises(ProviderWriteUnknown):
                await adapter(ScriptedTransport(response(data))).create(
                    InvoiceRequest(binding('platega'), 'Order', 'https://shop.example.com/'),
                    operation_id='invoice:1',
                    customer_email='buyer@example.com',
                )
        request = RefundRequest(binding('platega'), 'transaction-1', Money(2345, 'RUB', 2), 'invoice:1')
        for data in [[], accepted(transactionId='other'), accepted(accepted=1), accepted(manualControlRequired=None)]:
            transport = ScriptedTransport(response(transaction()), response(preflight()), response(data))
            with self.assertRaises(ProviderWriteUnknown):
                await adapter(transport).refund(request, operation_id='refund:1', approve_cost=lambda _: True)
            self.assertEqual(len(transport.requests), 3)

    async def test_malformed_preflight_and_customer_metadata_stop_before_write(self):
        request = RefundRequest(binding('platega'), 'transaction-1', Money(2345, 'RUB', 2), 'invoice:1')
        from telegram_patterns.providers import ProviderHttpResponse

        cases = [
            response(preflight(supported=1)),
            ProviderHttpResponse(
                200, b'{"supported":true,"partialSupported":true,"totalDeductUsdt":1e999999999,"penaltyUsdt":0}'
            ),
            ProviderHttpResponse(
                200, b'{"supported":true,"partialSupported":true,"totalDeductUsdt":1.23,"penaltyUsdt":-0.01}'
            ),
        ]
        for result in cases:
            transport = ScriptedTransport(response(transaction()), result)
            with self.assertRaises(ValidationFailure):
                await adapter(transport).refund(request, operation_id='refund:1', approve_cost=lambda _: True)
            self.assertEqual(len(transport.requests), 2)
        for email in ('missing-at', 'buyer\x00@example.com'):
            transport = ScriptedTransport()
            with self.assertRaises(ValidationFailure):
                await adapter(transport).create(
                    InvoiceRequest(binding('platega'), 'Order', 'https://shop.example.com/'),
                    operation_id='invoice:1',
                    customer_email=email,
                )
            self.assertEqual(transport.requests, [])

    async def test_create_current_case_exact_numeric_amount_and_required_metadata(self):
        order = binding('platega', amount=Money(9007199254740991, 'RUB', 2))
        transport = ScriptedTransport(
            response(
                dict(
                    transactionId='transaction-1',
                    merchantId='native-merchant',
                    status='PENDING',
                    redirect='https://pay.platega.io/payment/1',
                    paymentDetails='90071992547409.91 RUB',
                )
            )
        )
        with localcontext() as context:
            context.prec = 2
            created = await adapter(transport).create(
                InvoiceRequest(order, 'Order', 'https://shop.example.com/'),
                operation_id='invoice:1',
                customer_email='buyer@example.com',
            )
        self.assertEqual(created.native_state, 'PENDING')
        wire = transport.requests[0]
        self.assertEqual(wire.url, 'https://app.platega.io/transaction/process')
        self.assertIn(b'"amount":90071992547409.91', wire.body)
        data = json.loads(wire.body, parse_float=Decimal)
        self.assertEqual(data['paymentDetails']['amount'], Decimal('90071992547409.91'))
        self.assertEqual(data['metadata'], {'userId': '200', 'user_email': 'buyer@example.com'})
        self.assertEqual(data['payload'], binding_reference(order, 'invoice:1'))
        self.assertNotIn('id', data)
        self.assertNotIn('idempotency-key', wire.headers)
        self.assertNotIn('fixture-secret', repr(adapter(transport)))

    async def test_get_retains_exact_published_mechant_id_typo(self):
        transport = ScriptedTransport(response(transaction()))
        status = await adapter(transport).get(
            'transaction-1', binding=binding('platega'), invoice_operation_id='invoice:1'
        )
        self.assertEqual((status.native_state, status.paid_at), ('CONFIRMED', None))
        wrong = transaction()
        wrong['merchantId'] = wrong.pop('mechantId')
        with self.assertRaises(PermissionDenied):
            await adapter(ScriptedTransport(response(wrong))).get(
                'transaction-1', binding=binding('platega'), invoice_operation_id='invoice:1'
            )

    def test_callback_headers_not_client_redirect_or_fabricated_hmac(self):
        client = adapter(ScriptedTransport())
        self.assertEqual(client.verify_event(callback(), HEADERS).refund_id, 'refund-1')
        self.assertIsNone(client.verify_event(callback(), {'X-MerchantId': 'other', 'X-Secret': 'fixture-secret'}))
        self.assertIsNone(client.verify_event(callback(), {'X-MerchantId': 'native-merchant', 'X-Secret': 'wrong'}))
        self.assertIsNone(client.verify_event(callback(), {'X-Signature': 'fake'}))
        with self.assertRaises(ValidationFailure):
            client.verify_event(callback(), {**HEADERS, 'x-secret': 'ambiguous'})

    async def test_missing_native_paid_time_is_explicit_unsupported_without_fake_observation_time(self):
        transport = ScriptedTransport()
        with self.assertRaises(UnsupportedCapability):
            await adapter(transport).payment_event(
                binding('platega'), 'transaction-1', invoice_operation_id='invoice:1', evidence_ref='proof:1'
            )
        self.assertEqual(transport.requests, [])

    async def test_refund_preflight_cost_approval_and_partial_idempotency(self):
        transport = ScriptedTransport(response(transaction()), response(preflight()), response(accepted()))
        request = RefundRequest(binding('platega'), 'transaction-1', Money(2345, 'RUB', 2), 'invoice:1')
        quotes = []

        def approve(quote):
            quotes.append(quote)
            return quote.total_deduct_usdt == Decimal('1.23')

        result = await adapter(transport).refund(request, operation_id='refund:1', approve_cost=approve)
        self.assertEqual((result.native_state, result.provider_id), ('accepted', 'refund-1'))
        self.assertEqual(quotes[0].penalty_usdt, Decimal('0.01'))
        self.assertEqual(
            transport.requests[1].url, 'https://app.platega.io/transaction/transaction-1/cancel-supported?amount=23.45'
        )
        post = transport.requests[2]
        self.assertEqual(post.url, 'https://app.platega.io/transaction/transaction-1/cancel-partial')
        self.assertEqual(post.body, b'{"amount":23.45}')
        self.assertEqual(post.headers['idempotency-key'], binding_reference(binding('platega'), 'refund:1'))
        self.assertNotIn('idempotence-key', post.headers)

    async def test_full_refund_has_no_body_no_amount_and_manual_review_is_not_final(self):
        transport = ScriptedTransport(
            response(transaction()),
            response(preflight()),
            response(accepted(accepted=False, manualControlRequired=True)),
        )
        request = RefundRequest(binding('platega'), 'transaction-1', Money(12345, 'RUB', 2), 'invoice:1')
        result = await adapter(transport).refund(request, operation_id='refund:full', approve_cost=lambda _: True)
        self.assertEqual(
            (result.native_state, result.accepted, result.manual_control_required),
            ('manual-control-required', False, True),
        )
        self.assertEqual(transport.requests[2].url, 'https://app.platega.io/transaction/transaction-1/cancel')
        self.assertIsNone(transport.requests[2].body)
        self.assertNotIn('idempotency-key', transport.requests[2].headers)

    async def test_unsupported_or_unauthorized_cost_stops_before_remote_write(self):
        request = RefundRequest(binding('platega'), 'transaction-1', Money(2345, 'RUB', 2), 'invoice:1')
        for quote, approval, error in [
            (preflight(supported=False), True, UnsupportedCapability),
            (preflight(partialSupported=False), True, UnsupportedCapability),
            (preflight(), 1, PermissionDenied),
            (preflight(), False, PermissionDenied),
        ]:
            transport = ScriptedTransport(response(transaction()), response(quote))
            with self.assertRaises(error):
                await adapter(transport).refund(request, operation_id='refund:1', approve_cost=lambda _: approval)
            self.assertEqual([item.method for item in transport.requests], ['GET', 'GET'])

    async def test_final_refund_needs_native_id_amount_success_and_current_bound_status(self):
        request = RefundRequest(binding('platega'), 'transaction-1', Money(2345, 'RUB', 2), 'invoice:1')
        event = await adapter(ScriptedTransport(response(transaction(status='PARTIALLY_REFUNDED')))).refund_event(
            request, 'refund-1', callback(), HEADERS, operation_id='refund:1', evidence_ref='proof:2'
        )
        self.assertEqual((event.kind, event.refund_id, event.amount), ('refunded', 'refund-1', request.amount))
        cases = [
            ({'refundId': 'other'}, PermissionDenied),
            ({'refundStatus': 'Declined'}, UnsupportedCapability),
            ({'refundAmount': Decimal('23.44')}, PermissionDenied),
            ({'payload': 'other'}, PermissionDenied),
            ({'currency': 'USD'}, PermissionDenied),
            ({'amount': Decimal('123.46')}, PermissionDenied),
        ]
        for changes, error in cases:
            with self.subTest(changes=changes), self.assertRaises(error):
                await adapter(ScriptedTransport()).refund_event(
                    request, 'refund-1', callback(**changes), HEADERS, operation_id='refund:1', evidence_ref='proof:2'
                )
        with self.assertRaises(UnsupportedCapability):
            await adapter(ScriptedTransport(response(transaction()))).refund_event(
                request, 'refund-1', callback(), HEADERS, operation_id='refund:1', evidence_ref='proof:2'
            )

    async def test_wrong_binding_and_create_lost_reply_are_not_silently_accepted(self):
        for changes in [
            dict(mechantId='other'),
            dict(id='other'),
            dict(payload='other'),
            dict(paymentDetails={'amount': Decimal('123.46'), 'currency': 'RUB'}),
        ]:
            with self.assertRaises(PermissionDenied):
                await adapter(ScriptedTransport(response(transaction(**changes)))).get(
                    'transaction-1', binding=binding('platega'), invoice_operation_id='invoice:1'
                )
        transport = ScriptedTransport(TimeoutError('lost-reply'))
        with self.assertRaises(ProviderWriteUnknown):
            await adapter(transport).create(
                InvoiceRequest(binding('platega'), 'Order', 'https://shop.example.com/'),
                operation_id='invoice:1',
                customer_email='buyer@example.com',
            )
        self.assertEqual(len(transport.requests), 1)
