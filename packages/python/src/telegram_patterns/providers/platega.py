"""Current Platega camelCase payment/refund protocol; no invented paid timestamp or sandbox."""

from __future__ import annotations

import hmac
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from ..errors import PermissionDenied, UnsupportedCapability, ValidationFailure
from ..extensions import AsyncTransport
from ..payment_ledger import PaymentBinding, ProviderEvent
from .http import (
    InvoiceRequest,
    ProviderHttpClient,
    ProviderHttpRequest,
    ProviderHttpResponse,
    ProviderInvoice,
    ProviderNotification,
    ProviderRefund,
    ProviderWriteUnknown,
    RefundRequest,
    amount_value,
    binding_reference,
    bounded_decimal,
    decode_json,
    event_identity,
    headers_lower,
    https_url,
    identifier,
    object_value,
    operation_key,
    require_binding,
    require_snapshot,
    text,
)


@dataclass(frozen=True, slots=True)
class PlategaRefundSupport:
    supported: bool
    partial_supported: bool
    total_deduct_usdt: Decimal
    penalty_usdt: Decimal | None


class PlategaAdapter:
    """One fixed official origin. Merchant-enabled payment method and real customer metadata are explicit."""

    def __init__(
        self,
        transport: AsyncTransport[ProviderHttpRequest, ProviderHttpResponse],
        *,
        merchant_id: str,
        native_merchant_id: str,
        secret: str,
        payment_method: int,
        timeout_seconds: int = 15,
        max_response_bytes: int = 262144,
    ) -> None:
        self.merchant_id = identifier(merchant_id)
        self.native_merchant_id = identifier(native_merchant_id)
        self._secret = text(secret, maximum=512)
        if not secret.isascii() or type(payment_method) is not int or not 1 <= payment_method <= 100000:
            raise ValidationFailure('Invalid Platega merchant configuration')
        self.payment_method = payment_method
        self._http = ProviderHttpClient(
            transport, timeout_seconds=timeout_seconds, max_response_bytes=max_response_bytes
        )

    def _binding(self, binding: PaymentBinding) -> None:
        require_binding(binding, provider='platega', merchant_id=self.merchant_id)
        if binding.amount.exponent != 2:
            raise UnsupportedCapability('This Platega adapter requires two-decimal native currencies')

    async def _call(self, path: str, *, post: bool = False, body: Any = None, key: str | None = None) -> Any:
        headers = {
            'X-MerchantId': self.native_merchant_id,
            'X-Secret': self._secret,
            'Content-Type': 'application/json',
        }
        if key is not None:
            headers['Idempotency-Key'] = operation_key(key, maximum=128)
        return await self._http.json('POST' if post else 'GET', 'https://app.platega.io/' + path, headers, body)

    async def create(
        self, request: InvoiceRequest, *, operation_id: str, customer_email: str, failed_url: str | None = None
    ) -> ProviderInvoice:
        self._binding(request.binding)
        operation_key(operation_id)
        text(customer_email, maximum=254)
        if not isinstance(customer_email, str) or re.fullmatch(r'[^\s@]{1,64}@[^\s@]{1,189}', customer_email) is None:
            raise ValidationFailure('Supply real server-owned customer email metadata')
        reference = binding_reference(request.binding, operation_id)
        body = {
            'paymentMethod': self.payment_method,
            'paymentDetails': {
                'amount': Decimal(request.binding.amount.to_decimal()),
                'currency': request.binding.amount.currency,
            },
            'description': request.description,
            'return': request.return_url,
            'failedUrl': https_url(failed_url or request.return_url),
            'payload': reference,
            'metadata': {'userId': str(request.binding.user_id), 'user_email': customer_email},
        }
        data = await self._call('transaction/process', post=True, body=body)
        try:
            data = object_value(data)
            if data.get('merchantId') != self.native_merchant_id:
                raise PermissionDenied('Platega create returned another merchant')
            # create.paymentDetails is a presentation string, not an authoritative structured amount.
            return ProviderInvoice(
                identifier(data.get('transactionId')),
                identifier(data.get('status')),
                request.binding.amount,
                reference,
                self.merchant_id,
                checkout_url=https_url(data.get('redirect')),
            )
        except Exception as error:
            raise ProviderWriteUnknown('Created Platega transaction needs reconciliation') from error

    async def get(self, provider_id: str, *, binding: PaymentBinding, invoice_operation_id: str) -> ProviderInvoice:
        self._binding(binding)
        provider_id = identifier(provider_id)
        data = object_value(await self._call('transaction/' + provider_id))
        # mechantId is the exact published GET schema spelling; do not silently invent merchantId.
        if data.get('mechantId') != self.native_merchant_id or data.get('id') != provider_id:
            raise PermissionDenied('Platega transaction or merchant differs')
        amount = object_value(data.get('paymentDetails'))
        if amount.get('currency') != binding.amount.currency:
            raise PermissionDenied('Platega nominal currency differs')
        snapshot = ProviderInvoice(
            provider_id,
            identifier(data.get('status')),
            amount_value(amount.get('amount'), binding.amount, numeric=True),
            text(data.get('payload'), maximum=4096),
            self.merchant_id,
        )
        require_snapshot(snapshot, binding, invoice_operation_id)
        return snapshot

    def verify_event(self, body: bytes, headers: Mapping[str, str]) -> ProviderNotification | None:
        values = headers_lower(headers)
        merchant = values.get('x-merchantid', '')
        secret = values.get('x-secret', '')
        if not merchant.isascii() or not secret.isascii():
            return None
        # Payment callbacks use shared headers, not payout HMAC or a fabricated signature scheme.
        if not hmac.compare_digest(merchant, self.native_merchant_id) or not hmac.compare_digest(secret, self._secret):
            return None
        data = object_value(decode_json(body))
        return ProviderNotification(
            identifier(data.get('id')),
            'transaction',
            identifier(data.get('status')),
            identifier(data['refundId']) if data.get('refundId') is not None else None,
        )

    async def invoice_event(
        self, binding: PaymentBinding, provider_id: str, *, invoice_operation_id: str, evidence_ref: str
    ) -> ProviderEvent:
        snapshot = await self.get(provider_id, binding=binding, invoice_operation_id=invoice_operation_id)
        return ProviderEvent(
            binding,
            event_identity('platega', 'invoice', provider_id, snapshot.native_state),
            'invoice-created',
            snapshot.native_state,
            evidence_ref,
            operation_id=invoice_operation_id,
            provider_ref=provider_id,
        )

    async def payment_event(
        self, binding: PaymentBinding, provider_id: str, *, invoice_operation_id: str, evidence_ref: str
    ) -> ProviderEvent:
        self._binding(binding)
        raise UnsupportedCapability('Published Platega status has no native paid_at required by this ledger')

    @staticmethod
    def _cost(value: Any) -> Decimal:
        if type(value) is int:
            value = Decimal(value)
        if (
            not isinstance(value, Decimal)
            or not bounded_decimal(value)
            or value < 0
            or value > Decimal('1000000000000000000')
        ):
            raise ValidationFailure('Invalid Platega preflight cost')
        return value

    async def refund_support(self, request: RefundRequest) -> PlategaRefundSupport:
        self._binding(request.binding)
        snapshot = await self.get(
            request.charge_id, binding=request.binding, invoice_operation_id=request.invoice_operation_id
        )
        if snapshot.native_state not in ('CONFIRMED', 'PARTIALLY_REFUNDED'):
            raise UnsupportedCapability('Platega transaction is not in a refundable paid state')
        partial = request.amount != request.binding.amount
        query = '?' + urlencode({'amount': request.amount.to_decimal()}) if partial else ''
        data = object_value(await self._call('transaction/' + request.charge_id + '/cancel-supported' + query))
        if type(data.get('supported')) is not bool or type(data.get('partialSupported')) is not bool:
            raise ValidationFailure('Invalid Platega refund support flags')
        return PlategaRefundSupport(
            data['supported'],
            data['partialSupported'],
            self._cost(data.get('totalDeductUsdt')),
            self._cost(data['penaltyUsdt']) if data.get('penaltyUsdt') is not None else None,
        )

    async def refund(
        self,
        request: RefundRequest,
        *,
        operation_id: str,
        approve_cost: Callable[[PlategaRefundSupport], bool],
    ) -> ProviderRefund:
        operation_key(operation_id)
        support = await self.refund_support(request)
        partial = request.amount != request.binding.amount
        if not support.supported or (partial and not support.partial_supported):
            raise UnsupportedCapability('Platega merchant does not support this refund')
        if approve_cost(support) is not True:
            raise PermissionDenied('Host did not authorize the quoted merchant refund cost')
        path = 'transaction/' + request.charge_id + ('/cancel-partial' if partial else '/cancel')
        # Full cancellation must have no JSON body and no amount. Only partial has documented idempotency.
        data = await self._call(
            path,
            post=True,
            body={'amount': Decimal(request.amount.to_decimal())} if partial else None,
            key=binding_reference(request.binding, operation_id) if partial else None,
        )
        try:
            data = object_value(data)
            if data.get('transactionId') != request.charge_id:
                raise PermissionDenied('Platega refund response refers to another charge')
            if type(data.get('accepted')) is not bool or type(data.get('manualControlRequired')) is not bool:
                raise ValidationFailure('Invalid Platega refund acceptance flags')
            native_id = identifier(data['refundOperationId']) if data.get('refundOperationId') is not None else None
            state = (
                'manual-control-required'
                if data['manualControlRequired']
                else 'accepted'
                if data['accepted']
                else 'pending'
            )
            return ProviderRefund(
                native_id, request.charge_id, state, request.amount, data['accepted'], data['manualControlRequired']
            )
        except Exception as error:
            raise ProviderWriteUnknown('Platega refund request needs reconciliation') from error

    async def refund_event(
        self,
        request: RefundRequest,
        provider_refund_id: str,
        body: bytes,
        headers: Mapping[str, str],
        *,
        operation_id: str,
        evidence_ref: str,
    ) -> ProviderEvent:
        self._binding(request.binding)
        provider_refund_id = identifier(provider_refund_id)
        hint = self.verify_event(body, headers)
        if hint is None or hint.provider_id != request.charge_id or hint.refund_id != provider_refund_id:
            raise PermissionDenied('Authenticated refund hint does not match the persisted native refund')
        data = object_value(decode_json(body))
        if (
            data.get('currency') != request.amount.currency
            or data.get('payload') != binding_reference(request.binding, request.invoice_operation_id)
            or amount_value(data.get('amount'), request.binding.amount, numeric=True) != request.binding.amount
            or amount_value(data.get('refundAmount'), request.amount, numeric=True) != request.amount
        ):
            raise PermissionDenied('Platega callback refund binding differs')
        if data.get('refundStatus') != 'Succeeded' or hint.native_state not in ('CHARGEBACKED', 'PARTIALLY_REFUNDED'):
            raise UnsupportedCapability('Platega refund is not finally succeeded')
        snapshot = await self.get(
            request.charge_id, binding=request.binding, invoice_operation_id=request.invoice_operation_id
        )
        if snapshot.native_state not in ('CHARGEBACKED', 'PARTIALLY_REFUNDED'):
            raise UnsupportedCapability('Current Platega status does not confirm a refunded transaction')
        return ProviderEvent(
            request.binding,
            event_identity('platega', 'refund', provider_refund_id),
            'refunded',
            'Succeeded',
            evidence_ref,
            operation_id=operation_id,
            charge_id=request.charge_id,
            refund_id=provider_refund_id,
            amount=request.amount,
        )
