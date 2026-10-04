"""Классификация без сериализации текста исключения и без повторной записи."""
import json
from telegram_patterns import (
    AuthenticationRequired, ConflictFailure, ErrorCategory, ErrorCode, ErrorOutcome,
    ErrorReport, InvalidCompletion, InvalidType, OperationKind, PatternError,
    PermissionDenied, RecoveryAction, TimeoutFailure, TransportFailure, UnknownOutcome,
    UnsupportedCapability, ValidationFailure, safe_error_report,
)

operation: OperationKind = 'write'
errors = [PatternError('PRIVATE_FIXTURE'), ValidationFailure('PRIVATE_FIXTURE'),
          InvalidType('PRIVATE_FIXTURE'), AuthenticationRequired('PRIVATE_FIXTURE'),
          PermissionDenied('PRIVATE_FIXTURE'), UnsupportedCapability('PRIVATE_FIXTURE'),
          ConflictFailure('PRIVATE_FIXTURE'), TimeoutFailure('PRIVATE_FIXTURE'),
          TransportFailure('PRIVATE_FIXTURE'), UnknownOutcome('PRIVATE_FIXTURE'),
          InvalidCompletion('PRIVATE_FIXTURE')]
for error in errors:
    value: ErrorReport = error.report(operation=operation)
    category: ErrorCategory = value.category
    code: ErrorCode = value.code
    outcome: ErrorOutcome = value.outcome
    recovery: RecoveryAction = value.recovery
    assert value == safe_error_report(error, operation=operation)
    assert category and code and recovery and 'PRIVATE_FIXTURE' not in json.dumps(value.as_dict())
    if outcome == 'unknown': assert recovery == 'reconcile'
assert safe_error_report(ValidationFailure(), operation=operation).outcome == 'rejected'
assert safe_error_report(InvalidCompletion(), operation=operation).outcome == 'unknown'
print(json.dumps({'passed': True, 'case': 'core_errors', 'network': False}))
