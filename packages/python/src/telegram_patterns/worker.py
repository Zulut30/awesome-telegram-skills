"""SDK-free lifecycle composition over SQLiteInbox; transport/resources stay host-owned."""

from __future__ import annotations

import asyncio
import inspect
import math
import time
from contextlib import nullcontext
from typing import Any, Awaitable, Callable, Generic, Literal, ParamSpec, TypeVar

from .errors import InvalidType, UnknownOutcome, ValidationFailure
from .inbox import InboxClaim, InboxLeaseLost, InboxReason, SQLiteInbox
from .telemetry import Telemetry

P = ParamSpec('P')
T = TypeVar('T')
WorkerOutcome = Literal['idle', 'done', 'quarantined', 'lease-lost']


def _sync_result(value: Any) -> None:
    if inspect.isawaitable(value) or inspect.isasyncgen(value):
        if inspect.iscoroutine(value):
            value.close()
        raise InvalidType('Use a synchronous local callable')


def _sync_callback(callback: Any) -> None:
    if not callable(callback) or any(
        predicate(candidate)
        for predicate in (inspect.iscoroutinefunction, inspect.isasyncgenfunction)
        for candidate in (callback, getattr(callback, '__call__', None))
    ):
        raise InvalidType('Use a synchronous local callable')


async def settled_to_thread(action: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Join finite owned local work before propagating even repeated cancellation.

    Not a timeout/kill mechanism. The host must bound the local operation. This
    prevents closing resources while a cancelled await still has a live writer.
    """
    _sync_callback(action)

    def invoke() -> T:
        result = action(*args, **kwargs)
        _sync_result(result)
        return result

    work = asyncio.create_task(asyncio.to_thread(invoke))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        while not work.done():
            try:
                await asyncio.shield(work)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not work.cancelled():
            try:
                work.result()
            except Exception:
                pass
        raise


class InboxWorker(Generic[T]):
    """One-at-a-time accepted Update processing; no ACK, transport or sessions.

    Decode is local/synchronous and validates supported SDK event semantics.
    Handler must return exactly True after durable business completion. False,
    errors and cancellation quarantine the original payload; they never ACK as
    done. A lost lease may be recovered/replayed by SQLiteInbox: host effects
    therefore need stable operation IDs and outbox/unknown reconciliation.
    """

    def __init__(
        self,
        inbox: SQLiteInbox,
        bot_id: int,
        worker_id: str,
        decode: Callable[[dict[str, Any]], T],
        handle: Callable[[T, InboxClaim], Awaitable[bool]],
        *,
        lease_seconds: float = 60,
        idle_seconds: float = 0.25,
        telemetry: Telemetry | None = None,
    ) -> None:
        if not isinstance(inbox, SQLiteInbox):
            raise InvalidType('Use the existing SQLiteInbox')
        if type(bot_id) is not int or not 1 <= bot_id <= 2**63 - 1:
            raise ValidationFailure('Use a positive bounded bot ID')
        try:
            valid_worker = isinstance(worker_id, str) and bool(worker_id) and len(worker_id.encode('utf-8')) <= 128
        except UnicodeError:
            valid_worker = False
        if not valid_worker:
            raise ValidationFailure('Use a bounded worker ID')
        for value, minimum, maximum in ((lease_seconds, 0, 3600), (idle_seconds, 0, 60)):
            if type(value) not in (int, float) or not minimum < value <= maximum or not math.isfinite(value):
                raise ValidationFailure('Use positive bounded worker timing')
        _sync_callback(decode)
        if not callable(handle):
            raise InvalidType('Use an asynchronous handler')
        if telemetry is not None and not isinstance(telemetry, Telemetry):
            raise InvalidType('Use Telemetry or None')
        self.inbox, self.bot_id, self.worker_id = inbox, bot_id, worker_id
        self.decode, self.handle = decode, handle
        self.lease_seconds, self.idle_seconds, self.telemetry = lease_seconds, idle_seconds, telemetry
        self._serving = False
        self._running = False

    async def _quarantine(self, claim: InboxClaim, reason: InboxReason) -> WorkerOutcome:
        await settled_to_thread(self.inbox.quarantine, claim, reason=reason)
        return 'quarantined'

    async def run_one(self) -> WorkerOutcome:
        if self._running:
            raise ValidationFailure('This worker already has an active job/admission')
        self._running = True
        try:
            return await self._run_one()
        finally:
            self._running = False

    async def _run_one(self) -> WorkerOutcome:
        claim = await settled_to_thread(self.inbox.claim, self.bot_id, self.worker_id, lease_seconds=self.lease_seconds)
        if claim is None:
            return 'idle'
        binding = (
            self.telemetry.bind(bot_id=self.bot_id, update_id=claim.update_id, job_id=claim.update_id)
            if self.telemetry is not None
            else nullcontext()
        )
        with binding:
            started = time.perf_counter()

            def emit(
                outcome: Literal['succeeded', 'quarantined', 'unknown', 'cancelled'], error: BaseException | None = None
            ) -> None:
                if self.telemetry is not None:
                    self.telemetry.emit(
                        'job',
                        outcome,
                        duration_ms=min(86400000, max(0, (time.perf_counter() - started) * 1000)),
                        attempt=claim.attempt,
                        error=error,
                        operation='write',
                    )

            try:
                try:
                    decoded = self.decode(claim.payload)
                    _sync_result(decoded)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    result = await self._quarantine(claim, 'decode-failed')
                    emit('quarantined', error)
                    return result
                try:
                    pending = self.handle(decoded, claim)
                    if not inspect.isawaitable(pending):
                        raise InvalidType('Handler must return an awaitable')
                    accepted = await pending
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    result = await self._quarantine(claim, 'processing-failed')
                    emit('quarantined', error)
                    return result
                if accepted is not True:
                    result = await self._quarantine(claim, 'handler-rejected')
                    emit('quarantined')
                    return result
                await settled_to_thread(self.inbox.complete, claim)
                emit('succeeded')
                return 'done'
            except asyncio.CancelledError as error:
                try:
                    await self._quarantine(claim, 'processing-failed')
                except (asyncio.CancelledError, Exception):
                    # Expired/committed claim or unavailable store remains durable;
                    # preserve cancellation, never report complete for this path.
                    pass
                emit('cancelled', error)
                raise
            except InboxLeaseLost:
                emit('unknown', UnknownOutcome())
                return 'lease-lost'

    async def serve(self, stop_event: asyncio.Event) -> None:
        """Stop admitting claims once requested, then drain the current job.

        Owner handles OS signals and closes sessions/stores AFTER awaiting this
        method. Cancellation interrupts a handler conservatively and joins any
        local DB thread first. It never starts a polling consumer or drops data.
        """
        if not isinstance(stop_event, asyncio.Event):
            raise InvalidType('Use the host stop Event')
        if self._serving:
            raise ValidationFailure('This worker already has a serve owner')
        self._serving = True
        try:
            while not stop_event.is_set():
                outcome = await self.run_one()
                if outcome == 'idle':
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=self.idle_seconds)
                    except TimeoutError:
                        pass
        finally:
            self._serving = False
