# TypeScript Mini App — 0.17.0

[Индекс всех символов](api-reference.md). Образцы ниже воспроизводятся через установленный wheel/tarball вне исходного дерева. Assert — проверка fixture, не бизнес-правило production приложения.

Установите предоставленный local tarball в отдельный consumer, сохраните файлы в src/, добавьте ESM package.json и compile с strict, ES2022, NodeNext и DOM libs. Bridge требует настоящий Document; выполняйте exports в браузере, остальные fixtures также могут исполняться в Node с Response. Общий check.ts:

```typescript
/** Fixture assertions; this helper does not belong to the library API. */
export function check(value: unknown, message = 'Reference fixture failed'): asserts value {
  if (!value) throw new Error(message);
}
```

## Entry — run.ts

Сохраните рядом с check.ts и пятью файлами раздела. После strict compile импортируйте runReference из dist/run.js в browser ESM entry и вызовите `await runReference(document)`. Bundler текущего проекта разрешает package import; plain browser требует import map к установленному dist/index.js и link к styles.css. Созданные fixture DOM и listeners удаляются; production UI/state предоставляет host.

```typescript
import {referenceBridge} from './bridge.js';
import {referenceClient} from './client.js';
import {referenceDraft} from './draft.js';
import {referenceNative} from './native.js';
import {referenceErrors} from './errors.js';

export async function runReference(document: Document): Promise<string[]> {
  referenceBridge(document); await referenceClient(); referenceDraft(); referenceNative(); referenceErrors();
  return ['bridge', 'client', 'draft', 'native', 'errors'];
}
```

<a id="ref-bridge"></a>

## Theme bridge, shell и поле ввода — ref.bridge

Файл: `bridge.ts`. Символы: `TelegramBridge`, `TelegramWebApp`, `Insets`, `BridgeSnapshot`, `createAppShell`, `AppShell`, `createTextField`, `TextFieldControl`

Границы: ESM + DOM + явно подключенный styles.css. Native объект synthetic; snapshot не auth. Host разрешает coordinates insets и владеет состоянием/navigation/focus. Shell/field используют textContent; dispose удаляет только own UI/subscriptions. Viewport не physical Telegram QA.

```typescript
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
```

<a id="ref-client"></a>

## HTTP client с decoder и unknown write — ref.client

Файл: `client.ts`. Символы: `ApiClient`, `ApiError`, `FailureKind`, `ClientOptions`, `RequestOptions`, `FetchTransport`

Границы: Response/fetch synthetic, реального backend нет. Trusted baseUrl и same-origin paths; runtime decode обязательно. Headers/session/CSRF/ACL/idempotency у host. Один invocation транспорта не исключает wire replay браузером. Unknown POST сверяется с тем же ключом без автоматического retry.

```typescript
import {ApiClient, ApiError, safeErrorReport, type ClientOptions, type RequestOptions,
  type FailureKind, type FetchTransport} from '@awesome-telegram/patterns';
import {check} from './check.js';

/** Local Response fixture; never calls global fetch or an actual backend. */
export async function referenceClient(): Promise<void> {
  let calls = 0;
  const transport: FetchTransport = async () => { calls++; return Response.json({count: 1}); };
  const options: ClientOptions = {baseUrl: 'https://fixture.invalid', fetch: transport, headers: () => ({'X-Example': 'fixture'})};
  const request: RequestOptions = {method: 'GET', timeoutMs: 1000};
  const client = new ApiClient(options);
  const value = await client.request('/count', (body: unknown) => {
    if (typeof body !== 'object' || body === null || !('count' in body) || typeof body.count !== 'number') throw Error('Bad fixture schema');
    return body.count;
  }, request);
  check(value === 1 && calls === 1);
  let writes = 0;
  const unknown = new ApiClient({...options, fetch: async () => { writes++; throw Error('PRIVATE_FIXTURE'); }});
  try { await unknown.request('/orders', body => body, {method: 'POST', body: {product: 'public-id'}}); }
  catch (error) {
    check(error instanceof ApiError);
    const kind: FailureKind = error.kind;
    check(kind === 'network' && error.outcome === 'unknown' && safeErrorReport(error, 'write').recovery === 'reconcile');
    check(writes === 1); return;
  }
  throw Error('Unknown write outcome was not surfaced');
  // Headers/session/ACL/idempotency/сверку операции реализует backend приложения.
}
```

<a id="ref-draft"></a>

## Выбор с TTL и storage fallback — ref.draft

Файл: `draft.ts`. Символы: `SelectionDraftStore`, `SelectionDraft`, `DraftRead`, `DraftOptions`, `KeyValueStorage`, `StorageFactory`

Границы: Только serviceId/slotId, без auth/contacts/price/pending operation. Account scope должен поступать от server host; fixture scope не авторизация. Store не меняет scope автоматически при account switch. Storage sync; async CloudStorage требует другого adapter, failure дает unavailable/false.

```typescript
import {SelectionDraftStore, type SelectionDraft, type DraftRead, type DraftOptions,
  type KeyValueStorage, type StorageFactory} from '@awesome-telegram/patterns';
import {check} from './check.js';

/** Только ID выбора; scope — заранее выбранная public fixture, без контактов. */
export function referenceDraft(): void {
  const values = new Map<string, string>(); let now = 1000;
  const storage: KeyValueStorage = {getItem: key => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); }, removeItem: key => { values.delete(key); }};
  const factory: StorageFactory = () => storage;
  const options: DraftOptions = {namespace: 'reference', scope: 'fixture-actor:42', ttlMs: 10, now: () => now};
  const store = new SelectionDraftStore(factory, options);
  const draft: SelectionDraft = {serviceId: 'public-id', slotId: null};
  check(store.read().status === 'missing'); check(store.write(draft));
  const result: DraftRead = store.read(); check(result.status === 'restored' && result.value.serviceId === 'public-id');
  now = 1011; check(store.read().status === 'expired' && !values.has(store.key));
  storage.setItem(store.key, 'invalid-json'); check(store.read().status === 'corrupt');
  check(store.clear());
  const unavailable = new SelectionDraftStore(() => { throw Error('Storage blocked'); }, options);
  check(unavailable.read().status === 'unavailable' && !unavailable.write(draft) && !unavailable.clear());
  // Настоящий account scope получает host; server pending identity хранится отдельно.
}
```

<a id="ref-native"></a>

## Native availability и listener cleanup — ref.native

Файл: `native.ts`. Символы: `TelegramNativeAPI`, `UnsupportedTelegramCapability`, `TELEGRAM_NATIVE_METHODS`, `TELEGRAM_NATIVE_EVENTS`, `TELEGRAM_NATIVE_EVENT_DETAILS`, `TelegramNativeMethod`, `TelegramNativeEvent`

Границы: Каталоги и facade не являются полной parameter schema. Presence/platform/version не consent, launch, auth или успешный платеж. Callback и receiver сохраняются; host выбирает arguments/permissions. Listener/dispose подавляют late callbacks, native cleanup failure может требовать повторного dispose.

```typescript
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
```

<a id="ref-errors"></a>

## Safe errors и typed recovery — ref.errors

Файл: `errors.ts`. Символы: `PatternError`, `ValidationFailure`, `InvalidType`, `AuthenticationRequired`, `PermissionDenied`, `UnsupportedCapability`, `UnknownOutcome`, `safeErrorReport`, `ErrorReport`, `ErrorCategory`, `ErrorCode`, `ErrorOutcome`, `OperationKind`, `RecoveryAction`

Границы: Developer messages не сериализуются в safe report. Operation kind отражает реальное действие; unknown write требует reconcile, classification не отменяет effect. InvalidType сохраняет TypeError catch, а не наследование PatternError. Type aliases не валидируют произвольный JSON автоматически.

```typescript
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
```
