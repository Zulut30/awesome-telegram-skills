import {PatternError, ValidationFailure, InvalidType, AuthenticationRequired, PermissionDenied,
  UnsupportedCapability, UnknownOutcome, safeErrorReport,
  type ErrorCategory, type ErrorCode, type ErrorOutcome, type ErrorReport,
  type OperationKind, type RecoveryAction} from '@awesome-telegram/patterns';
import {check} from './check.js';

export function referenceErrors(): void {
  const operation: OperationKind = 'write';
  const errors = [new PatternError('internal', 'unknown', 'PRIVATE_FIXTURE'),
    new ValidationFailure('PRIVATE_FIXTURE'), new InvalidType('PRIVATE_FIXTURE'),
    new AuthenticationRequired('PRIVATE_FIXTURE'), new PermissionDenied('PRIVATE_FIXTURE'),
    new UnsupportedCapability('PRIVATE_FIXTURE'), new UnknownOutcome('PRIVATE_FIXTURE')];
  for (const error of errors) {
    const value: ErrorReport = safeErrorReport(error, operation);
    const category: ErrorCategory = value.category;
    const code: ErrorCode = value.code;
    const outcome: ErrorOutcome = value.outcome;
    const recovery: RecoveryAction = value.recovery;
    check(category && code && outcome && recovery && !JSON.stringify(value).includes('PRIVATE_FIXTURE'));
    check(error.report().code === value.code);
    if (outcome === 'unknown') check(recovery === 'reconcile');
  }
  check(safeErrorReport(new Error('PRIVATE_FIXTURE'), operation).outcome === 'unknown');
  // Классификация не подтверждает отмену операции и не запускает retry.
}
