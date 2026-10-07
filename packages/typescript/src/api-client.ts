import {PatternError, ValidationFailure, type ErrorCode} from './errors.js';
import type {FetchTransport} from './adapters.js';

export type FailureKind = 'http' | 'network' | 'timeout' | 'aborted' | 'invalid-response';
const MAX_RETRY_AFTER_MS = 86_400_000;
/** setTimeout fires immediately for larger delays. */
const MAX_TIMEOUT_MS = 2_147_483_647;

/** HTTP status → error code. The response body is never parsed for classification. */
function httpErrorCode(status: number): ErrorCode {
  if (status === 400 || status === 422) return 'validation-failed';
  if (status === 401) return 'authentication-required';
  if (status === 403) return 'permission-denied';
  if (status === 408) return 'timeout';
  if (status === 409) return 'operation-conflict';
  if (status === 429) return 'rate-limited';
  if (status >= 400 && status <= 499) return 'invalid-api-request';
  if (status >= 500 && status <= 599) return 'server-error';
  return 'network';
}

/** `Retry-After` as delay-seconds or HTTP-date, bounded to one day; invalid values are ignored. */
function parseRetryAfter(value: string | null, now: number = Date.now()): number | undefined {
  if (value === null) return undefined;
  const text = value.trim();
  if (/^\d{1,9}$/.test(text)) return Math.min(Number(text) * 1000, MAX_RETRY_AFTER_MS);
  // Every HTTP-date form (RFC 9110) starts with a day name; Date.parse alone accepts '-5'.
  const date = /^[A-Za-z]{3}/.test(text) ? Date.parse(text) : Number.NaN;
  return Number.isNaN(date) ? undefined : Math.min(Math.max(0, date - now), MAX_RETRY_AFTER_MS);
}

export class ApiError extends PatternError {
  declare readonly outcome: 'unknown' | 'read-failed' | 'rejected';
  constructor(readonly kind: FailureKind, readonly status: number | undefined,
              outcome: 'unknown' | 'read-failed' | 'rejected', readonly retryAfterMs?: number) {
    const code: ErrorCode = kind === 'aborted' ? 'cancelled'
      : kind === 'http' ? (status === undefined ? 'network' : httpErrorCode(status)) : kind;
    super(code, outcome, `API request failed: ${kind}`);
    this.name = 'ApiError';
  }
}
export interface RequestOptions {
  method?: 'GET' | 'HEAD' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Overrides ClientOptions.rejectedBeforeEffect for this endpoint's contract. */
  rejectedBeforeEffect?: readonly number[];
}
export interface ClientOptions {
  baseUrl: string;
  headers?: () => HeadersInit;
  fetch?: FetchTransport;
  /**
   * HTTP statuses that the backend contract returns only before any effect.
   * A write failing with one of them is `rejected` (fix input, sign in, retry later)
   * instead of the conservative `unknown` + reconcile. Reads are unaffected.
   */
  rejectedBeforeEffect?: readonly number[];
}

function statusSet(values: readonly number[] | undefined): ReadonlySet<number> {
  if (values === undefined) return new Set();
  if (!Array.isArray(values) || values.some(v => !Number.isInteger(v) || v < 400 || v > 599)) {
    throw new ValidationFailure('rejectedBeforeEffect accepts HTTP error statuses 400-599');
  }
  return new Set(values);
}

/** One fetch invocation, runtime decoding, no application retry or token storage.
 * Browser/proxy transport may repeat HTTP; server idempotency remains required.
 */
export class ApiClient {
  private readonly base: URL;
  /** Base URL as a directory: `/api/v1` becomes `/api/v1/`, without query or fragment. */
  private readonly prefix: URL;
  private readonly transport: FetchTransport;
  private readonly rejected: ReadonlySet<number>;
  constructor(private readonly options: ClientOptions) {
    try { this.base = new URL(options.baseUrl); }
    catch { throw new ValidationFailure('Configure a valid absolute HTTP(S) base URL'); }
    if (!['http:', 'https:'].includes(this.base.protocol) || this.base.username || this.base.password) {
      throw new ValidationFailure('Configure an HTTP(S) base URL without credentials');
    }
    this.prefix = new URL(this.base.href);
    this.prefix.search = ''; this.prefix.hash = '';
    if (!this.prefix.pathname.endsWith('/')) this.prefix.pathname += '/';
    this.rejected = statusSet(options.rejectedBeforeEffect);
    this.transport = options.fetch ?? globalThis.fetch.bind(globalThis);
  }
  /** `orders` and `/orders` both resolve inside the base path; absolute URLs must stay there too. */
  private resolve(path: string): URL {
    if (typeof path !== 'string' || path.startsWith('//')) throw new ValidationFailure('Configure a valid API path');
    let url: URL;
    try { url = /^[a-z][a-z\d+.-]*:/i.test(path) ? new URL(path) : new URL(path.replace(/^\//, ''), this.prefix); }
    catch { throw new ValidationFailure('Configure a valid API path'); }
    if (url.origin !== this.base.origin) throw new ValidationFailure('Cross-origin API path rejected');
    if (!url.pathname.startsWith(this.prefix.pathname)) throw new ValidationFailure('API path escapes the configured base path');
    return url;
  }
  async request<T>(path: string, decode: (value: unknown) => T, options: RequestOptions = {}): Promise<T> {
    const url = this.resolve(path);
    const method = options.method ?? 'GET';
    const outcome = method === 'GET' || method === 'HEAD' ? 'read-failed' : 'unknown';
    const rejected = options.rejectedBeforeEffect === undefined ? this.rejected : statusSet(options.rejectedBeforeEffect);
    const timeout = options.timeoutMs ?? 10000;
    if (!Number.isFinite(timeout) || timeout <= 0 || timeout > MAX_TIMEOUT_MS) {
      throw new ValidationFailure('Timeout must be positive and at most 2147483647 ms');
    }
    let headers: Headers;
    // Nothing was sent yet: report a rejected attempt without the callback's own message.
    try { headers = new Headers(this.options.headers?.()); }
    catch { throw new PatternError('internal', 'rejected', 'Request headers callback failed'); }
    headers.set('Accept', 'application/json');
    let body: string | undefined;
    if (options.body !== undefined) {
      if (method === 'GET' || method === 'HEAD') throw new ValidationFailure('Read method cannot have a body');
      try { body = JSON.stringify(options.body); }
      catch { throw new ValidationFailure('Request body must be JSON-serializable'); }
      if (body === undefined) throw new ValidationFailure('Request body must be JSON-serializable');
      headers.set('Content-Type', 'application/json');
    }
    const controller = new AbortController();
    let timedOut = false;
    const abort = () => controller.abort(options.signal?.reason);
    options.signal?.addEventListener('abort', abort, { once: true });
    if (options.signal?.aborted) abort();
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
    try {
      const init: RequestInit = { method, headers, credentials: 'same-origin', redirect: 'error', signal: controller.signal };
      if (body !== undefined) init.body = body;
      const response = await this.transport(url, init);
      if (!response.ok) {
        const known = outcome === 'unknown' && rejected.has(response.status) ? 'rejected' : outcome;
        throw new ApiError('http', response.status, known,
          response.status === 429 || response.status === 503 ? parseRetryAfter(response.headers.get('Retry-After')) : undefined);
      }
      let value: unknown = null;
      if (method !== 'HEAD' && response.status !== 204 && response.status !== 205) {
        try { value = await response.json(); }
        catch (error) {
          if (controller.signal.aborted) throw error;
          // Reading the transport and validating the application's JSON schema
          // are separate failure boundaries. Truncated bodies are not JSON errors.
          if (error instanceof SyntaxError) throw new ApiError('invalid-response', response.status, outcome);
          throw new ApiError('network', response.status, outcome);
        }
      }
      try {
        const result = decode(value);
        if (controller.signal.aborted) throw new Error('Request aborted');
        return result;
      } catch (error) {
        if (controller.signal.aborted) throw error;
        throw new ApiError('invalid-response', response.status, outcome);
      }
    } catch (error) {
      if (controller.signal.aborted) throw new ApiError(timedOut ? 'timeout' : 'aborted', undefined, outcome);
      if (error instanceof ApiError) throw error;
      throw new ApiError('network', undefined, outcome);
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener('abort', abort);
    }
  }
}
