# Состояние Mini App: чтение, черновик и неизвестная операция

`ScopedAsyncState` управляет чтением и кешем в памяти, `SelectionDraftStore` — допустимыми полями черновика, `PendingOperationStore` — отдельной ссылкой на уже отправленную операцию. Эти experimental API не создают HTTP/backend, серверную личность, offline-очередь платежей или новый Telegram bridge. Существующие `ApiClient` и framework adapters сохраняются. Установка скилла не устанавливает runtime-пакет; подключение локального wheel/tarball описано в [for-agents](for-agents.md).

## Чтение без устаревших ответов

```ts
import {ScopedAsyncState, type ApiClient} from '@awesome-telegram/patterns';

type Order = {readonly id: string; readonly status: string};
const reads = new ScopedAsyncState<Order>({maxEntries: 32});

async function loadOrder(client: ApiClient, verifiedScope: string,
                         decodeOrder: (value: unknown) => Order) {
  reads.setScope(verifiedScope); // Только scope из проверенной backend session.
  const result = await reads.read('order', ({signal}) =>
    client.request('/api/order', decodeOrder, {signal}));
  if (result.status === 'ready') return result.value;
  if (result.status === 'failed') return result.error; // Без raw exception/payload.
  // stale: запрос заменен, отменен или принадлежал прежнему аккаунту; UI не обновлять.
}
```

`snapshot(key)` возвращает `idle`, `loading`, `ready` с `value` или `failed` с безопасным `ErrorReport`. Для одного key побеждает последний начатый read; разные keys независимы. Предыдущий сигнал abort срабатывает, а результат дополнительно проверяется по generation даже при transport, игнорирующем abort. Отмененный read завершается как `stale`, не ожидая такого transport; его поздний success/rejection обработан и не меняет кеш.

Snapshot и DTO отделены от loader data и глубоко frozen. В кеш допускается plain JSON: scalar/null, плотный array, plain object; accessors/classes/cycles/undefined/nonfinite numbers не принимаются. Лимит одной копии — 10000 узлов и глубина 64. Это boundary корректности/памяти, не performance benchmark. `maxEntries` — целое 1–512, default 32; при переполнении старейший key удаляется, его незавершенный read отменяется. Компонент не назначает TTL свежести серверным данным: host показывает давность там, где это влияет на решение, и явно обновляет read.

`cancel(key)` удаляет состояние одного чтения, `clear()` удаляет весь кеш и делает все старые результаты stale. `dispose()` дополнительно сбрасывает scope и запрещает новые reads/setScope; повторный dispose допустим. Store не создает DOM/Telegram listeners, timers или subscriber loop. Host отвечает за собственные подписки/навигацию. Abort не является rollback серверной записи; этот store предназначен для reads.

## Смена аккаунта и токена

При обнаружении смены аккаунта сначала очистите memory token, видимые private order/cart и вызовите `setScope(null)`. После server validation новой initData присвойте новый memory bearer и `setScope(session.scope)`. Не передавайте `initDataUnsafe.user.id` как доказательство проверки; наличие Telegram SDK само по себе не устанавливает личность.

Любое изменение scope очищает кеш/reads синхронно, включая последовательность account A → logout → снова A. Повторный `setScope` с той же строкой не очищает кеш: обычный renewal token того же пользователя не означает другой аккаунт. Результаты проверяются после каждого прикладного `await`; одного abort transport недостаточно, если read успел завершиться до смены аккаунта.

Не переносите старые draft/pending keys в новый scope. Состояние прежнего пользователя может остаться в его scoped recovery storage, но не должно отображаться/отправляться новой сессией. Scoped localStorage не авторизует запросы: backend на каждом действии проверяет bearer и владельца объекта.

## Версии и TTL черновика

Старый конструктор `SelectionDraftStore(storage, {namespace,scope,ttlMs,now?})`, schema 1 и key `tg-selection:<namespace>:<scope>:v1` сохранены. Allowlist содержит только `serviceId`/`slotId`; auth, контакты, цена, receipt и operation IDs не копируются.

Для новой schema migration задается явно:

```ts
const draft = new SelectionDraftStore(() => localStorage, {
  namespace: 'booking', scope: session.scope, ttlMs: 15 * 60_000,
  schemaVersion: 2,
  migrateFrom: {
    1: value => {
      const old = value as {serviceId: unknown; slotId: unknown};
      // Итог повторно проверяется встроенным allowlist/ID validator.
      return {serviceId: old.serviceId as string | null,
              slotId: old.slotId as string | null};
    },
  },
});
```

`migrateFrom` перечисляет только известные меньшие версии и decoder каждой старой shape. Store не сканирует неизвестные версии или чужие scope. Same-scope envelope и исходный expiry проверяются до decoder. При migration expiry равен минимуму старого срока и текущего `now+ttlMs`: чтение старых полей не продлевает их жизнь. Успешная новая запись предшествует удалению legacy. Ошибка decoder/write сохраняет legacy; возвращается `corrupt`/`unavailable`, а не фиктивное восстановление. После quota fix migration можно повторить.

`clear()` удаляет текущую и все явно известные legacy-копии этого scope, чтобы старый draft не появился вновь. Ошибка удаления возвращает false. Expired fields не восстанавливаются даже при невозможности физического удаления. Default v1 corruption policy сохранена: поврежденный текущий draft очищается. Эта политика не применяется к pending operation pointer.

## Отдельный recovery pointer

```ts
const pending = new PendingOperationStore(() => localStorage, {
  namespace: 'booking', scope: session.scope,
});
const saved = pending.reserve(crypto.randomUUID());
if (saved.status === 'blocked') {
  // Corrupt/unsupported/unavailable storage: новый dispatch запрещен.
} else if (saved.status === 'existing') {
  // Сверить saved.value.operation на сервере; не отправлять новый intent с этим ID.
} else {
  // Pointer сохранен до отправки; backend должен поддерживать этот scoped opID.
}
```

Pointer содержит только UUID v4, `createdAt` и `pending|unknown` в отдельном `tg-pending:<namespace>:<scope>:v1`. Payload, token, initData, платежное подтверждение не сохраняются. При неизвестном исходе вызовите `markUnknown(originalID)`. Повторный `reserve` возвращает прежний ID, в том числе когда caller предложил новый UUID; это сигнал сверки прежнего intent, а не разрешение отправить новый payload под старым ключом.

Draft TTL/clear не удаляет pointer и не подтверждает отмену server operation. `complete(originalID)` допускается только после подтвержденного результата backend; неверный ID не меняет запись. Ошибка storage записи/удаления возвращает false/blocked, а не успех. `read()` различает missing/restored/corrupt/unsupported/unavailable. Corrupt/unknown-schema запись сохраняется и блокирует новую операцию; автоматической очистки неизвестного исхода нет.

Pointer не обещает вечное окно server/provider dedup. Когда сервер уже не может подтвердить прежний исход, нужен продуктовый unresolved/операторский путь. Очистка браузерного storage пользователем/ОС уничтожает локальную ссылку; серверный список своих объектов или другой recovery path остается ответственностью продукта.

Это **single-owner** helper: localStorage не предоставляет межвкладочный compare-and-swap/транзакцию `read → reserve`. Две независимые вкладки могут предложить разные intent IDs; компонент не заявляет exactly-once в такой гонке. Host согласует одного dispatcher либо резервирует intent на сервере. Idempotency/ACL/immutable payload проверяет backend, а не browser store.

## Композиция магазина

Новый [domain-state.ts](../examples/shop/frontend/src/domain-state.ts) отделяет memory session/cart/order и pending pointer от UI и Telegram globals. `ShopOrderReader` внедряет transport/decoding; запрос получает captured immutable session и signal. Для существующего сгенерированного shop клиента:

```ts
const state = new ShopDomainState(() => localStorage, {
  operation: (session, operation, signal) => {
    const client = new ApiClient({baseUrl: location.origin,
      headers: () => ({Authorization: 'Bearer ' + session.token})});
    return callApi(client, 'getOperation', {params: {operation}, signal});
  },
});
state.setSession(backendSession);
```

Scope switch/logout очищает видимые cart/order и read cache до применения нового account response; повторный вход той же identity сохраняет ее pointer. `reconcile()` читает только сохраненную operation, проверяет совпадение server DTO operation и дополнительно защищает собственное await-продолжение account generation. `completeOrder` разрешен лишь для уже сверенного exact ID. Snapshot не содержит bearer. `dispose()` идемпотентен и стирает memory identity/state.

Текущий `main.ts` магазина не подключен к этому headless примеру и не переписан. Автоматический renewal, native/browser history/closing flow и внедрение новой state composition во все экраны остаются отдельной интеграцией; наличие класса не закрывает целиком 46–50. Серверная session rotation/revoke и реальная локальная aiohttp/SQLite приемка описаны отдельно в [shop backend contract](internal/shop-backend-production-contract.md).

## Проверка

`npm test -w @awesome-telegram/patterns` собирает пакет, выполняет Node tests и strict positive/negative type consumers, включая `tests/types/async-state.ts`. Сохраняются проверки прежних ApiClient/bridge/draft APIs.

Отдельная реальная browser-проверка (Chrome или `CHROME_PATH`):

```powershell
npm.cmd run build -w @awesome-telegram/patterns
node_modules/.bin/tsc.cmd -p examples/shop/frontend/tsconfig.json --outDir output/production-run-2026-11-05/mini-app-state/domain
node packages/typescript/tests/async-state-browser.mjs
```

Она использует actual fetch/localStorage/reload, same-origin HTTP fixture и compiled shop domain. Проверяются stale responses, actual fetch abort, cache/account isolation, migration/expiry, unknown pointer после reload, headless order reconciliation и account switch между завершением read и domain continuation. Удаление последнего account-generation guard в отдельной **ignored compiled copy** отклоняется тем же browser assertion; исходный код для мутации не меняется.

Артефакты локального запуска: ignored `output/production-run-2026-11-05/mini-app-state/`. Source/build/Chrome evidence не равно installed tarball/full distribution acceptance. Реальные Telegram clients, физические устройства, keyboard/screen-reader, live server identity и платежи этим browser fixture не подтверждаются.

Сверено 5 ноября 2026: [HTML Web storage](https://html.spec.whatwg.org/multipage/webstorage.html#the-localstorage-attribute) — per-origin shared storage и отсутствие предполагаемого locking; [Storage.setItem](https://developer.mozilla.org/en-US/docs/Web/API/Storage/setItem) — quota отказ; [AbortController.abort](https://developer.mozilla.org/en-US/docs/Web/API/AbortController/abort) — отмена fetch/body/streams. Account generations, allowlist/TTL/migration и recovery pointer — явный контракт этой библиотеки, а не встроенные гарантии Telegram.
