# TypeScript Mini App — 0.27.0

Термины: **CAS** — сравнение с заменой: запись сохраняется, только если версия не изменилась с момента чтения; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей; **fallback** — запасной вариант, если основная возможность недоступна.

[Индекс всех символов](api-reference.md). Образцы ниже воспроизводятся через установленный wheel/tarball вне исходного дерева. Assert — проверка fixture, не бизнес-правило production приложения.

Установите предоставленный local tarball в отдельный consumer, сохраните файлы в src/, добавьте ESM package.json и compile с strict, ES2022, NodeNext и DOM libs. Bridge требует настоящий Document; выполняйте exports в браузере, остальные fixtures также могут исполняться в Node с Response. Общий check.ts:

```typescript
/** Fixture assertions; this helper does not belong to the library API. */
export function check(value: unknown, message = 'Reference fixture failed'): asserts value {
  if (!value) throw new Error(message);
}
```

## Entry — run.ts

Сохраните рядом с check.ts и файлами раздела. После strict compile импортируйте runReference из dist/run.js в browser ESM entry и вызовите `await runReference(document)`. Bundler текущего проекта разрешает package import; plain browser требует import map к установленному dist/index.js и link к styles.css и tokens.css. Созданные fixture DOM и listeners удаляются; production UI/state предоставляет host.

```typescript
import {referenceBridge} from './bridge.js';
import {referenceClient} from './client.js';
import {referenceDraft} from './draft.js';
import {referenceNative} from './native.js';
import {referenceErrors} from './errors.js';
import {referenceInitData} from './init-data.js';
import {referenceState} from './state.js';
import {referenceUi} from './ui.js';
import {referenceFlows} from './flows.js';

export async function runReference(document: Document): Promise<string[]> {
  referenceBridge(document); await referenceClient(); referenceDraft(); referenceNative(); referenceErrors();
  await referenceInitData();
  await referenceState();
  await referenceUi(document);
  await referenceFlows(document);
  return ['bridge', 'client', 'draft', 'native', 'errors', 'init_data', 'state', 'ui', 'flows'];
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

Файл: `native.ts`. Символы: `TelegramNativeAPI`, `UnsupportedTelegramCapability`, `TELEGRAM_NATIVE_METHODS`, `TELEGRAM_NATIVE_EVENTS`, `TELEGRAM_NATIVE_EVENT_DETAILS`, `TelegramNativeMethod`, `TelegramNativeEvent`, `TelegramNativeSignatures`, `TelegramNativeArguments`, `TelegramNativeResult`

Границы: Типы аргументов и результатов каждого пути сгенерированы из официальных сигнатур и документации (scripts/build_native_signatures.py): неверный аргумент ловит tsc, runtime значения не проверяет. Presence/platform/version не consent, launch, auth или успешный платеж. Callback и receiver сохраняются; host выбирает arguments/permissions. Listener/dispose подавляют late callbacks, native cleanup failure может требовать повторного dispose. Serverless.call индексируется с minVersion null: универсальный фасад отказывает до SDK. Для выбранного хостинга используется отдельный ServerlessEndpointClient с явным включением и проверкой наличия.

```typescript
import {TelegramNativeAPI, UnsupportedTelegramCapability, TELEGRAM_NATIVE_METHODS,
  TELEGRAM_NATIVE_EVENTS, TELEGRAM_NATIVE_EVENT_DETAILS,
  type TelegramNativeMethod, type TelegramNativeEvent, type TelegramNativeSignatures,
  type TelegramNativeArguments, type TelegramNativeResult} from '@awesome-telegram/patterns';
import {check} from './check.js';

/** Synchronous synthetic native SDK; physical permissions/haptic не проверяются. */
export function referenceNative(): void {
  const path: TelegramNativeMethod = 'HapticFeedback.impactOccurred';
  const event: TelegramNativeEvent = 'themeChanged';
  check(Object.keys(TELEGRAM_NATIVE_METHODS).length === 100 && TELEGRAM_NATIVE_EVENTS.length === 44);
  check(TELEGRAM_NATIVE_METHODS['Serverless.call'].minVersion === null);
  check(TELEGRAM_NATIVE_METHODS[path].minVersion && TELEGRAM_NATIVE_EVENT_DETAILS[event].url.startsWith('https://'));
  let impacts = 0, received = 0;
  const handlers = new Map<string, (...args: unknown[]) => void>();
  const feedback = {impactOccurred(this: unknown, style: unknown) { check(this === feedback && style === 'light'); impacts++; return feedback; }};
  const app = {platform: 'tdesktop', version: '10.3', HapticFeedback: feedback,
    onEvent: (name: string, listener: (...args: unknown[]) => void) => { handlers.set(name, listener); },
    offEvent: (name: string, listener: (...args: unknown[]) => void) => { if (handlers.get(name) === listener) handlers.delete(name); }};
  const native = new TelegramNativeAPI(app); check(native.supports(path));
  // Arguments and results are typed per path: 'loud' or a missing style fail at tsc, not in the client.
  const style: TelegramNativeArguments<'HapticFeedback.impactOccurred'>[0] = 'light';
  const chained: TelegramNativeResult<'HapticFeedback.impactOccurred'> = native.call('HapticFeedback.impactOccurred', style);
  const documented: keyof TelegramNativeSignatures = path; check(chained === feedback && documented === path);
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

<a id="ref-init_data"></a>

## Проверка initData без токена бота — ref.init_data

Файл: `init-data.ts`. Символы: `verifyInitDataSignature`, `InvalidInitData`, `TELEGRAM_PUBLIC_KEYS`, `SignedLaunch`, `SignedObject`, `InitDataSignatureOptions`

Границы: Для сервера или третьей стороны, которой известен только bot_id: подпись Ed25519 проверяется через WebCrypto (браузеры, Node 20+), без зависимостей. Нет WebCrypto или Ed25519 — UnsupportedCapability, а не успех. Результат подтверждает данные запуска, но не сессию, права на объект и однократность операции. Проверка HMAC с токеном бота остается в Python.

```typescript
import {InvalidInitData, TELEGRAM_PUBLIC_KEYS, verifyInitDataSignature,
  type InitDataSignatureOptions, type SignedLaunch, type SignedObject} from '@awesome-telegram/patterns';
import {check} from './check.js';

// Независимый вектор из тестов aiogram: их собственная пара ключей и бот 42, не ключ Telegram.
const SIGNED = 'auth_date=1650385342&user=%7B%22id%22%3A42%2C%22first_name%22%3A%22Test%22%7D&query_id=test'
  + '&signature=JQ0JR2tjC65yq_jNZV0wuJVX6J-SWPMV0mprUXG34g-NvxL4RcF1Rz5n4VVo00VRghEUBf5t___uoeb1-jU_Cw';
const FIXTURE_KEY = '4112765021341e5415e772cd65903f6b94e3ea1c2ab669e6d3e18ee2db00da61';

export async function referenceInitData(): Promise<void> {
  const publicKey = Uint8Array.from(FIXTURE_KEY.match(/../g) ?? [], (pair) => Number.parseInt(pair, 16));
  const options: InitDataSignatureOptions = {publicKey, now: 1650385342};
  const launch: SignedLaunch = await verifyInitDataSignature(SIGNED, 42, options);
  const user: SignedObject = launch.user;
  check(launch.userId === 42 && user['first_name'] === 'Test' && launch.queryId === 'test');
  const otherBot = await verifyInitDataSignature(SIGNED, 43, options).then(() => null, (error: unknown) => error);
  check(otherBot instanceof InvalidInitData);
  check(TELEGRAM_PUBLIC_KEYS.production.length === 64); // настоящая initData: {environment: 'production'} без publicKey
  // Сессию, права на объект и защиту от повтора проверяет backend; токен бота здесь не нужен.
}
```

<a id="ref-client_state"></a>

## Account scope, гонки чтений и незавершенная операция — ref.client_state

Файл: `state.ts`. Символы: `ScopedAsyncState`, `AsyncReadSnapshot`, `AsyncReadResult`, `AsyncReadContext`, `AsyncStateOptions`, `PendingOperationStore`, `PendingOperation`, `PendingOperationRead`, `PendingOperationReservation`, `PendingOperationOptions`

Границы: Framework-neutral state без fetch/retry/auth/token. Scope задает backend-validated host; смена аккаунта/dispose очищает кеш и инвалидирует ответы, даже если transport игнорирует abort. DTO только bounded plain JSON, detached/deep-frozen. PendingOperationStore хранит только scoped UUID/createdAt/pending-or-unknown отдельно от draft; corrupt/unavailable/unsupported блокирует dispatch. Только authoritative server result разрешает complete. localStorage single-owner, не межвкладочный CAS или серверная идемпотентность.

```typescript
import {ScopedAsyncState, PendingOperationStore, type AsyncStateOptions, type AsyncReadContext,
  type AsyncReadResult, type AsyncReadSnapshot, type PendingOperationOptions, type PendingOperation,
  type PendingOperationRead, type PendingOperationReservation} from '@awesome-telegram/patterns';
import {check} from './check.js';

export async function referenceState(): Promise<void> {
  const options: AsyncStateOptions={maxEntries:2};
  const cache=new ScopedAsyncState<{label:string}>(options);
  cache.setScope('server-verified:100:42');
  let late!: (value:{label:string})=>void;
  const old=cache.read('order',()=>new Promise(resolve=>{late=resolve;}));
  const result: AsyncReadResult<{label:string}>=await cache.read('order',async(context:AsyncReadContext)=>{
    check(context.scope==='server-verified:100:42' && !context.signal.aborted);
    return {label:'current'};
  });
  check(result.status==='ready' && result.value.label==='current');
  check((await old).status==='stale');late({label:'obsolete'});
  await Promise.resolve();
  const snapshot: AsyncReadSnapshot<{label:string}>=cache.snapshot('order');
  check(snapshot.status==='ready' && snapshot.value.label==='current');
  cache.setScope('server-verified:100:77');
  check(cache.snapshot('order').status==='idle');cache.dispose();

  const values=new Map<string,string>();
  const storage=()=>({getItem:(key:string)=>values.get(key)??null,
    setItem:(key:string,value:string)=>{values.set(key,value);},removeItem:(key:string)=>{values.delete(key);}});
  const pendingOptions: PendingOperationOptions={namespace:'reference',scope:'server-verified:100:42',now:()=>1000};
  const pending=new PendingOperationStore(storage,pendingOptions);
  const id='01234567-1234-4123-8123-0123456789ab';
  const reserved: PendingOperationReservation=pending.reserve(id);
  check(reserved.status==='reserved');
  if(reserved.status!=='reserved') throw Error('Fixture reservation failed');
  const pointer: PendingOperation=reserved.value;check(pointer.operation===id);
  check(pending.markUnknown(id));
  const reopened=new PendingOperationStore(storage,pendingOptions);
  const read: PendingOperationRead=reopened.read();
  check(read.status==='restored' && read.value.state==='unknown');
  const reused=reopened.reserve('11234567-1234-4123-8123-0123456789ab');
  check(reused.status==='existing' && reused.value.operation===id);
  // Host first verifies this exact server operation. Completing a draft or closing invoice is insufficient.
  check(reopened.complete(id) && reopened.read().status==='missing');
}
```

<a id="ref-ui_controls"></a>

## Компоненты интерфейса и принадлежащий им жизненный цикл — ref.ui_controls

Файл: `ui.ts`. Символы: `createUiButton`, `createUiField`, `validateUiFields`, `uiUrl`, `createUiLink`, `createUiBadge`, `createUiCard`, `createUiList`, `createUiSkeleton`, `createUiFeedback`, `createUiTabs`, `createUiDialog`, `connectUiShell`, `bindUiFocusVisibility`, `UiControl`, `UiTone`, `UiButtonOptions`, `UiButton`, `UiFieldOptions`, `UiField`, `UiListItem`, `UiFeedbackOptions`, `UiTab`, `UiTabs`, `UiDialog`, `UiShellOptions`

Границы: Компоненты создаются в переданном Document, используют буквальный текст и не дают серверных прав. Host владеет операцией, ответами backend, настоящими разрешениями Telegram и исходом платежа. Отмена или dispose после начала действия не отменяют удаленный эффект. Нативный dialog требует поддержки браузером; темы сохраняют ввод, отступы разрешаются host один раз. Подключите styles.css и tokens.css из того же пакета. Проверки Chrome/axe не доказывают работу системной клавиатуры, screen reader, физических устройств или полное соответствие WCAG.

```typescript
import {createAppShell, TelegramBridge, createUiButton, createUiField, validateUiFields,
  uiUrl, createUiLink, createUiBadge, createUiCard, createUiList, createUiSkeleton,
  createUiFeedback, createUiTabs, createUiDialog, connectUiShell, bindUiFocusVisibility,
  type UiControl, type UiTone, type UiButtonOptions, type UiButton, type UiFieldOptions,
  type UiField, type UiListItem, type UiFeedbackOptions, type UiTab, type UiTabs,
  type UiDialog, type UiShellOptions, type TelegramWebApp} from '@awesome-telegram/patterns';
import {check} from './check.js';

/** Installed-package DOM contract. No network, authenticated identity, payment or device claim. */
export async function referenceUi(document: Document): Promise<void> {
  const host=document.createElement('div');document.body.append(host);
  const shell=createAppShell(host,'UI consumer fixture');
  const events=new Map<string,Set<()=>void>>();let scheme='light';
  const app:TelegramWebApp={platform:'tdesktop',get colorScheme(){return scheme;},
    get themeParams(){return scheme==='dark'?{bg_color:'#101d27',text_color:'#edf4ff'}:{bg_color:'#ffffff',text_color:'#172f45'};},
    contentSafeAreaInset:{top:0,right:0,bottom:12,left:0},ready(){},
    onEvent(name,listener){const set=events.get(name)??new Set();set.add(listener);events.set(name,set);},
    offEvent(name,listener){events.get(name)?.delete(listener);}};
  const bridge=new TelegramBridge(app,new EventTarget());
  const options:UiShellOptions={resolveInsets:snapshot=>snapshot.contentInsets};
  const disconnect=connectUiShell(shell,bridge,options),focusCleanup=bindUiFocusVisibility(shell.element);
  bridge.start();
  const fieldOptions:UiFieldOptions={label:'Ваше имя',value:'Сохранённый ввод',required:true,inputMode:'text'};
  const field:UiField=createUiField(document,fieldOptions);shell.content.append(field.root);
  field.input.focus();field.input.setSelectionRange(2,4);field.setError('Ошибка сервера');
  check(field.input.value==='Сохранённый ввод'&&field.input.selectionStart===2);
  check(validateUiFields([field])&&field.input.getAttribute('aria-invalid')==='false');
  scheme='dark';for(const listener of events.get('themeChanged')??[])listener();
  check(shell.element.dataset.theme==='dark'&&field.input.value==='Сохранённый ввод');
  let presses=0;const buttonOptions:UiButtonOptions={label:'Продолжить',variant:'primary',onPress:async()=>{presses++;}};
  const button:UiButton=createUiButton(document,buttonOptions);shell.actions.append(button.element);
  button.setPending(true);button.element.click();check(presses===0);button.setPending(false);
  button.setDisabled(true);check(button.element.disabled);button.setDisabled(false);button.element.click();
  await new Promise<void>(resolve=>setTimeout(resolve,0));check(Number(presses)===1);
  const tone:UiTone='success';const card=createUiCard(document,'Карточка','<script>literal</script>');
  card.append(createUiBadge(document,'Подтверждённый локальный результат',tone));
  const rows:readonly UiListItem[]=[{title:'Сведения',detail:'Без персонального payload',badge:'Обзор'}];
  card.append(createUiList(document,rows,'Список'),createUiSkeleton(document,2));
  const safe=uiUrl('https://example.org/help',document.baseURI);card.append(createUiLink(document,'Справка',safe));
  let rejected=false;try{uiUrl('javascript:alert(1)',document.baseURI);}catch{rejected=true;}check(rejected);
  const feedbackOptions:UiFeedbackOptions={kind:'success',title:'Готово',message:'Это UI fixture, не оплата.'};
  const feedback:UiControl=createUiFeedback(document,feedbackOptions);card.append(feedback.element);
  const other=document.createElement('section');other.textContent='Второй раздел';
  const panels:readonly UiTab[]=[{id:'first',label:'Первый',content:card},{id:'second',label:'Второй',content:other}];
  const tabs:UiTabs=createUiTabs(document,'Разделы',panels);shell.content.append(tabs.element);tabs.select('second');
  check(tabs.selected==='second'&&card.hidden&&!other.hidden);
  const dialog:UiDialog=createUiDialog(document,'Подтверждение','sheet');shell.element.append(dialog.element);
  dialog.content.append(document.createTextNode('Без сетевого запроса'));button.element.focus();dialog.open(button.element);
  check(dialog.element.open&&dialog.element.contains(document.activeElement));dialog.close();
  check(!dialog.element.open&&document.activeElement===button.element);
  dialog.dispose();tabs.dispose();feedback.dispose();field.dispose();button.dispose();focusCleanup();disconnect();bridge.dispose();shell.dispose();
  check(host.children.length===0&&[...events.values()].every(set=>set.size===0));host.remove();
}
```

<a id="ref-native_flows"></a>

## Нативные сценарии и время владения — ref.native_flows

Файл: `flows.ts`. Символы: `NativeFlowScope`, `NativeActionButtons`, `NativePrompts`, `NativeAccountStorage`, `NativeSharing`, `createNativeFileInput`, `ServerlessEndpointClient`, `NativeFlowResult`, `NativeLaunch`, `NativeInteraction`, `NativeFlowKind`, `NativeScopeOptions`, `NativeCapability`, `NativeButtonsState`, `NativeButtonHandlers`, `NativeStorageKind`, `NativeStoredValue`, `NativeFileInputOptions`, `TelegramServerlessError`, `TelegramServerlessBridge`, `ServerlessCallOptions`

Границы: Наличие функции, версия SDK и политика платформы проверяются отдельно от разрешения пользователя. Host владеет серверными правами и состоянием внешней операции; закрытый invoice не подтверждает оплату. Смена аккаунта и dispose подавляют старые ответы, но не отменяют удаленный эффект. У ответа записи и удаления обязательно проверяйте stored/removed. Serverless включается явно только при присутствии платформенного объекта; минимальная версия не выдумывается, неизвестная запись сверяется по сохраненному ID. Браузер не доказывает доступность на реальном устройстве.

```typescript
import {NativeFlowScope,NativeActionButtons,NativePrompts,NativeAccountStorage,NativeSharing,createNativeFileInput,ServerlessEndpointClient,
  type NativeFlowResult,type NativeLaunch,type NativeInteraction,type NativeFlowKind,type NativeScopeOptions,type NativeCapability,
  type NativeButtonsState,type NativeButtonHandlers,type NativeStorageKind,type NativeStoredValue,type NativeFileInputOptions,
  type TelegramServerlessError,type TelegramServerlessBridge,type ServerlessCallOptions} from '@awesome-telegram/patterns';
import {check} from './check.js';

/** Installed-package fake callbacks + real DOM, not Telegram/backend authentication. */
export async function referenceFlows(document:Document):Promise<void>{
  const host=document.createElement('section');document.body.append(host);
  const listeners=new Map<string,Set<()=>void>>(),records=new Map<string,string>();
  const replies:{popup?:(id:string|null)=>void;share?:(sent:boolean)=>void}={};let presses=0,visible=false;
  const endpointError:TelegramServerlessError={message:'PRIVATE_SERVERLESS_MESSAGE',type:'ENDPOINT_ERROR',status:0,parameters:{secret:'PRIVATE_PARAMETERS'}};
  const raw:TelegramServerlessBridge={call(_name:string,input?:Readonly<Record<string,unknown>>|((error:TelegramServerlessError|null,result?:unknown)=>void),callback?:(error:TelegramServerlessError|null,result?:unknown)=>void){const reply=typeof input==='function'?input:callback;reply?.(endpointError,null);}};
  const app={platform:'tdesktop',version:'9.6',initData:'PRIVATE_INITDATA_CANARY',Serverless:raw,isVersionAtLeast:()=>true,
    onEvent(name:string,callback:()=>void){const set=listeners.get(name)??new Set();set.add(callback);listeners.set(name,set);},
    offEvent(name:string,callback:()=>void){listeners.get(name)?.delete(callback);},
    MainButton:{setText(){return {};},show(){visible=true;return {};},hide(){visible=false;return {};},enable(){return {};},disable(){return {};},showProgress(){return {};},hideProgress(){return {};},onClick(){return {};},offClick(){return {};}},
    showPopup(_params:unknown,callback?:(id:string|null)=>void){if(callback)replies.popup=callback;},
    shareMessage(_id:string,callback?:(sent:boolean)=>void){if(callback)replies.share=callback;},
    DeviceStorage:{getItem(key:string,callback:(error:string|null,value?:string|null)=>void){callback(null,records.get(key)??null);return {};},setItem(key:string,value:string,callback?:(error:string|null,stored?:boolean)=>void){records.set(key,value);callback?.(null,true);return {};},removeItem(key:string,callback?:(error:string|null,removed?:boolean)=>void){records.delete(key);callback?.(null,true);return {};}},
  };
  const launch:NativeLaunch='direct',options:NativeScopeOptions={accountTag:'bot100_account42',launch,timeoutMs:5};
  const scope=new NativeFlowScope(app,options),flow:NativeFlowKind='popup';
  const capability:NativeCapability|undefined=scope.capabilities().find(value=>value.flow===flow);check(capability?.available&&capability.launch===launch);
  const handlers:NativeButtonHandlers={main:async()=>{presses++;}};const buttons=new NativeActionButtons(scope,handlers);
  const state:NativeButtonsState={main:{text:'Продолжить',visible:true}};buttons.render(state);check(visible);
  for(const listener of listeners.get('mainButtonClicked')??[])listener();await new Promise<void>(resolve=>setTimeout(resolve,0));check(presses===1);
  const prompts=new NativePrompts(scope);const popup:Promise<NativeFlowResult<{buttonId:string}>>=prompts.popup({message:'Продолжить?',buttons:[{id:'ok',type:'ok'}]});
  check((await prompts.popup({message:'Duplicate'})).status==='busy');check(replies.popup);const late=replies.popup;late(null);check((await popup).status==='cancelled');late('old');
  const storage=new NativeAccountStorage(scope),kind:NativeStorageKind='device';check((await storage.write(kind,'draft','account42')).status==='completed');
  buttons.dispose();scope.setAccount('bot100_account77');const read=await storage.read(kind,'draft');check(read.status==='completed');
  const stored:NativeStoredValue=read.value;check(stored.value===null&&records.get('tp_16_bot100_account42_draft')==='account42');
  const action:NativeInteraction={purpose:'Поделиться результатом текущего шага',userInitiated:true};const sharing=new NativeSharing(scope);
  const share=await sharing.message('server-prepared-id',action);check(share.status==='unknown'&&share.error.recovery==='reconcile');replies.share?.(false);
  check(sharing.story('https://example.org/approved.jpg',undefined,action).status==='unsupported');
  let selected=-1;const fileOptions:NativeFileInputOptions={label:'Файл без OS dialog',accept:['image/*'],capture:'environment',maxBytes:1024,onFiles:files=>{selected=files.length;}};
  const picker=createNativeFileInput(document,fileOptions);host.append(picker.element);picker.input.dispatchEvent(new Event('change'));check(selected===0&&picker.input.type==='file');
  const disabled=new ServerlessEndpointClient(app,{serverlessHosting:false});check((await disabled.call('getProfile',{},value=>value)).status==='unsupported');
  const serverless=new ServerlessEndpointClient(app,{serverlessHosting:true});const callOptions:ServerlessCallOptions={operation:'write'};
  const response=await serverless.call('place_order',{operation_id:'fixture-stable-operation'},value=>value,callOptions);
  check(response.status==='unknown'&&response.error.recovery==='reconcile'&&!JSON.stringify(response).includes('PRIVATE'));
  serverless.dispose();disabled.dispose();picker.dispose();scope.dispose();check(host.children.length===0&&[...listeners.values()].every(set=>set.size===0));host.remove();
}
```
