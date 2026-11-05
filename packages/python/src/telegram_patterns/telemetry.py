"""Allowlisted local telemetry; opaque correlation references never authorize work."""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import math
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterator, Literal, cast

from .errors import InvalidType, OperationKind, ValidationFailure, safe_error_report

TelemetryStage = Literal['update', 'action', 'operation', 'job']
TelemetryOutcome = Literal[
    'started', 'succeeded', 'replayed', 'rejected', 'failed', 'unknown', 'cancelled', 'quarantined'
]
_STAGES = frozenset({'update', 'action', 'operation', 'job'})
_OUTCOMES = frozenset({'started', 'succeeded', 'replayed', 'rejected', 'failed', 'unknown', 'cancelled', 'quarantined'})


@dataclass(frozen=True, slots=True)
class TelemetryContext:
    trace_id: str
    bot_ref: str
    update_ref: str | None = None
    action_ref: str | None = None
    operation_ref: str | None = None
    job_ref: str | None = None


@dataclass(frozen=True, slots=True)
class TelemetryMetric:
    stage: TelemetryStage
    outcome: TelemetryOutcome
    error_category: str
    count: int
    duration_ms_sum: float
    duration_ms_max: float
    retries: int


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    metrics: tuple[TelemetryMetric, ...]
    sink_failures: int


@dataclass(frozen=True, slots=True)
class _Binding:
    owner: str
    context: TelemetryContext


_CONTEXT: ContextVar[_Binding | None] = ContextVar('telegram_patterns_telemetry', default=None)


def _sync_callback(callback: Any) -> None:
    if not callable(callback) or any(
        predicate(candidate)
        for predicate in (inspect.iscoroutinefunction, inspect.isasyncgenfunction)
        for candidate in (callback, getattr(callback, '__call__', None))
    ):
        raise InvalidType('Use a fast synchronous telemetry sink')


def _reference_value(value: str | int) -> str:
    if type(value) is int and -(2**63) <= value <= 2**63 - 1:
        return f'int:{value}'
    try:
        valid = type(value) is str and bool(value) and len(value.encode('utf-8')) <= 512
    except UnicodeError:
        valid = False
    if not valid:
        raise ValidationFailure('Use bounded internal correlation identities')
    return 'str:' + cast(str, value)


class Telemetry:
    """Fixed schema + finite metric labels, optional best-effort serialized sink.

    No raw fields, URL, message, headers or exception strings are accepted as
    event attributes. Key is host-owned (>=32 bytes), never logged. HMAC refs
    are pseudonymous identifiers, not anonymization/auth/idempotency keys.
    A synchronous sink must be fast; no hidden queue/background service exists.
    """

    def __init__(self, key: bytes, sink: Callable[[str], Any] | None = None) -> None:
        if type(key) is not bytes or not 32 <= len(key) <= 1024:
            raise ValidationFailure('Use a dedicated telemetry HMAC key of 32 to 1024 bytes')
        if sink is not None:
            _sync_callback(sink)
        self._key = key
        self._sink = sink
        self._owner = uuid.uuid4().hex
        self._lock = threading.Lock()
        self._metrics: dict[tuple[str, str, str], list[float | int]] = {}
        self._sink_failures = 0

    def _ref(self, domain: str, bot_id: int, value: str | int) -> str:
        message = json.dumps([domain, bot_id, _reference_value(value)], separators=(',', ':')).encode('utf-8')
        return hmac.digest(self._key, message, hashlib.sha256).hex()[:32]

    @contextmanager
    def bind(
        self,
        *,
        bot_id: int,
        update_id: str | int | None = None,
        action_id: str | int | None = None,
        operation_id: str | int | None = None,
        job_id: str | int | None = None,
        inherit: bool = False,
    ) -> Iterator[TelemetryContext]:
        """Root binding by default; explicit inherit adds refs within the same bot."""
        if type(bot_id) is not int or not 1 <= bot_id <= 2**63 - 1 or type(inherit) is not bool:
            raise ValidationFailure('Use a positive bot ID and an explicit bool inherit flag')
        bot_ref = self._ref('bot', bot_id, bot_id)
        old = _CONTEXT.get()
        previous = old.context if inherit and old is not None and old.owner == self._owner else None
        if previous is not None and previous.bot_ref != bot_ref:
            raise ValidationFailure('Inherited telemetry context must belong to the same bot')

        def reference(domain: str, value: str | int | None) -> str | None:
            if value is not None:
                return self._ref(domain, bot_id, value)
            return getattr(previous, domain + '_ref') if previous is not None else None

        context = TelemetryContext(
            previous.trace_id if previous is not None else uuid.uuid4().hex,
            bot_ref,
            reference('update', update_id),
            reference('action', action_id),
            reference('operation', operation_id),
            reference('job', job_id),
        )
        token = _CONTEXT.set(_Binding(self._owner, context))
        try:
            yield context
        finally:
            _CONTEXT.reset(token)

    def current(self) -> TelemetryContext | None:
        binding = _CONTEXT.get()
        return binding.context if binding is not None and binding.owner == self._owner else None

    def emit(
        self,
        stage: TelemetryStage,
        outcome: TelemetryOutcome,
        *,
        duration_ms: float = 0,
        attempt: int = 1,
        error: BaseException | None = None,
        operation: OperationKind = 'read',
    ) -> None:
        if not isinstance(stage, str) or stage not in _STAGES:
            raise ValidationFailure('Use a documented telemetry stage')
        if not isinstance(outcome, str) or outcome not in _OUTCOMES:
            raise ValidationFailure('Use a documented telemetry outcome')
        if type(duration_ms) not in (float, int) or not 0 <= duration_ms <= 86400000 or not math.isfinite(duration_ms):
            raise ValidationFailure('Use duration between zero and one day in milliseconds')
        if type(attempt) is not int or not 1 <= attempt <= 1000:
            raise ValidationFailure('Use attempt between 1 and 1000')
        if not isinstance(operation, str) or operation not in {'read', 'write'}:
            raise ValidationFailure('Use read or write operation kind')
        report = safe_error_report(error, operation=operation) if error is not None else None
        category = report.category if report is not None else 'none'
        context = self.current()
        event = {
            'stage': stage,
            'outcome': outcome,
            'duration_ms': float(duration_ms),
            'attempt': attempt,
            'error_code': report.code if report is not None else None,
            'error_category': category,
            'error_outcome': report.outcome if report is not None else None,
            'context': asdict(context) if context is not None else None,
        }
        with self._lock:
            values = self._metrics.setdefault((stage, outcome, category), [0, 0.0, 0.0, 0])
            values[0] += 1
            values[1] += duration_ms
            values[2] = max(values[2], duration_ms)
            values[3] += int(attempt > 1)
        if self._sink is not None:
            try:
                result = self._sink(json.dumps(event, separators=(',', ':'), sort_keys=True))
                if inspect.isawaitable(result) or inspect.isasyncgen(result):
                    if inspect.iscoroutine(result):
                        result.close()
                    raise InvalidType('Telemetry sink must complete synchronously')
            except Exception:
                with self._lock:
                    self._sink_failures += 1

    def snapshot(self) -> TelemetrySnapshot:
        """Metrics never contain individual refs; fixed enum/category labels only."""
        with self._lock:
            metrics = tuple(
                TelemetryMetric(
                    cast(TelemetryStage, stage),
                    cast(TelemetryOutcome, outcome),
                    category,
                    int(values[0]),
                    float(values[1]),
                    float(values[2]),
                    int(values[3]),
                )
                for (stage, outcome, category), values in sorted(self._metrics.items())
            )
            return TelemetrySnapshot(metrics, self._sink_failures)
