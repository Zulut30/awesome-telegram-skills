/** Native calls keep their documented callbacks/return values; no implicit auth or retry. */
import { TELEGRAM_NATIVE_EVENTS, TELEGRAM_NATIVE_EVENT_DETAILS, TELEGRAM_NATIVE_METHODS, type TelegramNativeEvent, type TelegramNativeMethod } from './native-catalog.js';

type ObjectLike = Record<string, unknown>;
type Listener = (...args: unknown[]) => void;
const object = (value: unknown): value is ObjectLike => value !== null && typeof value === 'object';

export class UnsupportedTelegramCapability extends Error {
  constructor() { super('Telegram capability unavailable in the current client or disposed adapter'); this.name = 'UnsupportedTelegramCapability'; }
}

export class TelegramNativeAPI {
  private disposed = false;
  private readonly cleanups = new Set<() => void>();
  constructor(private readonly app: unknown) {}

  private atLeast(required: string): boolean {
    if (!object(this.app) || typeof this.app.version !== 'string' || !/^\d+\.\d+$/.test(this.app.version)) return false;
    const [major = 0, minor = 0] = this.app.version.split('.').map(Number);
    const [requiredMajor = 0, requiredMinor = 0] = required.split('.').map(Number);
    if (major < requiredMajor || (major === requiredMajor && minor < requiredMinor)) return false;
    return typeof this.app.isVersionAtLeast !== 'function' || this.app.isVersionAtLeast(required) === true;
  }

  private resolve(path: TelegramNativeMethod): { owner: ObjectLike; fn: (...args: unknown[]) => unknown } | undefined {
    if (this.disposed || !Object.hasOwn(TELEGRAM_NATIVE_METHODS, path) || !object(this.app)) return;
    if (typeof this.app.platform !== 'string' || !this.app.platform || this.app.platform === 'unknown') return;
    if (!this.atLeast(TELEGRAM_NATIVE_METHODS[path].minVersion)) return;
    const parts = path.split('.');
    let owner: ObjectLike = this.app;
    for (const part of parts.slice(0, -1)) {
      const next = owner[part];
      if (!object(next)) return;
      owner = next;
    }
    const last = parts.at(-1);
    if (!last) return;
    const fn = owner[last];
    if (typeof fn !== 'function') return;
    return { owner, fn: fn as (...args: unknown[]) => unknown };
  }

  /** Availability is separate from permission, signed identity and successful completion. */
  supports(path: TelegramNativeMethod): boolean {
    try { return this.resolve(path) !== undefined; } catch { return false; }
  }

  call(path: TelegramNativeMethod, ...args: unknown[]): unknown {
    const method = this.resolve(path);
    if (!method) throw new UnsupportedTelegramCapability();
    return method.fn.apply(method.owner, args);
  }

  /** Each registration gets its own callback, even when consumers reuse a function. */
  listen(event: TelegramNativeEvent, listener: Listener): () => void {
    if (!(TELEGRAM_NATIVE_EVENTS as readonly string[]).includes(event) || typeof listener !== 'function') throw new TypeError('Use a documented Telegram event and a callable listener');
    const on = this.resolve('onEvent'), off = this.resolve('offEvent');
    if (!on || !off || !this.atLeast(TELEGRAM_NATIVE_EVENT_DETAILS[event].minVersion)) throw new UnsupportedTelegramCapability();
    let active = true, removed = false;
    const wrapper: Listener = (...args) => { if (active && !this.disposed) listener(...args); };
    const cleanup = () => {
      if (removed) return;
      active = false; // Suppress late callbacks even if native removal fails.
      // Retain cleanup on failure so disposal/unsubscribe can be retried.
      off.fn.call(off.owner, event, wrapper);
      removed = true;
      this.cleanups.delete(cleanup);
    };
    this.cleanups.add(cleanup);
    try { on.fn.call(on.owner, event, wrapper); }
    catch (error) { try { cleanup(); } catch { /* retained for retry */ } throw error; }
    return cleanup;
  }

  /** Stops new work immediately. Failed SDK cleanup remains retryable via dispose(). */
  dispose(): void {
    this.disposed = true;
    let failed = false, failure: unknown;
    for (const cleanup of [...this.cleanups]) {
      try { cleanup(); } catch (error) { if (!failed) failure = error; failed = true; }
    }
    if (failed) throw failure;
  }
}
