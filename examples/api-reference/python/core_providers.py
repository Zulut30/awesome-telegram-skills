"""Локальные HTTP-фикстуры провайдеров: DTO и уведомление не выдают доступ."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any

from telegram_patterns import (
    AsyncTransport,
    CryptoPayAdapter,
    InvoiceRequest,
    Money,
    PaymentBinding,
    PlategaAdapter,
    PlategaRefundSupport,
    ProviderHttpRequest,
    ProviderHttpResponse,
    ProviderInvoice,
    ProviderNotification,
    ProviderRateLimited,
    ProviderReadFailure,
    ProviderRefund,
    ProviderWriteUnknown,
    RefundRequest,
    YooKassaAdapter,
    YooKassaCreateOptions,
    YooKassaPeerPolicy,
    binding_reference,
)


def response(value: object, status: int = 200) -> ProviderHttpResponse:
    return ProviderHttpResponse(status, json.dumps(value).encode('utf-8'))


class FixtureHTTP:
    """Очередь ответов в памяти; каждый запрос использует публичный контракт, без сети."""

    def __init__(self, *replies: ProviderHttpResponse) -> None:
        self.replies = list(replies)
        self.requests: list[ProviderHttpRequest] = []

    async def send(self, request: ProviderHttpRequest) -> ProviderHttpResponse:
        assert request.url.startswith(('https://api.yookassa.ru/', 'https://testnet-pay.crypt.bot/',
                                       'https://app.platega.io/'))
        assert request.timeout_seconds <= 60 and request.max_response_bytes <= 1048576
        self.requests.append(request)
        if not self.replies:
            raise AssertionError('Unexpected local HTTP request')
        return self.replies.pop(0)


def order(provider: str) -> PaymentBinding:
    return PaymentBinding('merchant:fixture', 100, 42, 'order:fixture', provider,
                          Money(1000, 'RUB', 2), allow_partial_refunds=True)


def payment(binding: PaymentBinding, state: str) -> dict[str, Any]:
    native: dict[str, Any] = {
        'id': 'payment-fixture', 'status': state, 'paid': state != 'pending', 'test': True,
        'amount': {'value': binding.amount.to_decimal(), 'currency': binding.amount.currency},
        'recipient': {'account_id': 'shop-fixture'},
        'metadata': {'telegram_binding': binding_reference(binding, 'invoice:1'),
                     'telegram_operation': 'invoice:1'},
    }
    if state == 'succeeded':
        native['captured_at'] = '2026-11-05T12:00:00Z'
    return native


def yookassa(transport: AsyncTransport[ProviderHttpRequest, ProviderHttpResponse]) -> YooKassaAdapter:
    return YooKassaAdapter(transport, merchant_id='merchant:fixture', shop_id='shop-fixture',
                          secret_key='fixture-only-not-a-secret', test=True)


async def main() -> None:
    binding = order('yookassa')
    held = payment(binding, 'waiting_for_capture')
    paid = payment(binding, 'succeeded')
    refund = {'id': 'refund-fixture', 'payment_id': 'payment-fixture', 'status': 'pending',
              'amount': {'value': '2.00', 'currency': 'RUB'}}
    local = FixtureHTTP(response(held), response(held), response(paid), response(paid),
                        response(paid), response(paid), response(refund))
    transport: AsyncTransport[ProviderHttpRequest, ProviderHttpResponse] = local
    adapter = yookassa(transport)
    created: ProviderInvoice = await adapter.create(
        InvoiceRequest(binding, 'Fixture order', 'https://example.com/return'),
        operation_id='invoice:1', options=YooKassaCreateOptions(capture=False))
    assert created.native_state == 'waiting_for_capture' and created.paid_at is None
    capture_key = adapter.capture_key(binding, created.provider_id, invoice_operation_id='invoice:1',
                                      operation_id='capture:1')
    captured = await adapter.capture(binding, created.provider_id, invoice_operation_id='invoice:1',
                                     operation_id='capture:1')
    assert captured.native_state == 'succeeded' and captured.paid_at == 1793880000
    assert local.requests[2].headers['idempotence-key'] == capture_key
    trusted_observation = await adapter.payment_event(binding, created.provider_id,
                                                      invoice_operation_id='invoice:1',
                                                      evidence_ref='fixture:get-payment')
    assert trusted_observation.kind == 'paid' and trusted_observation.amount == binding.amount
    pending: ProviderRefund = await adapter.refund(
        RefundRequest(binding, created.provider_id, Money(200, 'RUB', 2), 'invoice:1'),
        operation_id='refund:1')
    assert pending.native_state == 'pending'  # Receipt acceptance is not a completed refund.
    policy = YooKassaPeerPolicy()
    assert policy.allows('185.71.76.1') and not policy.allows('127.0.0.1')
    body = json.dumps({'type': 'notification', 'event': 'payment.succeeded',
                       'object': {'id': created.provider_id, 'status': 'succeeded'}}).encode()
    hint: ProviderNotification | None = adapter.verify_notification(body, peer_ip='185.71.76.1')
    assert hint is not None and hint.provider_id == created.provider_id
    assert adapter.verify_notification(body, peer_ip='127.0.0.1') is None

    crypto_order = order('cryptopay')
    invoice = {'invoice_id': 123, 'status': 'paid', 'currency_type': 'fiat', 'fiat': 'RUB',
               'amount': '10.00', 'payload': binding_reference(crypto_order, 'invoice:1'),
               'paid_at': '2026-11-05T12:00:00Z'}
    crypto_http = FixtureHTTP(response({'ok': True, 'result': [invoice]}))
    crypto = CryptoPayAdapter(crypto_http, merchant_id=crypto_order.merchant_id, token='fixture-only-token')
    crypto_paid = await crypto.payment_event(crypto_order, '123', invoice_operation_id='invoice:1',
                                             evidence_ref='fixture:crypto-get')
    assert crypto_paid.charge_id == '123' and crypto_paid.amount == crypto_order.amount
    # Synthetic local HMAC demonstrates the wire contract, not a real provider identity.
    raw = json.dumps({'update_id': 7, 'request_date': '2026-11-05T12:00:00Z',
                      'update_type': 'invoice_paid', 'payload': invoice}).encode()
    signature = hmac.new(hashlib.sha256(b'fixture-only-token').digest(), raw, hashlib.sha256).hexdigest()
    crypto_hint = crypto.verify_event(raw, {'crypto-pay-api-signature': signature})
    assert crypto_hint is not None and crypto_hint.provider_id == '123'
    assert crypto.verify_event(raw + b' ', {'crypto-pay-api-signature': signature}) is None

    platega_order = order('platega')
    transaction = {'id': 'transaction-fixture', 'status': 'CONFIRMED', 'mechantId': 'native-merchant',
                   'paymentDetails': {'amount': 10, 'currency': 'RUB'},
                   'payload': binding_reference(platega_order, 'invoice:1')}
    platega_http = FixtureHTTP(response(transaction), response({'supported': True, 'partialSupported': True,
                                                               'totalDeductUsdt': 1, 'penaltyUsdt': 0}))
    platega = PlategaAdapter(platega_http, merchant_id=platega_order.merchant_id,
                            native_merchant_id='native-merchant', secret='fixture-only-secret', payment_method=2)
    support: PlategaRefundSupport = await platega.refund_support(
        RefundRequest(platega_order, 'transaction-fixture', Money(200, 'RUB', 2), 'invoice:1'))
    assert support.supported and support.partial_supported and support.total_deduct_usdt == 1
    # No native paid timestamp is invented to grant access from this Platega snapshot.

    limited_http = FixtureHTTP(ProviderHttpResponse(429, b'{}', {'Retry-After': '7'}))
    try:
        await yookassa(limited_http).get(created.provider_id, binding=binding, invoice_operation_id='invoice:1')
    except ProviderRateLimited as limited:
        assert limited.retry_after == 7 and len(limited_http.requests) == 1
    else:
        raise AssertionError('Read rate limit was ignored')
    missing_http = FixtureHTTP(response({}, 404))
    try:
        await yookassa(missing_http).get(created.provider_id, binding=binding, invoice_operation_id='invoice:1')
    except ProviderReadFailure:
        assert len(missing_http.requests) == 1  # Absence is not permission to create again.
    else:
        raise AssertionError('Missing lookup was accepted')
    unknown_http = FixtureHTTP(response({}, 502))
    try:
        await yookassa(unknown_http).create(InvoiceRequest(binding, 'Fixture', 'https://example.com/return'),
                                           operation_id='invoice:unknown')
    except ProviderWriteUnknown:
        assert len(unknown_http.requests) == 1  # Host preserves its operation and reconciles; no retry here.
    else:
        raise AssertionError('Uncertain write was accepted')
    assert not local.replies and not crypto_http.replies and not platega_http.replies
    print(json.dumps({'passed': True, 'case': 'core_providers', 'network': False,
                      'live_provider_verified': False}))


asyncio.run(main())
