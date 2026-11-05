"""HTTP safety contracts with an injected transport; no network access."""

import asyncio
import json
import unittest
from dataclasses import replace
from decimal import Decimal, localcontext

from telegram_patterns.errors import ValidationFailure, safe_error_report
from telegram_patterns.money import Money
from telegram_patterns.payment_ledger import PaymentBinding
from telegram_patterns.providers.http import (
    InvoiceRequest,
    ProviderHttpClient,
    ProviderHttpResponse,
    ProviderRateLimited,
    ProviderReadFailure,
    ProviderWriteUnknown,
    RefundRequest,
    amount_value,
    binding_reference,
    decode_json,
    encode_json,
    headers_lower,
    timestamp,
)


def binding(provider='yookassa', **changes):
    fields = dict(
        merchant_id='merchant:test',
        bot_id=100,
        user_id=200,
        order_id='order:1',
        provider=provider,
        amount=Money(12345, 'RUB', 2),
        allow_partial_refunds=True,
    )
    fields.update(changes)
    return PaymentBinding(**fields)


def response(data, *, status=200, **kwargs):
    return ProviderHttpResponse(status, encode_json(data), **kwargs)


class ScriptedTransport:
    def __init__(self, *results):
        self.results = list(results)
        self.requests = []

    async def send(self, request):
        self.requests.append(request)
        if not self.results:
            raise AssertionError('Unexpected extra HTTP attempt')
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class ProviderHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_failure_does_not_establish_write_absence(self):
        for result in (response({}, status=404), OSError('private-token'), response({}, status=500)):
            with self.subTest(result=type(result)):
                transport = ScriptedTransport(result)
                with self.assertRaises(ProviderReadFailure) as caught:
                    await ProviderHttpClient(transport).json('GET', 'https://api.example.com/status', {})
                report = safe_error_report(caught.exception, operation='read')
                self.assertEqual((report.outcome, report.recovery), ('read-failed', 'retry-read'))
                self.assertEqual(len(transport.requests), 1)
                self.assertNotIn('private-token', str(report.as_dict()))

    async def test_every_ambiguous_write_response_is_unknown_without_retry(self):
        results = [
            OSError('credential'),
            TimeoutError('card-data'),
            response({}, status=404),
            response({}, status=429),
            response({}, status=503),
            response({}, redirected=True),
            ProviderHttpResponse(200, b'{"x":1,"x":2}'),
            ProviderHttpResponse(200, b'bad'),
            ProviderHttpResponse(200, b'x' * 1025),
        ]
        for result in results:
            transport = ScriptedTransport(result)
            with self.subTest(result=result), self.assertRaises(ProviderWriteUnknown) as caught:
                await ProviderHttpClient(transport, max_response_bytes=1024).json(
                    'POST', 'https://api.example.com/payment', {'Authorization': 'secret'}, {'amount': '1.00'}
                )
            report = safe_error_report(caught.exception, operation='write')
            self.assertEqual((report.outcome, report.recovery), ('unknown', 'reconcile'))
            self.assertEqual(len(transport.requests), 1)
            self.assertNotIn('credential', str(report.as_dict()))

    async def test_read_429_has_only_bounded_retry_hint(self):
        for raw, expected in [
            ('12', 12),
            ('86400', 86400),
            ('86401', None),
            ('-1', None),
            ('9999999999999999', None),
            ('Wed, 21 Oct', None),
            ('١', None),
        ]:
            transport = ScriptedTransport(response({}, status=429, headers={'Retry-After': raw}))
            with self.assertRaises(ProviderRateLimited) as caught:
                await ProviderHttpClient(transport).json('GET', 'https://api.example.com/status', {})
            self.assertEqual(caught.exception.retry_after, expected)
            self.assertEqual(len(transport.requests), 1)

    async def test_timeout_is_enforced_on_actual_wait(self):
        class Hanging:
            async def send(self, _request):
                await asyncio.Event().wait()

        with self.assertRaises(ProviderWriteUnknown):
            await ProviderHttpClient(Hanging(), timeout_seconds=1).json('POST', 'https://api.example.com/', {}, {})

    async def test_cancellation_propagates_and_does_not_mean_remote_cancel(self):
        started = asyncio.Event()

        class Hanging:
            async def send(self, _request):
                started.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(ProviderHttpClient(Hanging()).json('POST', 'https://api.example.com/', {}, {}))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_request_contract_and_repr_hide_credentials_and_body(self):
        transport = ScriptedTransport(response({'ok': True}))
        await ProviderHttpClient(transport, timeout_seconds=2, max_response_bytes=2048).json(
            'POST',
            'https://api.example.com/pay',
            {'Authorization': 'Basic credentials'},
            {'email': 'buyer@example.com'},
        )
        request = transport.requests[0]
        self.assertEqual((request.timeout_seconds, request.max_response_bytes), (2, 2048))
        self.assertEqual(request.headers['authorization'], 'Basic credentials')
        self.assertNotIn('credentials', repr(request))
        self.assertNotIn('buyer@example.com', repr(request))
        self.assertNotIn('secret', repr(ProviderHttpResponse(200, b'secret', {'X-Secret': 'secret'})))

    def test_strict_json_and_exact_large_amount_ignore_decimal_context(self):
        with localcontext() as context:
            context.prec = 2
            raw = b'{"amount":90071992547409.91}'
            decoded = decode_json(raw)
            amount = amount_value(decoded['amount'], Money(0, 'RUB', 2), numeric=True)
            self.assertEqual(amount.minor_units, 9007199254740991)
            self.assertIn(b'90071992547409.91', encode_json({'amount': Decimal(amount.to_decimal())}))
        for raw in [b'{"a":1,"a":2}', b'{"a":NaN}', b'\xff', b'[' * 33 + b']' * 33]:
            with self.subTest(raw=raw), self.assertRaises(ValidationFailure):
                decode_json(raw)
        for amount in [Decimal('1e999999999'), Decimal('1e-999999999'), True, 1.1, Decimal('NaN')]:
            with self.subTest(amount=amount), self.assertRaises(ValidationFailure):
                amount_value(amount, Money(0, 'RUB', 2), numeric=True)

    def test_full_server_binding_and_operation_are_in_digest(self):
        original = binding()
        digest = binding_reference(original, 'invoice:1')
        self.assertEqual(len(digest), 64)
        for changed in [
            replace(original, user_id=201),
            replace(original, bot_id=101),
            replace(original, order_id='order:2'),
            replace(original, merchant_id='merchant:other'),
            replace(original, amount=Money(12344, 'RUB', 2)),
            replace(original, provider='platega'),
            replace(original, allow_partial_refunds=False),
        ]:
            self.assertNotEqual(binding_reference(changed, 'invoice:1'), digest)
        self.assertNotEqual(binding_reference(original, 'invoice:2'), digest)

    def test_validation_precedes_transport(self):
        for values in [{'timeout_seconds': 0}, {'timeout_seconds': True}, {'max_response_bytes': 100}]:
            with self.assertRaises(ValidationFailure):
                ProviderHttpClient(ScriptedTransport(), **values)
        with self.assertRaises(ValidationFailure):
            InvoiceRequest(binding(), 'test', 'http://insecure.example.com')
        with self.assertRaises(ValidationFailure):
            RefundRequest(binding(), 'charge', Money(12346, 'RUB', 2), 'invoice:1')
        with self.assertRaises(ValidationFailure):
            RefundRequest(binding(), 'charge', Money(1, 'USD', 2), 'invoice:1')
        with self.assertRaises(ValidationFailure):
            headers_lower({'X-Secret': 'one', 'x-secret': 'two'})
        with self.assertRaises(ValidationFailure):
            timestamp('2026-11-05T12:00:00')
        self.assertEqual(timestamp('2026-11-05T12:00:00Z'), 1793880000)
        self.assertEqual(
            json.loads(encode_json({'a': True, 'b': None, 'c': ['строка', 2]})),
            {'a': True, 'b': None, 'c': ['строка', 2]},
        )
