# @awesome-telegram/patterns — TypeScript

Все публичные value/type imports и полные композиции: [справочник TypeScript](../../docs/api-reference-typescript.md), [индекс API](../../docs/api-reference.md). Эти ссылки доступны в source checkout; при передаче tarball отдельно приложите portable references навыка telegram-code-patterns. Declarations доступны в пакете; type exports не существуют в runtime JavaScript.

[Поставка](../../docs/distribution-contract.md): архивы и установленные consumer-проекты проверяются отдельно; прежние публичные API сохранены.

[Адаптеры проекта](../../docs/extension-model.md): публичные structural interfaces для storage/transport/provider, без новой runtime dependency и смены стека.

[Модель ошибок](../../docs/error-model.md): безопасный ErrorReport, категории и recovery без автоматического повтора записи; прежние обработчики исключений сохранены.

Root имеет явные value/type exports; `TextFieldControl` именует результат `createTextField`. [Структура и consumer typing](../../docs/api-structure.md).

Все текущие публичные API experimental. [Зрелость и evidence](../../docs/v1-maturity.md) задаются отдельно: browser/mock проверка не дает обещание стабильности 1.0.

ESM-пакет 0.24.0 с declarations, без runtime dependencies и привязки к React/Vue. Каталог и facade native Mini App API: 99 функций, 44 события официального снимка. Пока поставляется локально из этого репозитория/npm tarball; публикации в npm нет. Node >=20 нужен для tooling/tests. Runtime предназначен для браузера Mini App.

Runtime API сохранен относительно 0.4.0; версия согласована с Python CLI. Новый `bot-mini-app` starter подключает этот tarball, bridge, shell/поле и CSS; backend auth отсутствует. [Галерея и подготовка проекта](../../docs/developer-tools-review.md).

После сборки и npm pack в исходном репозитории, из каталога consumer-проекта:

```powershell
npm.cmd install "C:/path/to/library/output/pattern-library-0.24.0/dist/awesome-telegram-patterns-0.24.0.tgz"
```

В проекте с существующим bundler:

```typescript
import { TelegramBridge, ApiClient, SelectionDraftStore, createAppShell, createTextField } from '@awesome-telegram/patterns';
import '@awesome-telegram/patterns/styles.css';
```

| Компонент | Назначение |
| --- | --- |
| `TelegramNativeAPI(app)` | supports/call для документированных native methods, version + presence gates; listen с own cleanup/dispose |
| `TELEGRAM_NATIVE_METHODS`, `TELEGRAM_NATIVE_EVENTS`, `TELEGRAM_NATIVE_EVENT_DETAILS` | Immutable source metadata, ссылки, minimum versions; literal union types для путей/событий |
| `TelegramBridge(app, lifecycle?)` | Snapshot theme/viewport/insets, стабильные subscriptions, ready один раз, pagehide/pageshow и dispose |
| `ApiClient({baseUrl, headers?}).request(path, decode, options?)` | Один вызов fetch со стороны библиотеки, timeout/cancel, runtime decoder, отказ чужому origin |
| `SelectionDraftStore(() => storage, {namespace, scope, ttlMs})` | Только serviceId/slotId, schema/TTL/verified account scope, наблюдаемые storage errors |
| `createAppShell(host, title)` + `createTextField(document, label, hint)` | Компактная/широкая компоновка, две темы, labels/focus/errors, точки подключения content/summary/actions |

Native catalog/recipe: [99 методов и 44 события](../../recipes/mini-app/README.md), [popup/location composition](../../examples/mini-app/src/native-recipes.ts). `TelegramNativeAPI` получает существующий native object; наличие методов и версия проверяются отдельно от permissions и auth. `call` сохраняет SDK callbacks и возвращает unknown; это не полная схема параметров SDK, не Promise успеха и не automatic retry. `listen` владеет только своими callbacks, прекращает их после cleanup/dispose; неуспешный offEvent можно повторить. Direct onClick/onEvent через `call` очищает сам host. Init и user interaction/permission order проверяются для выбранной функции. Platform unknown означает отсутствие native-клиента для этой facade; browser mock не является авторизацией.

```typescript
const bridge = new TelegramBridge(window.Telegram?.WebApp);
const shell = createAppShell(document.getElementById('app')!, 'Запись');
const unsubscribe = bridge.subscribe(snapshot => shell.applyTheme(snapshot));
bridge.start();
// При окончательном unmount:
unsubscribe(); bridge.dispose(); shell.dispose();
```

Тип `window.Telegram` подключает выбранный SDK/приложение; пакет не добавляет глобальный fake объект. Bridge snapshot не является аутентификацией. `platform: 'unknown'` означает `insideTelegram: false`, даже при наличии объекта WebApp. Для прежних адаптеров без platform сохранено определение по наличию объекта; этот флаг подходит для UI, личность устанавливает backend. Ошибка первого уведомления удаляет неуспешную подписку, а ошибка регистрации SDK снимает частичные подписки и позволяет повторный start. Версионные native APIs и серверный вход подключаются отдельно. `systemInsets` и `contentInsets` не складываются библиотекой: shell получает уже разрешенную геометрию через setInsets. Без нее используется CSS env fallback. После проверки на целевом клиенте продукт задает собственного единственного владельца inset policy.

ApiClient требует runtime decoder вместо `as Order`. Base URL задается доверенной конфигурацией приложения; запрос к иному origin отклоняется. Authentication/CSRF headers передаются по контракту backend, секреты в storage не сохраняются. Успешные HEAD/204/205 передают decoder значение null; decoder должен разрешать его для такого endpoint. Обрыв чтения тела дает `network`, некорректный JSON или отказ decoder — `invalid-response`; timeout/abort сохраняют свои категории. HTTP body/исключение сервера не добавляются в ApiError. Ошибка любой записи помечается `outcome: unknown` консервативно; endpoint может доказать отказ своим контрактом. Library не повторяет запись, не считает AbortController отменой серверного effect и не реализует payments outbox.

Draft scope берется из подтвержденной сессии/tenant, не initDataUnsafe. Namespace, scope и TTL фиксируются при создании store; изменение переданного options-объекта не переключает аккаунт. При смене подтвержденной сессии создайте новый store и восстановите выбор из его scope. В нем сохраняются только идентификаторы выбора; дополнительные поля отбрасываются. Личные контакты, цены, auth и неизвестные operation IDs этим компонентом не хранятся. Recovery неизвестной записи и ее retention должны оставаться отдельными от TTL выбора. `write=false`/`unavailable` дают UI возможность предупредить о несохраненном черновике.

Shell не владеет состоянием формы и ее навигацией: приложение сохраняет их при resize/theme/back. При смене темы не remount поля. Цвета секции, подсказки, разделителя и ошибки берутся из соответствующих optional ThemeParams с CSS fallback; для native controls задается светлая/темная color-scheme. ID полей непрозрачны для приложения, проверяются вместе с hint/error против существующего DOM; доступен fallback без randomUUID. Подтверждение связывайте с прикладной операцией; disabled button не заменяет backend protection. Проверяйте контраст фактических theme colors и достижимость действия при настоящей клавиатуре Telegram. CSS/браузерные tests не подтверждают physical device QA или screen reader.

HTTP redirects запрещены через redirect='error', включая переход на другой сервер с configured headers. Base URL должен указывать прямо на конечный endpoint.

Библиотека не запускает retry loop, но browser/proxy transport может повторить фактический HTTP POST при сетевом обрыве. Это наблюдалось в Chrome 154 при потере ответа после effect. Передавай устойчивый operation ID по контракту backend и проверяй idempotence на сервере; один вызов fetch не гарантирует одну доставку или один effect.

Источники: [Telegram ThemeParams](https://core.telegram.org/bots/webapps#themeparams), [официальный SDK и platform](https://telegram.org/js/telegram-web-app.js), [pagehide](https://developer.mozilla.org/en-US/docs/Web/API/Window/pagehide_event), [fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch), [Response.json](https://developer.mozilla.org/en-US/docs/Web/API/Response/json), [204](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/204), [205](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/205), [color-scheme](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/color-scheme), [randomUUID](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID), [redirect](https://developer.mozilla.org/en-US/docs/Web/API/Request/redirect), [TypeScript declarations](https://www.typescriptlang.org/tsconfig/declaration.html). Контракты сверены 3 октября 2026 года.
