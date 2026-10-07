"""Safe error metadata; classification never retries or changes business state."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Literal, TypeAlias, cast

ErrorCategory: TypeAlias = Literal['validation', 'permission', 'unsupported', 'timeout', 'network', 'conflict', 'cancelled', 'internal', 'unknown-outcome', 'rate-limit', 'server']
ErrorOutcome: TypeAlias = Literal['rejected', 'read-failed', 'unknown']
RecoveryAction: TypeAlias = Literal['fix-input', 'authenticate', 'check-permissions', 'use-fallback', 'retry-read', 'retry-later', 'reconcile', 'none']
OperationKind: TypeAlias = Literal['read', 'write']
ErrorCode: TypeAlias = Literal['validation-failed', 'invalid-init-data', 'invalid-api-request', 'invalid-field', 'authentication-required', 'permission-denied', 'unsupported-capability', 'timeout', 'network', 'operation-conflict', 'cancelled', 'internal', 'unknown-outcome', 'invalid-response', 'rate-limited', 'server-error']

_DESCRIPTORS: dict[str, tuple[ErrorCategory, RecoveryAction, str]] = {
    'validation-failed': ('validation', 'fix-input', 'Проверьте входные данные.'),
    'invalid-init-data': ('validation', 'authenticate', 'Откройте приложение заново для входа.'),
    'invalid-api-request': ('validation', 'fix-input', 'Проверьте параметры запроса.'),
    'invalid-field': ('validation', 'fix-input', 'Проверьте значение поля.'),
    'authentication-required': ('permission', 'authenticate', 'Требуется вход в приложение.'),
    'permission-denied': ('permission', 'check-permissions', 'Недостаточно прав для действия.'),
    'unsupported-capability': ('unsupported', 'use-fallback', 'Функция недоступна в текущем окружении.'),
    'timeout': ('timeout', 'retry-read', 'Ответ не получен вовремя.'),
    'network': ('network', 'retry-read', 'Не удалось получить ответ.'),
    'operation-conflict': ('conflict', 'reconcile', 'Проверьте состояние существующей операции.'),
    'cancelled': ('cancelled', 'none', 'Ожидание ответа отменено.'),
    'internal': ('internal', 'none', 'Не удалось обработать действие.'),
    'unknown-outcome': ('unknown-outcome', 'reconcile', 'Результат операции пока не подтвержден.'),
    'invalid-response': ('validation', 'none', 'Получен неподдерживаемый ответ сервера.'),
    'rate-limited': ('rate-limit', 'retry-later', 'Слишком много запросов. Повторите позже.'),
    'server-error': ('server', 'retry-read', 'Сервер временно не смог обработать запрос.'),
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

    def report(self, *, operation: OperationKind = 'read') -> ErrorReport:
        return safe_error_report(self, operation=operation)


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


def safe_error_report(error: BaseException, *, operation: OperationKind = 'read') -> ErrorReport:
    """Known metadata only, no exception str/args/stack/payload in public output.

    Unknown write outcome always requires reconciliation, never automatic retry.
    Callers must supply the actual operation kind; no I/O is performed here.
    """
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
    outcome: ErrorOutcome = known if isinstance(known, str) and known in {'rejected', 'read-failed', 'unknown'} else ('unknown' if operation == 'write' else 'read-failed')
    category, recovery, message = _DESCRIPTORS[code]
    if outcome == 'unknown':
        recovery = 'reconcile'
        message = 'Результат операции пока не подтвержден. Проверьте ее статус.'
    return ErrorReport(cast(ErrorCode, code), category, outcome, recovery, message)
