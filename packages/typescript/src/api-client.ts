export type FailureKind = 'http' | 'network' | 'timeout' | 'aborted' | 'invalid-response';
export class ApiError extends Error {
  constructor(readonly kind: FailureKind, readonly status: number | undefined,
              readonly outcome: 'unknown' | 'read-failed') {
    super(`API request failed: ${kind}`);
    this.name = 'ApiError';
  }
}
export interface RequestOptions {
  method?: 'GET' | 'HEAD' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
}
export interface ClientOptions {
  baseUrl: string;
  headers?: () => HeadersInit;
  fetch?: typeof fetch;
}

/** One fetch invocation, runtime decoding, no application retry or token storage.
 * Browser/proxy transport may repeat HTTP; server idempotency remains required.
 */
export class ApiClient {
  private readonly base: URL;
  private readonly transport: typeof fetch;
  constructor(private readonly options: ClientOptions) {
    this.base = new URL(options.baseUrl);
    if (!['http:', 'https:'].includes(this.base.protocol) || this.base.username || this.base.password) {
      throw new Error('Configure an HTTP(S) base URL without credentials');
    }
    this.transport = options.fetch ?? globalThis.fetch.bind(globalThis);
  }
  async request<T>(path: string, decode: (value: unknown) => T, options: RequestOptions = {}): Promise<T> {
    const url = new URL(path, this.base);
    if (url.origin !== this.base.origin) throw new Error('Cross-origin API path rejected');
    const method = options.method ?? 'GET';
    const outcome = method === 'GET' || method === 'HEAD' ? 'read-failed' : 'unknown';
    const timeout = options.timeoutMs ?? 10000;
    if (!Number.isFinite(timeout) || timeout <= 0) throw new Error('Positive timeout required');
    const headers = new Headers(this.options.headers?.());
    headers.set('Accept', 'application/json');
    let body: string | undefined;
    if (options.body !== undefined) {
      if (method === 'GET' || method === 'HEAD') throw new Error('Read method cannot have a body');
      body = JSON.stringify(options.body);
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
      if (!response.ok) throw new ApiError('http', response.status, outcome);
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
