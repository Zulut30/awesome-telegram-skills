import {TelegramBridge, createAppShell, createTextField,
  type TelegramWebApp, type Insets, type BridgeSnapshot, type AppShell,
  type TextFieldControl} from '@awesome-telegram/patterns';
import {check} from './check.js';

/** Synthetic WebApp + real DOM; geometry/color updates keep the same input. */
export function referenceBridge(document: Document): void {
  const host = document.createElement('div'); document.body.append(host);
  const listeners = new Map<string, Set<() => void>>();
  let scheme = 'light', ready = 0;
  const insets: Insets = {top: 0, right: 0, bottom: 16, left: 0};
  const app: TelegramWebApp = {platform: 'tdesktop', get colorScheme() { return scheme; },
    get themeParams() { return scheme === 'dark'
      ? {bg_color: '#101d27', text_color: '#edf4ff', secondary_bg_color: '#243246'}
      : {bg_color: '#ffffff', text_color: '#172f45', secondary_bg_color: '#f1f5fa'}; }, viewportStableHeight: 600,
    safeAreaInset: insets, contentSafeAreaInset: insets,
    ready: () => { ready++; },
    onEvent: (event, listener) => { const set = listeners.get(event) ?? new Set(); set.add(listener); listeners.set(event, set); },
    offEvent: (event, listener) => { listeners.get(event)?.delete(listener); }};
  const lifecycle = new EventTarget();
  const bridge = new TelegramBridge(app, lifecycle);
  const shell: AppShell = createAppShell(host, 'Публичный пример');
  const field: TextFieldControl = createTextField(document, 'Тема', 'Сохраняется при смене темы');
  shell.content.append(field.root); field.input.value = 'public-fixture';
  shell.summary.textContent = 'Локальный пример без auth'; shell.actions.textContent = 'Действия приложения';
  let snapshots = 0;
  const unsubscribe = bridge.subscribe((snapshot: BridgeSnapshot) => {
    snapshots++; shell.applyTheme(snapshot);
    // Одинаковые fixture coordinates: выбираем contentInsets явно, не суммируем.
    shell.setInsets(snapshot.contentInsets ?? {top: 0, right: 0, bottom: 0, left: 0});
  });
  bridge.start(); bridge.start(); check(ready === 1);
  const first: BridgeSnapshot = bridge.snapshot(); check(first.insideTelegram && first.stableHeight === 600);
  scheme = 'dark'; for (const listener of listeners.get('themeChanged') ?? []) listener();
  check(bridge.snapshot().colorScheme === 'dark' && field.input.value === 'public-fixture');
  check(field.root.querySelector('label')?.control === field.input);
  field.setError('Проверьте значение'); check(field.input.getAttribute('aria-invalid') === 'true');
  field.setError(null); check(field.input.getAttribute('aria-invalid') !== 'true');
  lifecycle.dispatchEvent(new Event('pagehide')); lifecycle.dispatchEvent(new Event('pageshow'));
  check(snapshots >= 3);
  unsubscribe(); bridge.dispose(); shell.dispose();
  check(host.children.length === 0 && [...listeners.values()].every(set => set.size === 0)); host.remove();
  // Snapshot/native presence не являются серверной аутентификацией.
}
