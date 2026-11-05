"""Direct YooKassa v3 payments, full capture and refunds with authenticated GET reconciliation."""

from __future__ import annotations

import base64
import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

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
    decode_json,
    event_identity,
    https_url,
    identifier,
    object_value,
    operation_key,
    require_binding,
    require_snapshot,
    text,
    timestamp,
)


@dataclass(frozen=True, slots=True)
class YooKassaCreateOptions:
    """Explicit two-stage opt-in; the existing one-stage default remains capture=True."""

    capture: bool = True

    def __post_init__(self) -> None:
        if type(self.capture) is not bool:
            raise ValidationFailure('YooKassa capture option must be an exact boolean')


@dataclass(frozen=True, slots=True)
class YooKassaPeerPolicy:
    """Host supplies the socket peer, or a peer resolved by its fixed trusted proxy configuration."""

    networks: tuple[str, ...] = (
        '185.71.76.0/27',
        '185.71.77.0/27',
        '77.75.153.0/25',
        '77.75.156.11/32',
        '77.75.156.35/32',
        '77.75.154.128/25',
        '2a02:5180::/32',
    )

    def __post_init__(self) -> None:
        if not 1 <= len(self.networks) <= 32:
            raise ValidationFailure('Use a bounded provider peer allowlist')
        try:
            for network in self.networks:
                ipaddress.ip_network(network, strict=True)
        except ValueError as error:
            raise ValidationFailure('Invalid provider peer network') from error

    def allows(self, peer_ip: str) -> bool:
        try:
            address = ipaddress.ip_address(peer_ip)
            return any(address in ipaddress.ip_network(network) for network in self.networks)
        except ValueError:
            return False


class YooKassaAdapter:
    """Fixed API origin for test/live shops. No HMAC or client redirect is treated as payment proof."""

    def __init__(
        self,
        transport: AsyncTransport[ProviderHttpRequest, ProviderHttpResponse],
        *,
        merchant_id: str,
        shop_id: str,
        secret_key: str,
        test: bool,
        peer_policy: YooKassaPeerPolicy | None = None,
        timeout_seconds: int = 15,
        max_response_bytes: int = 262144,
    ) -> None:
        self.merchant_id = identifier(merchant_id)
        self.shop_id = identifier(shop_id)
        text(secret_key, maximum=512)
        if not secret_key.isascii() or ':' in shop_id or type(test) is not bool:
            raise ValidationFailure('Invalid YooKassa shop configuration')
        self._authorization = 'Basic ' + base64.b64encode((shop_id + ':' + secret_key).encode('ascii')).decode('ascii')
        self.test = test
        self.peer_policy = peer_policy or YooKassaPeerPolicy()
        self._http = ProviderHttpClient(
            transport, timeout_seconds=timeout_seconds, max_response_bytes=max_response_bytes
        )

    def _binding(self, binding: PaymentBinding) -> None:
        require_binding(binding, provider='yookassa', merchant_id=self.merchant_id)
        if binding.amount.exponent != 2:
            raise UnsupportedCapability('This YooKassa adapter supports currencies with two decimal places only')

    async def _call(self, path: str, *, body: dict[str, Any] | None = None, key: str | None = None) -> Any:
        headers = {'Authorization': self._authorization, 'Content-Type': 'application/json'}
        if key is not None:
            headers['Idempotence-Key'] = operation_key(key, maximum=64)
        return await self._http.json(
            'GET' if body is None else 'POST', 'https://api.yookassa.ru/v3/' + path, headers, body
        )

    def _snapshot(self, data: Any, binding: PaymentBinding, invoice_operation_id: str) -> ProviderInvoice:
        data = object_value(data)
        if data.get('test') is not self.test or object_value(data.get('recipient')).get('account_id') != self.shop_id:
            raise PermissionDenied('YooKassa recipient or test environment differs')
        amount = object_value(data.get('amount'))
        if amount.get('currency') != binding.amount.currency:
            raise PermissionDenied('YooKassa currency differs')
        metadata = object_value(data.get('metadata'))
        if metadata.get('telegram_operation') != invoice_operation_id:
            raise PermissionDenied('YooKassa invoice operation differs')
        state = identifier(data.get('status'))
        paid_at = None
        if state == 'succeeded':
            if data.get('paid') is not True:
                raise PermissionDenied('YooKassa captured payment lacks its paid flag')
            paid_at = timestamp(data.get('captured_at'))
        checkout = None
        if data.get('confirmation') is not None:
            confirmation = object_value(data['confirmation'])
            if confirmation.get('type') == 'redirect' and confirmation.get('confirmation_url') is not None:
                checkout = https_url(confirmation['confirmation_url'])
        snapshot = ProviderInvoice(
            identifier(data.get('id')),
            state,
            amount_value(amount.get('value'), binding.amount),
            text(metadata.get('telegram_binding'), maximum=64),
            self.merchant_id,
            paid_at,
            checkout,
        )
        require_snapshot(snapshot, binding, invoice_operation_id)
        return snapshot

    async def create(
        self, request: InvoiceRequest, *, operation_id: str, options: YooKassaCreateOptions | None = None
    ) -> ProviderInvoice:
        self._binding(request.binding)
        operation_key(operation_id)
        if options is not None and not isinstance(options, YooKassaCreateOptions):
            raise ValidationFailure('Use YooKassaCreateOptions for the selected payment stage')
        if len(request.description) > 128:
            raise ValidationFailure('YooKassa payment description exceeds 128 characters')
        body = {
            'amount': {'value': request.binding.amount.to_decimal(), 'currency': request.binding.amount.currency},
            'capture': True if options is None else options.capture,
            'confirmation': {'type': 'redirect', 'return_url': request.return_url},
            'description': request.description,
            'metadata': {
                'telegram_binding': binding_reference(request.binding, operation_id),
                'telegram_operation': operation_id,
            },
        }
        data = await self._call('payments', body=body, key=binding_reference(request.binding, operation_id))
        try:
            return self._snapshot(data, request.binding, operation_id)
        except Exception as error:
            raise ProviderWriteUnknown('Created YooKassa payment needs reconciliation') from error

    async def _read_payment(
        self, provider_id: str, *, binding: PaymentBinding, invoice_operation_id: str
    ) -> tuple[ProviderInvoice, dict[str, Any]]:
        self._binding(binding)
        provider_id = identifier(provider_id)
        data = object_value(await self._call('payments/' + provider_id))
        snapshot = self._snapshot(data, binding, invoice_operation_id)
        if snapshot.provider_id != provider_id:
            raise PermissionDenied('YooKassa lookup returned another payment')
        return snapshot, data

    async def get(self, provider_id: str, *, binding: PaymentBinding, invoice_operation_id: str) -> ProviderInvoice:
        snapshot, _data = await self._read_payment(
            provider_id, binding=binding, invoice_operation_id=invoice_operation_id
        )
        return snapshot

    def verify_event(self, body: bytes, headers: Mapping[str, str]) -> None:
        """Headers alone cannot authenticate a YooKassa notification; deliberately fail closed."""
        return None

    def verify_notification(self, body: bytes, *, peer_ip: str) -> ProviderNotification | None:
        """The host must resolve peer_ip from its trusted socket/proxy context, never arbitrary headers."""
        if not self.peer_policy.allows(peer_ip):
            return None
        data = object_value(decode_json(body))
        if data.get('type') != 'notification':
            return None
        event = text(data.get('event'), maximum=64)
        if event not in ('payment.succeeded', 'payment.waiting_for_capture', 'payment.canceled', 'refund.succeeded'):
            return None
        item = object_value(data.get('object'))
        return ProviderNotification(identifier(item.get('id')), event, identifier(item.get('status')))

    async def invoice_event(
        self, binding: PaymentBinding, provider_id: str, *, invoice_operation_id: str, evidence_ref: str
    ) -> ProviderEvent:
        snapshot = await self.get(provider_id, binding=binding, invoice_operation_id=invoice_operation_id)
        return ProviderEvent(
            binding,
            event_identity('yookassa', 'invoice', provider_id, snapshot.native_state),
            'invoice-created',
            snapshot.native_state,
            evidence_ref,
            operation_id=invoice_operation_id,
            provider_ref=provider_id,
        )

    async def payment_event(
        self, binding: PaymentBinding, provider_id: str, *, invoice_operation_id: str, evidence_ref: str
    ) -> ProviderEvent:
        snapshot = await self.get(provider_id, binding=binding, invoice_operation_id=invoice_operation_id)
        if snapshot.native_state != 'succeeded' or snapshot.paid_at is None:
            raise UnsupportedCapability('YooKassa payment is not captured and succeeded')
        return ProviderEvent(
            binding,
            event_identity('yookassa', 'paid', provider_id),
            'paid',
            snapshot.native_state,
            evidence_ref,
            charge_id=provider_id,
            amount=snapshot.amount,
            paid_at=snapshot.paid_at,
        )

    def _refund_snapshot(self, data: Any, request: RefundRequest) -> ProviderRefund:
        data = object_value(data)
        amount = object_value(data.get('amount'))
        if data.get('payment_id') != request.charge_id or amount.get('currency') != request.amount.currency:
            raise PermissionDenied('YooKassa refund charge or currency differs')
        parsed = amount_value(amount.get('value'), request.amount)
        if parsed != request.amount:
            raise PermissionDenied('YooKassa refund amount differs')
        return ProviderRefund(identifier(data.get('id')), request.charge_id, identifier(data.get('status')), parsed)

    async def refund(self, request: RefundRequest, *, operation_id: str) -> ProviderRefund:
        self._binding(request.binding)
        operation_key(operation_id)
        # This read is outside any financial DB transaction; caller has already reserved its refund budget.
        await self.get(request.charge_id, binding=request.binding, invoice_operation_id=request.invoice_operation_id)
        body = {
            'payment_id': request.charge_id,
            'amount': {'value': request.amount.to_decimal(), 'currency': request.amount.currency},
        }
        data = await self._call('refunds', body=body, key=binding_reference(request.binding, operation_id))
        try:
            return self._refund_snapshot(data, request)
        except Exception as error:
            raise ProviderWriteUnknown('Created YooKassa refund needs reconciliation') from error

    async def get_refund(self, provider_id: str, *, request: RefundRequest) -> ProviderRefund:
        self._binding(request.binding)
        provider_id = identifier(provider_id)
        data = await self._call('refunds/' + provider_id)
        snapshot = self._refund_snapshot(data, request)
        if snapshot.provider_id != provider_id:
            raise PermissionDenied('YooKassa lookup returned another refund')
        await self.get(request.charge_id, binding=request.binding, invoice_operation_id=request.invoice_operation_id)
        return snapshot

    async def refund_event(
        self, request: RefundRequest, provider_id: str, *, operation_id: str, evidence_ref: str
    ) -> ProviderEvent:
        snapshot = await self.get_refund(provider_id, request=request)
        if snapshot.native_state != 'succeeded':
            raise UnsupportedCapability('YooKassa refund is not finally succeeded')
        return ProviderEvent(
            request.binding,
            event_identity('yookassa', 'refund', provider_id),
            'refunded',
            snapshot.native_state,
            evidence_ref,
            operation_id=operation_id,
            charge_id=request.charge_id,
            refund_id=provider_id,
            amount=snapshot.amount,
        )

    def capture_key(
        self, binding: PaymentBinding, provider_id: str, *, invoice_operation_id: str, operation_id: str
    ) -> str:
        """Stable separate namespace; host persists this key and full intent before attempting capture."""
        self._binding(binding)
        provider_id = identifier(provider_id)
        operation_key(invoice_operation_id)
        operation_key(operation_id)
        return event_identity(
            'yookassa', 'capture', binding_reference(binding, invoice_operation_id), provider_id, operation_id
        ).split(':')[1]

    async def capture(
        self, binding: PaymentBinding, provider_id: str, *, invoice_operation_id: str, operation_id: str
    ) -> ProviderInvoice:
        """Capture the full immutable order amount once; response alone never authorizes access.

        A fresh authenticated GET must confirm succeeded/paid/captured_at after the POST.
        If the POST or this follow-up is ambiguous, preserve the same durable capture intent as unknown.
        Partial capture and repeated sends after an unknown result are outside this full-only contract.
        """
        key = self.capture_key(
            binding, provider_id, invoice_operation_id=invoice_operation_id, operation_id=operation_id
        )
        before, data = await self._read_payment(provider_id, binding=binding, invoice_operation_id=invoice_operation_id)
        if before.native_state != 'waiting_for_capture' or data.get('paid') is not True:
            raise UnsupportedCapability('Full capture requires an authoritatively authorized payment')
        body = {'amount': {'value': binding.amount.to_decimal(), 'currency': binding.amount.currency}}
        result = await self._call('payments/' + provider_id + '/capture', body=body, key=key)
        try:
            returned = self._snapshot(result, binding, invoice_operation_id)
            if returned.provider_id != provider_id:
                raise PermissionDenied('Capture response refers to another payment')
            # POST success/pending is not financial proof. Observe the current authoritative object independently.
            current = await self.get(provider_id, binding=binding, invoice_operation_id=invoice_operation_id)
            if current.native_state != 'succeeded' or current.paid_at is None:
                raise ProviderWriteUnknown(
                    'Capture result is not authoritatively final; reconcile without another POST'
                )
            return current
        except Exception as error:
            raise ProviderWriteUnknown('YooKassa capture needs native payment reconciliation') from error
