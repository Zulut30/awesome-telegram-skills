"""Crypto Pay invoices and raw-body HMAC hints; no undocumented invoice refunds."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping
from typing import Any, Literal

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
    ProviderReadFailure,
    ProviderWriteUnknown,
    RefundRequest,
    amount_value,
    binding_reference,
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
    timestamp,
)


class CryptoPayAdapter:
    """Host binds its merchant ID to an application token; no token/account discovery is invented."""

    def __init__(
        self,
        transport: AsyncTransport[ProviderHttpRequest, ProviderHttpResponse],
        *,
        merchant_id: str,
        token: str,
        environment: Literal['testnet', 'mainnet'] = 'testnet',
        currency_type: Literal['fiat', 'crypto'] = 'fiat',
        timeout_seconds: int = 15,
        max_response_bytes: int = 262144,
    ) -> None:
        self.merchant_id = identifier(merchant_id)
        self._token = text(token, maximum=512)
        if not token.isascii() or environment not in ('testnet', 'mainnet') or currency_type not in ('fiat', 'crypto'):
            raise ValidationFailure('Invalid Crypto Pay configuration')
        self.environment = environment
        self.currency_type = currency_type
        self._base = 'https://testnet-pay.crypt.bot/api/' if environment == 'testnet' else 'https://pay.crypt.bot/api/'
        self._http = ProviderHttpClient(
            transport, timeout_seconds=timeout_seconds, max_response_bytes=max_response_bytes
        )

    def _binding(self, binding: PaymentBinding) -> None:
        require_binding(binding, provider='cryptopay', merchant_id=self.merchant_id)
        fiat = {
            'USD',
            'EUR',
            'RUB',
            'BYN',
            'UAH',
            'GBP',
            'CNY',
            'KZT',
            'UZS',
            'GEL',
            'TRY',
            'AMD',
            'THB',
            'INR',
            'BRL',
            'IDR',
            'AZN',
            'AED',
            'PLN',
            'ILS',
        }
        crypto = {'USDT', 'TON', 'BTC', 'ETH', 'LTC', 'BNB', 'TRX', 'USDC'}
        if self.environment == 'testnet':
            crypto.add('JET')
        if binding.amount.currency not in (fiat if self.currency_type == 'fiat' else crypto):
            raise UnsupportedCapability('Currency is outside the documented Crypto Pay invoice set')

    async def _call(self, method: str, *, body: dict[str, Any] | None = None, query: str = '') -> Any:
        write = body is not None
        raw = await self._http.json(
            'POST' if write else 'GET',
            self._base + method + query,
            {'Crypto-Pay-API-Token': self._token, 'Content-Type': 'application/json'},
            body,
        )
        try:
            result = object_value(raw)
        except ValidationFailure as error:
            failure = ProviderWriteUnknown if write else ProviderReadFailure
            raise failure('Crypto Pay envelope needs reconciliation') from error
        if result.get('ok') is not True or 'result' not in result:
            failure = ProviderWriteUnknown if write else ProviderReadFailure
            raise failure('Crypto Pay did not establish the operation result')
        return result['result']

    @staticmethod
    def _native_id(value: Any) -> str:
        if type(value) is not int or not 0 < value <= 2**63 - 1:
            raise ValidationFailure('Expected an exact positive Crypto Pay invoice ID')
        return str(value)

    def _snapshot(self, data: Any, binding: PaymentBinding, operation_id: str) -> ProviderInvoice:
        data = object_value(data)
        if data.get('currency_type') != self.currency_type:
            raise PermissionDenied('Crypto Pay currency mode differs from the server order')
        currency = data.get('fiat' if self.currency_type == 'fiat' else 'asset')
        if currency != binding.amount.currency:
            raise PermissionDenied('Crypto Pay nominal currency differs')
        state = identifier(data.get('status'))
        snapshot = ProviderInvoice(
            self._native_id(data.get('invoice_id')),
            state,
            amount_value(data.get('amount'), binding.amount),
            text(data.get('payload'), maximum=4096),
            self.merchant_id,
            timestamp(data['paid_at']) if state == 'paid' else None,
            https_url(data['bot_invoice_url']) if data.get('bot_invoice_url') is not None else None,
        )
        require_snapshot(snapshot, binding, operation_id)
        return snapshot

    async def create(self, request: InvoiceRequest, *, operation_id: str) -> ProviderInvoice:
        self._binding(request.binding)
        operation_key(operation_id)
        body = {
            'currency_type': self.currency_type,
            'fiat' if self.currency_type == 'fiat' else 'asset': request.binding.amount.currency,
            'amount': request.binding.amount.to_decimal(),
            'description': request.description,
            'payload': binding_reference(request.binding, operation_id),
            'expires_in': request.expires_in,
            'allow_comments': False,
            'allow_anonymous': True,
        }
        data = await self._call('createInvoice', body=body)
        try:
            return self._snapshot(data, request.binding, operation_id)
        except Exception as error:
            raise ProviderWriteUnknown('Created invoice response needs reconciliation') from error

    async def get(self, provider_id: str, *, binding: PaymentBinding, invoice_operation_id: str) -> ProviderInvoice:
        self._binding(binding)
        if not isinstance(provider_id, str) or re.fullmatch(r'[1-9][0-9]{0,18}', provider_id) is None:
            raise ValidationFailure('Expected a canonical positive Crypto Pay invoice ID')
        result = await self._call('getInvoices', query='?invoice_ids=' + provider_id)
        # Current deployments wrap lists in items; the documented direct list is also accepted.
        items = result.get('items') if isinstance(result, dict) else result
        if not isinstance(items, list) or len(items) != 1:
            raise ProviderReadFailure('Invoice lookup did not identify one existing invoice')
        snapshot = self._snapshot(items[0], binding, invoice_operation_id)
        if snapshot.provider_id != provider_id:
            raise PermissionDenied('Crypto Pay lookup returned a different invoice')
        return snapshot

    def verify_event(self, body: bytes, headers: Mapping[str, str]) -> ProviderNotification | None:
        """Verify exact body bytes. update_id is deliberately not used as a financial identity."""
        values = headers_lower(headers)
        signature = values.get('crypto-pay-api-signature', '')
        if re.fullmatch(r'[0-9a-f]{64}', signature) is None or not isinstance(body, bytes) or len(body) > 262144:
            return None
        expected = hmac.new(hashlib.sha256(self._token.encode('ascii')).digest(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        data = object_value(decode_json(body))
        if data.get('update_type') != 'invoice_paid':
            return None
        timestamp(data.get('request_date'))
        invoice = object_value(data.get('payload'))
        return ProviderNotification(
            self._native_id(invoice.get('invoice_id')), 'invoice_paid', identifier(invoice.get('status'))
        )

    async def invoice_event(
        self, binding: PaymentBinding, provider_id: str, *, invoice_operation_id: str, evidence_ref: str
    ) -> ProviderEvent:
        snapshot = await self.get(provider_id, binding=binding, invoice_operation_id=invoice_operation_id)
        return ProviderEvent(
            binding,
            event_identity('cryptopay', 'invoice', provider_id, snapshot.native_state),
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
        if snapshot.native_state != 'paid' or snapshot.paid_at is None:
            raise UnsupportedCapability('Invoice is not authoritatively paid')
        return ProviderEvent(
            binding,
            event_identity('cryptopay', 'paid', provider_id),
            'paid',
            snapshot.native_state,
            evidence_ref,
            charge_id=provider_id,
            amount=snapshot.amount,
            paid_at=snapshot.paid_at,
        )

    async def refund(self, request: RefundRequest, *, operation_id: str) -> None:
        raise UnsupportedCapability('Crypto Pay has no documented native invoice refund method')
