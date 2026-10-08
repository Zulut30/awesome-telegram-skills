"""Safe error metadata; classification never retries or changes business state."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias, cast

if TYPE_CHECKING:
    from .texts import Texts

ErrorCategory: TypeAlias = Literal[
    'validation',
    'permission',
    'unsupported',
    'timeout',
    'network',
    'conflict',
    'cancelled',
    'internal',
    'unknown-outcome',
    'rate-limit',
    'server',
]
ErrorOutcome: TypeAlias = Literal['rejected', 'read-failed', 'unknown']
RecoveryAction: TypeAlias = Literal[
    'fix-input', 'authenticate', 'check-permissions', 'use-fallback', 'retry-read', 'retry-later', 'reconcile', 'none'
]
OperationKind: TypeAlias = Literal['read', 'write']
ErrorCode: TypeAlias = Literal[
    'validation-failed',
    'invalid-init-data',
    'invalid-api-request',
    'invalid-field',
    'authentication-required',
    'permission-denied',
    'unsupported-capability',
    'timeout',
    'network',
    'operation-conflict',
    'cancelled',
    'internal',
    'unknown-outcome',
    'invalid-response',
    'rate-limited',
    'server-error',
]

# The public message of each code is the text 'error.<code>' of telegram_patterns.texts.
_DESCRIPTORS: dict[str, tuple[ErrorCategory, RecoveryAction]] = {
    'validation-failed': ('validation', 'fix-input'),
    'invalid-init-data': ('validation', 'authenticate'),
    'invalid-api-request': ('validation', 'fix-input'),
    'invalid-field': ('validation', 'fix-input'),
    'authentication-required': ('permission', 'authenticate'),
    'permission-denied': ('permission', 'check-permissions'),
    'unsupported-capability': ('unsupported', 'use-fallback'),
    'timeout': ('timeout', 'retry-read'),
    'network': ('network', 'retry-read'),
    'operation-conflict': ('conflict', 'reconcile'),
    'cancelled': ('cancelled', 'none'),
    'internal': ('internal', 'none'),
    'unknown-outcome': ('unknown-outcome', 'reconcile'),
    'invalid-response': ('validation', 'none'),
    'rate-limited': ('rate-limit', 'retry-later'),
    'server-error': ('server', 'retry-read'),
}


@dataclass(frozen=True, slots=True)
class ErrorReport:
    code: ErrorCode
    category: ErrorCategory
    outcome: ErrorOutcome
    recovery: RecoveryAction
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


class PatternError(Exception):
    """Developer exception text is not copied to the public ErrorReport."""

    code: ErrorCode = 'internal'
    _known_outcome: ErrorOutcome | None = None

    def report(self, *, operation: OperationKind = 'read', texts: Texts | None = None) -> ErrorReport:
        return safe_error_report(self, operation=operation, texts=texts)


class ValidationFailure(PatternError, ValueError):
    """Known local/pre-effect validation rejection, not arbitrary remote failure."""

    code: ErrorCode = 'validation-failed'
    _known_outcome = 'rejected'


class PermissionDenied(PatternError):
    """Host verified rejection before effect; remote denial needs its contract."""

    code: ErrorCode = 'permission-denied'
    _known_outcome = 'rejected'


class AuthenticationRequired(PatternError):
    code: ErrorCode = 'authentication-required'
    _known_outcome = 'rejected'


class InvalidType(ValidationFailure, TypeError):
    """Known local type rejection; preserves legacy TypeError catches."""


class UnsupportedCapability(PatternError):
    code: ErrorCode = 'unsupported-capability'
    _known_outcome = 'rejected'


class TimeoutFailure(PatternError):
    code: ErrorCode = 'timeout'


class TransportFailure(PatternError):
    code: ErrorCode = 'network'


class ConflictFailure(PatternError, ValueError):
    code: ErrorCode = 'operation-conflict'
    _known_outcome = 'rejected'


class UnknownOutcome(PatternError):
    code: ErrorCode = 'unknown-outcome'
    _known_outcome = 'unknown'


class InvalidCompletion(UnknownOutcome, ValueError):
    """An effect may have happened before a callback returned invalid feedback."""


def safe_error_report(
    error: BaseException, *, operation: OperationKind = 'read', texts: Texts | None = None
) -> ErrorReport:
    """Known metadata only, no exception str/args/stack/payload in public output.

    Unknown write outcome always requires reconciliation, never automatic retry.
    Callers must supply the actual operation kind; no I/O is performed here.
    message is the text 'error.<code>' of texts (Russian by default).
    """
    from .texts import Texts  # texts imports this module

    if texts is None:
        texts = Texts()
    elif not isinstance(texts, Texts):
        raise InvalidType('Use Texts or None')
    if operation not in {'read', 'write'}:
        raise ValidationFailure('Use read or write operation kind')
    if not isinstance(error, BaseException):
        raise InvalidType('Use an exception, not an external error payload')
    code: str = 'internal'
    known: ErrorOutcome | None = None
    if isinstance(error, PatternError):
        candidate = type(error).code
        if isinstance(candidate, str) and candidate in _DESCRIPTORS:
            code = candidate
            known = type(error)._known_outcome
    elif isinstance(error, TimeoutError):
        code = 'timeout'
    elif isinstance(error, asyncio.CancelledError):
        code = 'cancelled'
    elif isinstance(error, PermissionError):
        code = 'permission-denied'
    outcome: ErrorOutcome = (
        known
        if isinstance(known, str) and known in {'rejected', 'read-failed', 'unknown'}
        else ('unknown' if operation == 'write' else 'read-failed')
    )
    category, recovery = _DESCRIPTORS[code]
    message = texts('error.' + code)
    if outcome == 'unknown':
        recovery = 'reconcile'
        message = texts('error.unknown-outcome-write')
    return ErrorReport(cast(ErrorCode, code), category, outcome, recovery, message)
