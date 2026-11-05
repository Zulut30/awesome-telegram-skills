"""Official v3 shape fixtures; captured and refunded states require authenticated GET."""

import asyncio
import base64
import json
import unittest

from test_provider_http import ScriptedTransport, binding, response

from telegram_patterns.errors import PermissionDenied, UnsupportedCapability, ValidationFailure, safe_error_report
from telegram_patterns.money import Money
from telegram_patterns.providers import (
    InvoiceRequest,
    ProviderWriteUnknown,
    RefundRequest,
    YooKassaAdapter,
    YooKassaCreateOptions,
    YooKassaPeerPolicy,
    binding_reference,
)


def payment(order=None, **changes):
    order = order or binding()
    data = dict(
        id='payment-1',
        status='succeeded',
        paid=True,
        test=True,
        amount={'value': order.amount.to_decimal(), 'currency': order.amount.currency},
        recipient={'account_id': 'shop-1', 'gateway_id': 'gateway-1'},
        metadata={'telegram_binding': binding_reference(order, 'invoice:1'), 'telegram_operation': 'invoice:1'},
        captured_at='2026-11-05T12:00:00Z',
        confirmation={'type': 'redirect', 'confirmation_url': 'https://yoomoney.ru/checkout/payments/v2/1'},
    )
    data.update(changes)
    return data


def refund(**changes):
    data = dict(
        id='refund-1',
        payment_id='payment-1',
        status='succeeded',
        amount={'value': '23.45', 'currency': 'RUB'},
        created_at='2026-11-05T13:00:00Z',
    )
    data.update(changes)
    return data


def adapter(transport, **changes):
    options = dict(merchant_id='merchant:test', shop_id='shop-1', secret_key='fixture-key', test=True)
    options.update(changes)
    return YooKassaAdapter(transport, **options)


class YooKassaTests(unittest.IsolatedAsyncioTestCase):
    async def test_refund_write_response_binding_failure_is_unknown(self):
        request = RefundRequest(binding(), 'payment-1', Money(2345, 'RUB', 2), 'invoice:1')
        for data in [[], refund(payment_id='other'), refund(amount={'value': '23.44', 'currency': 'RUB'})]:
            transport = ScriptedTransport(response(payment()), response(data))
            with self.assertRaises(ProviderWriteUnknown):
                await adapter(transport).refund(request, operation_id='refund:1')
            self.assertEqual([item.method for item in transport.requests], ['GET', 'POST'])

    def test_invalid_peer_policy_and_shop_configuration_fail_closed(self):
        for networks in ((), ('0.0.0.1/24',), ('not-an-address',)):
            with self.assertRaises(ValidationFailure):
                YooKassaPeerPolicy(networks)
        with self.assertRaises(ValidationFailure):
            adapter(ScriptedTransport(), test=1)

    async def test_create_exact_strings_basic_auth_stable_scoped_key_and_one_stage_capture(self):
        transport = ScriptedTransport(response(payment(status='pending', paid=False)))
        created = await adapter(transport).create(
            InvoiceRequest(binding(), 'Order', 'https://shop.example.com/return'), operation_id='invoice:1'
        )
        self.assertEqual(created.native_state, 'pending')
        request = transport.requests[0]
        self.assertEqual(request.url, 'https://api.yookassa.ru/v3/payments')
        self.assertEqual(request.headers['authorization'], 'Basic ' + base64.b64encode(b'shop-1:fixture-key').decode())
        self.assertEqual(request.headers['idempotence-key'], binding_reference(binding(), 'invoice:1'))
        wire = json.loads(request.body)
        self.assertIs(wire['capture'], True)
        self.assertEqual(wire['amount'], {'value': '123.45', 'currency': 'RUB'})
        self.assertEqual(wire['metadata']['telegram_binding'], binding_reference(binding(), 'invoice:1'))
        self.assertNotIn('fixture-key', repr(adapter(transport)))
        self.assertNotIn('receipt', wire)  # Tax receipt integration is an explicit merchant-owned boundary.

    async def test_current_get_is_required_and_waiting_paid_flag_never_grants(self):
        for state, paid in [('pending', False), ('waiting_for_capture', True), ('canceled', False), ('future', True)]:
            transport = ScriptedTransport(response(payment(status=state, paid=paid)))
            with self.subTest(state=state), self.assertRaises(UnsupportedCapability):
                await adapter(transport).payment_event(
                    binding(), 'payment-1', invoice_operation_id='invoice:1', evidence_ref='proof:1'
                )
            self.assertEqual(transport.requests[0].method, 'GET')
        event = await adapter(ScriptedTransport(response(payment()))).payment_event(
            binding(), 'payment-1', invoice_operation_id='invoice:1', evidence_ref='proof:1'
        )
        self.assertEqual(
            (event.kind, event.charge_id, event.paid_at, event.amount),
            ('paid', 'payment-1', 1793880000, Money(12345, 'RUB', 2)),
        )

    async def test_payee_test_amount_metadata_and_id_binding_are_checked(self):
        for changes in [
            dict(test=False),
            dict(test=1),
            dict(recipient={'account_id': 'attacker'}),
            dict(amount={'value': '123.46', 'currency': 'RUB'}),
            dict(amount={'value': '123.45', 'currency': 'USD'}),
            dict(id='other-payment'),
            dict(metadata={'telegram_binding': 'other', 'telegram_operation': 'invoice:1'}),
            dict(
                metadata={
                    'telegram_binding': binding_reference(binding(), 'invoice:1'),
                    'telegram_operation': 'invoice:2',
                }
            ),
            dict(paid=False),
        ]:
            with self.subTest(changes=changes), self.assertRaises(PermissionDenied):
                await adapter(ScriptedTransport(response(payment(**changes)))).payment_event(
                    binding(), 'payment-1', invoice_operation_id='invoice:1', evidence_ref='proof:1'
                )

    def test_no_fabricated_hmac_or_forwarded_header_auth(self):
        client = adapter(ScriptedTransport())
        body = json.dumps(
            {'type': 'notification', 'event': 'payment.succeeded', 'object': {'id': 'payment-1', 'status': 'succeeded'}}
        ).encode()
        self.assertIsNone(client.verify_event(body, {'X-Signature': 'anything', 'X-Forwarded-For': '185.71.76.1'}))
        self.assertIsNone(client.verify_notification(body, peer_ip='127.0.0.1'))
        self.assertEqual(client.verify_notification(body, peer_ip='185.71.76.1').provider_id, 'payment-1')
        policy = YooKassaPeerPolicy()
        self.assertTrue(policy.allows('2a02:5180::1'))
        self.assertFalse(policy.allows('185.71.76.32'))
        self.assertFalse(policy.allows('185.71.76.1, 127.0.0.1'))
        self.assertFalse(policy.allows('invalid'))

    async def test_refund_post_pending_is_not_final_and_has_distinct_stable_key(self):
        transport = ScriptedTransport(response(payment()), response(refund(status='pending')))
        request = RefundRequest(binding(), 'payment-1', Money(2345, 'RUB', 2), 'invoice:1')
        pending = await adapter(transport).refund(request, operation_id='refund:1')
        self.assertEqual((pending.native_state, pending.provider_id), ('pending', 'refund-1'))
        self.assertEqual([item.method for item in transport.requests], ['GET', 'POST'])
        post = transport.requests[1]
        self.assertEqual(post.url, 'https://api.yookassa.ru/v3/refunds')
        self.assertEqual(
            json.loads(post.body), {'payment_id': 'payment-1', 'amount': {'value': '23.45', 'currency': 'RUB'}}
        )
        self.assertEqual(post.headers['idempotence-key'], binding_reference(binding(), 'refund:1'))
        self.assertNotEqual(post.headers['idempotence-key'], binding_reference(binding(), 'invoice:1'))
        with self.assertRaises(UnsupportedCapability):
            await adapter(ScriptedTransport(response(refund(status='pending')), response(payment()))).refund_event(
                request, 'refund-1', operation_id='refund:1', evidence_ref='proof:2'
            )

    async def test_refund_requires_both_native_refund_and_bound_payment_get(self):
        request = RefundRequest(binding(), 'payment-1', Money(2345, 'RUB', 2), 'invoice:1')
        transport = ScriptedTransport(response(refund()), response(payment()))
        event = await adapter(transport).refund_event(
            request, 'refund-1', operation_id='refund:1', evidence_ref='proof:2'
        )
        self.assertEqual(
            (event.kind, event.charge_id, event.refund_id, event.amount, event.operation_id),
            ('refunded', 'payment-1', 'refund-1', Money(2345, 'RUB', 2), 'refund:1'),
        )
        self.assertEqual(
            [item.url for item in transport.requests],
            ['https://api.yookassa.ru/v3/refunds/refund-1', 'https://api.yookassa.ru/v3/payments/payment-1'],
        )
        for changes in [
            dict(payment_id='other'),
            dict(id='other-refund'),
            dict(amount={'value': '23.44', 'currency': 'RUB'}),
            dict(amount={'value': '23.45', 'currency': 'USD'}),
        ]:
            with self.subTest(changes=changes), self.assertRaises(PermissionDenied):
                await adapter(ScriptedTransport(response(refund(**changes)))).refund_event(
                    request, 'refund-1', operation_id='refund:1', evidence_ref='proof:2'
                )
        with self.assertRaises(PermissionDenied):
            await adapter(
                ScriptedTransport(response(refund()), response(payment(recipient={'account_id': 'other'})))
            ).refund_event(request, 'refund-1', operation_id='refund:1', evidence_ref='proof:2')

    async def test_invalid_write_success_and_lost_reply_are_unknown_without_second_post(self):
        for result in [TimeoutError('private-body'), response(payment(test=False)), response([])]:
            transport = ScriptedTransport(result)
            with self.assertRaises(ProviderWriteUnknown):
                await adapter(transport).create(
                    InvoiceRequest(binding(), 'Order', 'https://shop.example.com/'), operation_id='invoice:1'
                )
            self.assertEqual(len(transport.requests), 1)

    async def test_subscriptions_remain_explicitly_unsupported(self):
        transport = ScriptedTransport()
        with self.assertRaises(UnsupportedCapability):
            await adapter(transport).get(
                'payment-1', binding=binding(subscription_id='sub:1'), invoice_operation_id='invoice:1'
            )
        self.assertEqual(transport.requests, [])

    async def test_two_stage_create_is_explicit_and_option_is_exact_boolean(self):
        transport = ScriptedTransport(response(payment(status='pending', paid=False)))
        await adapter(transport).create(
            InvoiceRequest(binding(), 'Two-stage order', 'https://shop.example.com/'),
            operation_id='invoice:1',
            options=YooKassaCreateOptions(capture=False),
        )
        self.assertIs(json.loads(transport.requests[0].body)['capture'], False)
        for invalid in (0, 1, None, 'false'):
            with self.assertRaises(ValidationFailure):
                YooKassaCreateOptions(capture=invalid)
        no_http = ScriptedTransport()
        with self.assertRaises(ValidationFailure):
            await adapter(no_http).create(
                InvoiceRequest(binding(), 'Order', 'https://shop.example.com/'),
                operation_id='invoice:1',
                options={'capture': False},
            )
        self.assertEqual(no_http.requests, [])

    async def test_full_capture_preflight_one_post_then_independent_final_get(self):
        transport = ScriptedTransport(
            response(payment(status='waiting_for_capture')), response(payment()), response(payment())
        )
        client = adapter(transport)
        key = client.capture_key(binding(), 'payment-1', invoice_operation_id='invoice:1', operation_id='capture:1')
        result = await client.capture(
            binding(), 'payment-1', invoice_operation_id='invoice:1', operation_id='capture:1'
        )
        self.assertEqual((result.native_state, result.paid_at), ('succeeded', 1793880000))
        self.assertEqual([item.method for item in transport.requests], ['GET', 'POST', 'GET'])
        post = transport.requests[1]
        self.assertEqual(post.url, 'https://api.yookassa.ru/v3/payments/payment-1/capture')
        self.assertEqual(json.loads(post.body), {'amount': {'value': '123.45', 'currency': 'RUB'}})
        self.assertEqual(post.headers['idempotence-key'], key)
        self.assertEqual(len(key), 64)
        self.assertNotEqual(key, binding_reference(binding(), 'capture:1'))
        self.assertNotEqual(key, binding_reference(binding(), 'invoice:1'))
        self.assertNotEqual(key, binding_reference(binding(), 'refund:1'))
        self.assertEqual(
            key, client.capture_key(binding(), 'payment-1', invoice_operation_id='invoice:1', operation_id='capture:1')
        )
        for changed, native_id, invoice_id, capture_id in [
            (binding(user_id=201), 'payment-1', 'invoice:1', 'capture:1'),
            (binding(), 'payment-2', 'invoice:1', 'capture:1'),
            (binding(), 'payment-1', 'invoice:2', 'capture:1'),
            (binding(), 'payment-1', 'invoice:1', 'capture:2'),
        ]:
            self.assertNotEqual(
                key, client.capture_key(changed, native_id, invoice_operation_id=invoice_id, operation_id=capture_id)
            )

    async def test_capture_preflight_denies_nonheld_or_unpaid_and_changed_binding_before_post(self):
        for state in ('pending', 'succeeded', 'canceled', 'future-state'):
            transport = ScriptedTransport(response(payment(status=state)))
            with self.subTest(state=state), self.assertRaises(UnsupportedCapability):
                await adapter(transport).capture(
                    binding(), 'payment-1', invoice_operation_id='invoice:1', operation_id='capture:1'
                )
            self.assertEqual([item.method for item in transport.requests], ['GET'])
        cases = [
            dict(paid=False),
            dict(test=False),
            dict(id='another-payment'),
            dict(recipient={'account_id': 'other-shop'}),
            dict(amount={'value': '100.00', 'currency': 'RUB'}),
            dict(metadata={'telegram_binding': 'other-order', 'telegram_operation': 'invoice:1'}),
            dict(
                metadata={
                    'telegram_binding': binding_reference(binding(), 'invoice:1'),
                    'telegram_operation': 'invoice:2',
                }
            ),
        ]
        for changes in cases:
            transport = ScriptedTransport(response(payment(status='waiting_for_capture', **changes)))
            expected = UnsupportedCapability if changes == {'paid': False} else PermissionDenied
            with self.subTest(changes=changes), self.assertRaises(expected):
                await adapter(transport).capture(
                    binding(), 'payment-1', invoice_operation_id='invoice:1', operation_id='capture:1'
                )
            self.assertEqual([item.method for item in transport.requests], ['GET'])

    async def test_capture_post_success_is_not_proof_and_unsettled_or_canceled_get_never_grants(self):
        cases = [
            payment(status='pending', paid=False),
            payment(status='waiting_for_capture'),
            payment(status='canceled', paid=False),
            payment(status='future-state'),
            payment(captured_at=None),
            payment(paid=False),
        ]
        for current in cases:
            transport = ScriptedTransport(
                response(payment(status='waiting_for_capture')), response(payment()), response(current)
            )
            with self.subTest(state=current['status']), self.assertRaises(ProviderWriteUnknown):
                await adapter(transport).capture(
                    binding(), 'payment-1', invoice_operation_id='invoice:1', operation_id='capture:1'
                )
            self.assertEqual([item.method for item in transport.requests], ['GET', 'POST', 'GET'])

    async def test_capture_write_and_followup_read_failures_are_unknown_without_another_post(self):
        from telegram_patterns.providers import ProviderHttpResponse

        for failed in (
            TimeoutError('lost-reply'),
            OSError('disconnect'),
            response({}, status=400),  # Authorization can be canceled after the preflight GET.
            response({}, status=429),
            response({}, status=500),
            response(payment(id='wrong-payment')),
            response(payment(amount={'value': '1.00', 'currency': 'RUB'})),
            ProviderHttpResponse(200, b'{"status":'),
        ):
            transport = ScriptedTransport(response(payment(status='waiting_for_capture')), failed)
            with self.assertRaises(ProviderWriteUnknown) as caught:
                await adapter(transport).capture(
                    binding(), 'payment-1', invoice_operation_id='invoice:1', operation_id='capture:1'
                )
            self.assertEqual([item.method for item in transport.requests], ['GET', 'POST'])
            self.assertEqual(safe_error_report(caught.exception, operation='write').outcome, 'unknown')
        for failed in (TimeoutError('read-timeout'), response({}, status=404), response(payment(test=False))):
            transport = ScriptedTransport(
                response(payment(status='waiting_for_capture')), response(payment(status='pending', paid=False)), failed
            )
            with self.assertRaises(ProviderWriteUnknown):
                await adapter(transport).capture(
                    binding(), 'payment-1', invoice_operation_id='invoice:1', operation_id='capture:1'
                )
            self.assertEqual([item.method for item in transport.requests], ['GET', 'POST', 'GET'])

    async def test_capture_task_cancellation_propagates_after_write_started(self):
        started = asyncio.Event()

        class HangingAfterPost:
            def __init__(self):
                self.requests = []

            async def send(self, request):
                self.requests.append(request)
                if request.method == 'GET':
                    return response(payment(status='waiting_for_capture'))
                started.set()
                await asyncio.Event().wait()

        transport = HangingAfterPost()
        task = asyncio.create_task(
            adapter(transport).capture(
                binding(), 'payment-1', invoice_operation_id='invoice:1', operation_id='capture:1'
            )
        )
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual([item.method for item in transport.requests], ['GET', 'POST'])
