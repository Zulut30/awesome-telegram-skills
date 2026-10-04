import {TelegramNativeAPI, UnsupportedTelegramCapability, TELEGRAM_NATIVE_METHODS,
  TELEGRAM_NATIVE_EVENTS, TELEGRAM_NATIVE_EVENT_DETAILS,
  type TelegramNativeMethod, type TelegramNativeEvent} from '@awesome-telegram/patterns';
import {check} from './check.js';

/** Synchronous synthetic native SDK; physical permissions/haptic не проверяются. */
export function referenceNative(): void {
  const path: TelegramNativeMethod = 'HapticFeedback.impactOccurred';
  const event: TelegramNativeEvent = 'themeChanged';
  check(Object.keys(TELEGRAM_NATIVE_METHODS).length === 99 && TELEGRAM_NATIVE_EVENTS.length === 44);
  check(TELEGRAM_NATIVE_METHODS[path].minVersion && TELEGRAM_NATIVE_EVENT_DETAILS[event].url.startsWith('https://'));
  let impacts = 0, received = 0;
  const handlers = new Map<string, (...args: unknown[]) => void>();
  const feedback = {impactOccurred(this: unknown, style: unknown) { check(this === feedback && style === 'light'); impacts++; }};
  const app = {platform: 'tdesktop', version: '10.3', HapticFeedback: feedback,
    onEvent: (name: string, listener: (...args: unknown[]) => void) => { handlers.set(name, listener); },
    offEvent: (name: string, listener: (...args: unknown[]) => void) => { if (handlers.get(name) === listener) handlers.delete(name); }};
  const native = new TelegramNativeAPI(app); check(native.supports(path)); native.call(path, 'light');
  const unsubscribe = native.listen(event, () => { received++; });
  const late = handlers.get(event); check(late); late(); check(received === 1);
  unsubscribe(); late(); check(received === 1 && handlers.size === 0);
  native.dispose(); check(!native.supports(path) && impacts === 1);
  try { native.call(path, 'light'); }
  catch (error) { check(error instanceof UnsupportedTelegramCapability); return; }
  throw Error('Disposed native adapter accepted a call');
  // `.supports` не проверяет launch/consent/ACL; host выбирает реальные аргументы.
}
