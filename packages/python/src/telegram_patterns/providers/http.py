"""Bounded, injected HTTP contracts for optional payment adapters; no networking library."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlsplit

from ..errors import ErrorCode, PermissionDenied, TransportFailure, UnknownOutcome, ValidationFailure
from ..extensions import AsyncTransport
from ..money import Money
from ..payment_ledger import PaymentBinding


@dataclass(frozen=True, slots=True)
class ProviderHttpRequest:
    """Transport must verify TLS, refuse redirects/retries and stream at most max_response_bytes."""

    method: Literal['GET', 'POST']
    url: str
    headers: Mapping[str, str] = field(repr=False)
    body: bytes | None = field(default=None, repr=False)
    timeout_seconds: int = 15
    max_response_bytes: int = 262144


@dataclass(frozen=True, slots=True)
class ProviderHttpResponse:
    status: int
    body: bytes = field(repr=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    redirected: bool = False


class ProviderReadFailure(TransportFailure):
    """Lookup failed or was absent; this does not establish that a write had no effect."""


class ProviderWriteUnknown(UnknownOutcome):
    """The remote write may have happened; preserve the same operation and reconcile."""


class ProviderRateLimited(TransportFailure):
    """Read-only 429 hint. Host owns bounded retry budget and rate scheduling."""

    code: ErrorCode = 'rate-limited'

    def __init__(self, retry_after: int | None) -> None:
        super().__init__('Provider read rate limit')
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class InvoiceRequest:
    binding: PaymentBinding
    description: str = field(repr=False)
    return_url: str = field(repr=False)
    expires_in: int = 900

    def __post_init__(self) -> None:
        text(self.description, maximum=1024)
        https_url(self.return_url)
        if type(self.expires_in) is not int or not 1 <= self.expires_in <= 2678400:
            raise ValidationFailure('Use a bounded invoice lifetime')


@dataclass(frozen=True, slots=True)
class RefundRequest:
    binding: PaymentBinding
    charge_id: str
    amount: Money
    invoice_operation_id: str

    def __post_init__(self) -> None:
        identifier(self.charge_id)
        operation_key(self.invoice_operation_id)
        if self.amount.currency != self.binding.amount.currency or self.amount.exponent != self.binding.amount.exponent:
            raise ValidationFailure('Refund currency must match the immutable order')
        if not 0 < self.amount.minor_units <= self.binding.amount.minor_units:
            raise ValidationFailure('Refund amount must be positive and within the charge')
        if self.amount != self.binding.amount and not self.binding.allow_partial_refunds:
            raise ValidationFailure('Partial refunds require the server order policy')


@dataclass(frozen=True, slots=True)
class ProviderInvoice:
    """A data snapshot, not an authentication capability or permission to grant access."""

    provider_id: str
    native_state: str
    amount: Money
    binding_reference: str
    merchant_id: str
    paid_at: int | None = None
    checkout_url: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ProviderRefund:
    provider_id: str | None
    charge_id: str
    native_state: str
    amount: Money
    accepted: bool | None = None
    manual_control_required: bool = False


@dataclass(frozen=True, slots=True)
class ProviderNotification:
    """Authenticated routing hint where a provider offers authentication; always reconcile via API."""

    provider_id: str
    event: str
    native_state: str
    refund_id: str | None = None


def text(value: Any, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise ValidationFailure('Expected a bounded text field')
    return value


def identifier(value: Any) -> str:
    result = text(value, maximum=128)
    if re.fullmatch(r'[A-Za-z0-9_.:-]+', result) is None:
        raise ValidationFailure('Expected a safe provider identifier')
    return result


def operation_key(value: Any, *, maximum: int = 128) -> str:
    return text(identifier(value), maximum=maximum)


def https_url(value: Any) -> str:
    result = text(value, maximum=2048)
    parsed = urlsplit(result)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValidationFailure('Expected an absolute HTTPS URL without credentials or fragment')
    return result


def headers_lower(headers: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, value in headers.items():
        lower = name.lower()
        if lower in result or not isinstance(value, str) or len(value) > 4096 or '\r' in value or '\n' in value:
            raise ValidationFailure('Ambiguous or invalid HTTP headers')
        result[lower] = value
    return result


def object_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationFailure('Expected a JSON object')
    return value


def decode_json(body: bytes, *, maximum: int = 262144) -> Any:
    if not isinstance(body, bytes) or len(body) > maximum:
        raise ValidationFailure('Provider payload exceeds the byte limit')

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate key')
            result[key] = value
        return result

    def bad_constant(_: str) -> Any:
        raise ValueError('Nonfinite number')

    try:
        # Guard nesting before the recursive stdlib decoder allocates nested objects.
        raw = body.decode('utf-8')
        depth = 0
        quoted = escaped = False
        for char in raw:
            if quoted:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in '[{':
                depth += 1
                if depth > 32:
                    raise ValueError('Nested payload')
            elif char in ']}':
                depth -= 1
        return json.loads(raw, parse_float=Decimal, parse_constant=bad_constant, object_pairs_hook=pairs)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValidationFailure('Invalid provider JSON') from error


def bounded_decimal(value: Decimal) -> bool:
    exponent = value.as_tuple().exponent
    return (
        value.is_finite() and len(value.as_tuple().digits) <= 64 and isinstance(exponent, int) and -18 <= exponent <= 0
    )


def encode_json(value: Any) -> bytes:
    """Encode Decimal as an exact JSON number, without a binary float or decimal-context rounding."""

    def encode(item: Any) -> str:
        if isinstance(item, Decimal):
            if not bounded_decimal(item) or item < 0:
                raise ValidationFailure('Expected a finite nonnegative amount')
            return format(item, 'f')
        if item is None or type(item) in (str, int, bool):
            return json.dumps(item, ensure_ascii=False, allow_nan=False)
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise ValidationFailure('JSON keys must be strings')
            return '{' + ','.join(encode(key) + ':' + encode(val) for key, val in item.items()) + '}'
        if isinstance(item, list):
            return '[' + ','.join(encode(val) for val in item) + ']'
        raise ValidationFailure('Unsupported request JSON value')

    body = encode(value).encode('utf-8')
    if len(body) > 65536:
        raise ValidationFailure('Provider request exceeds the byte limit')
    return body


def amount_value(value: Any, expected: Money, *, numeric: bool = False) -> Money:
    if numeric:
        if type(value) is int:
            value = str(value)
        elif isinstance(value, Decimal) and bounded_decimal(value):
            value = format(value, 'f')
        else:
            raise ValidationFailure('Expected an exact JSON monetary number')
    return Money.from_decimal(value, expected.currency, expected.exponent)


def timestamp(value: Any) -> int:
    value = text(value, maximum=64)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('Timezone required')
        result = int(parsed.timestamp())
        if result <= 0:
            raise ValueError('Positive timestamp required')
        return result
    except (ValueError, OverflowError, OSError) as error:
        raise ValidationFailure('Expected a provider UTC timestamp') from error


def binding_reference(binding: PaymentBinding, operation_id: str) -> str:
    """Opaque full server-binding digest; not an authentication token."""
    operation_key(operation_id)
    raw = json.dumps([asdict(binding), operation_id], sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(raw.encode('ascii')).hexdigest()


class ProviderHttpClient:
    """One HTTP attempt. Stateless adapter; durable intent and retry decisions belong to the host."""

    def __init__(
        self,
        transport: AsyncTransport[ProviderHttpRequest, ProviderHttpResponse],
        *,
        timeout_seconds: int = 15,
        max_response_bytes: int = 262144,
    ) -> None:
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
            raise ValidationFailure('HTTP timeout must be between one and sixty seconds')
        if type(max_response_bytes) is not int or not 1024 <= max_response_bytes <= 1048576:
            raise ValidationFailure('Use a bounded provider response size')
        self._transport = transport
        self._timeout = timeout_seconds
        self._maximum = max_response_bytes

    async def json(self, method: Literal['GET', 'POST'], url: str, headers: Mapping[str, str], body: Any = None) -> Any:
        write = method == 'POST'
        request = ProviderHttpRequest(
            method,
            https_url(url),
            headers_lower(headers),
            None if body is None else encode_json(body),
            self._timeout,
            self._maximum,
        )
        try:
            async with asyncio.timeout(self._timeout):
                response = await self._transport.send(request)
            if not isinstance(response, ProviderHttpResponse) or response.redirected:
                raise ValueError('Invalid or redirected provider response')
            response_headers = headers_lower(response.headers)
            if response.status == 429 and not write:
                retry = response_headers.get('retry-after', '')
                seconds = int(retry) if retry.isascii() and retry.isdecimal() and len(retry) <= 6 else None
                raise ProviderRateLimited(seconds if seconds is not None and seconds <= 86400 else None)
            if type(response.status) is not int or not 200 <= response.status < 300:
                raise ValueError('Provider HTTP status did not establish success')
            return decode_json(response.body, maximum=self._maximum)
        except ProviderRateLimited:
            raise
        except asyncio.CancelledError:
            # Host cancellation does not cancel a remote effect; caller preserves its started intent.
            raise
        except Exception as error:
            failure = ProviderWriteUnknown if write else ProviderReadFailure
            raise failure('Provider write requires reconciliation' if write else 'Provider read failed') from error


def require_binding(binding: PaymentBinding, *, provider: str, merchant_id: str) -> None:
    if binding.provider != provider or binding.merchant_id != merchant_id:
        raise PermissionDenied('Payment binding does not belong to this configured provider merchant')
    if binding.route != 'external' or binding.subscription_id is not None:
        from ..errors import UnsupportedCapability

        raise UnsupportedCapability('This adapter supports external one-time orders only')
    if binding.amount.minor_units <= 0:
        raise ValidationFailure('Invoice amount must be positive')


def require_snapshot(snapshot: ProviderInvoice, binding: PaymentBinding, operation_id: str) -> None:
    if snapshot.amount != binding.amount or snapshot.binding_reference != binding_reference(binding, operation_id):
        raise PermissionDenied('Provider amount or immutable order reference differs')


def event_identity(*parts: str) -> str:
    return 'provider:' + hashlib.sha256(encode_json(list(parts))).hexdigest()
