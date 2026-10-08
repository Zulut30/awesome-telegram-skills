/** Safe public metadata. Never serializes exception text, stack or payload. */
export type ErrorCategory = 'validation' | 'permission' | 'unsupported' | 'timeout' | 'network' | 'conflict' | 'cancelled' | 'internal' | 'unknown-outcome' | 'rate-limit' | 'server';
export type ErrorOutcome = 'rejected' | 'read-failed' | 'unknown';
export type RecoveryAction = 'fix-input' | 'authenticate' | 'check-permissions' | 'use-fallback' | 'retry-read' | 'retry-later' | 'reconcile' | 'none';
export type OperationKind = 'read' | 'write';
export type ErrorCode = 'validation-failed' | 'invalid-init-data' | 'invalid-api-request' | 'invalid-field' | 'authentication-required' | 'permission-denied' | 'unsupported-capability' | 'timeout' | 'network' | 'operation-conflict' | 'cancelled' | 'internal' | 'unknown-outcome' | 'invalid-response' | 'rate-limited' | 'server-error';
export interface ErrorReport {
  readonly code: ErrorCode;
  readonly category: ErrorCategory;
  readonly outcome: ErrorOutcome;
  readonly recovery: RecoveryAction;
  readonly message: string;
}

const descriptions: Record<ErrorCode, readonly [ErrorCategory, RecoveryAction, string]> = {
  'validation-failed': ['validation', 'fix-input', 'Проверьте входные данные.'],
  'invalid-init-data': ['validation', 'authenticate', 'Откройте приложение заново для входа.'],
  'invalid-api-request': ['validation', 'fix-input', 'Проверьте параметры запроса.'],
  'invalid-field': ['validation', 'fix-input', 'Проверьте значение поля.'],
  'authentication-required': ['permission', 'authenticate', 'Требуется вход в приложение.'],
  'permission-denied': ['permission', 'check-permissions', 'Недостаточно прав для действия.'],
  'unsupported-capability': ['unsupported', 'use-fallback', 'Функция недоступна в текущем окружении.'],
  timeout: ['timeout', 'retry-read', 'Ответ не получен вовремя.'],
  network: ['network', 'retry-read', 'Не удалось получить ответ.'],
  'operation-conflict': ['conflict', 'reconcile', 'Проверьте состояние существующей операции.'],
  cancelled: ['cancelled', 'none', 'Ожидание ответа отменено.'],
  internal: ['internal', 'none', 'Не удалось обработать действие.'],
  'unknown-outcome': ['unknown-outcome', 'reconcile', 'Результат операции пока не подтвержден.'],
  'invalid-response': ['validation', 'none', 'Получен неподдерживаемый ответ сервера.'],
  'rate-limited': ['rate-limit', 'retry-later', 'Слишком много запросов. Повторите позже.'],
  'server-error': ['server', 'retry-read', 'Сервер временно не смог обработать запрос.'],
};

function report(code: ErrorCode, outcome: ErrorOutcome): ErrorReport {
  if (!Object.hasOwn(descriptions, code)) code = 'internal';
  if (outcome !== 'rejected' && outcome !== 'read-failed' && outcome !== 'unknown') outcome = 'unknown';
  const [category, recovery, message] = descriptions[code];
  return Object.freeze({code, category, outcome,
    recovery: outcome === 'unknown' ? 'reconcile' : recovery,
    message: outcome === 'unknown' ? 'Результат операции пока не подтвержден. Проверьте ее статус.' : message});
}

export class PatternError extends Error {
  readonly category: ErrorCategory;
  readonly recovery: RecoveryAction;
  constructor(readonly code: ErrorCode, readonly outcome: ErrorOutcome, developerMessage?: string) {
    const value = report(code, outcome);
    super(developerMessage ?? value.message);
    this.name = new.target.name;
    this.category = value.category;
    this.recovery = value.recovery;
  }
  report(): ErrorReport { return report(this.code, this.outcome); }
}
export class ValidationFailure extends PatternError {
  constructor(message?: string) { super('validation-failed', 'rejected', message); }
}
export class PermissionDenied extends PatternError {
  constructor(message?: string) { super('permission-denied', 'rejected', message); }
}
export class AuthenticationRequired extends PatternError {
  constructor(message?: string) { super('authentication-required', 'rejected', message); }
}
export class UnsupportedCapability extends PatternError {
  constructor(message?: string) { super('unsupported-capability', 'rejected', message); }
}
export class UnknownOutcome extends PatternError {
  constructor(message?: string) { super('unknown-outcome', 'unknown', message); }
}
/** Preserves TypeError catches at existing native event argument boundaries. */
export class InvalidType extends TypeError {
  constructor(message?: string) { super(message ?? descriptions['validation-failed'][2]); this.name = 'InvalidType'; }
  report(): ErrorReport { return report('validation-failed', 'rejected'); }
}

export function safeErrorReport(error: unknown, operation: OperationKind = 'read'): ErrorReport {
  if (operation !== 'read' && operation !== 'write') throw new ValidationFailure('Use read or write operation kind');
  if (error instanceof InvalidType) return report('validation-failed', 'rejected');
  if (error instanceof PatternError) return report(error.code, error.outcome);
  if (typeof DOMException !== 'undefined' && error instanceof DOMException) {
    if (error.name === 'TimeoutError') return report('timeout', operation === 'write' ? 'unknown' : 'read-failed');
    if (error.name === 'AbortError') return report('cancelled', operation === 'write' ? 'unknown' : 'read-failed');
  }
  // Arbitrary objects, DOM errors and exceptions have no proven write outcome.
  return report('internal', operation === 'write' ? 'unknown' : 'read-failed');
}
