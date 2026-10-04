"""Structural extension contracts; no SDK, framework or connection ownership."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Protocol, TypeVar

from .sqlite_once import OnceResult

_Transaction_co = TypeVar('_Transaction_co', covariant=True)
_Request_contra = TypeVar('_Request_contra', contravariant=True)
_Response_co = TypeVar('_Response_co', covariant=True)
_Event_co = TypeVar('_Event_co', covariant=True)


class OnceStore(Protocol[_Transaction_co]):
    """Effect + replay result atomic in one owned storage transaction.

    Authorization precedes both new effects and returned replay results.
    initialize is explicit; a custom adapter may use the host's migration.
    """
    def initialize(self) -> None: ...

    def run(self, scope: str, operation_key: str, payload: Any,
            apply: Callable[[_Transaction_co], Any]) -> OnceResult: ...


class AsyncTransport(Protocol[_Request_contra, _Response_co]):
    """Single application invocation; adapter documents actual wire retries.

    The supplied transport remains owned by the host. Unknown write outcomes
    must propagate; the interface alone supplies no idempotency guarantee.
    """
    async def send(self, request: _Request_contra) -> _Response_co: ...


class ProviderAdapter(Protocol[_Request_contra, _Response_co, _Event_co]):
    """Provider-specific request, snapshot and authenticated event models.

    create/get may perform I/O; verify_event does local verification/parsing.
    An authenticated event is not proof of payment or permission to grant.
    """
    async def create(self, request: _Request_contra, *, operation_id: str) -> _Response_co: ...

    async def get(self, provider_id: str) -> _Response_co: ...

    def verify_event(self, body: bytes, headers: Mapping[str, str]) -> _Event_co | None: ...


class RefundProvider(Protocol[_Request_contra, _Response_co]):
    """Optional extension; creation providers need not support refunds."""
    async def refund(self, request: _Request_contra, *, operation_id: str) -> _Response_co: ...
