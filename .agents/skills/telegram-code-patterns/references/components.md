# API библиотеки 0.24.0

Термины: **ACK** — ответ на нажатие кнопки через `answerCallbackQuery`: клиент убирает индикатор ожидания; это не сообщение об успехе операции; **CAS** — сравнение с заменой: запись сохраняется, только если версия не изменилась с момента чтения; квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта; **outbox** — события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик выполняет их позже; **неизвестный результат** — запрос мог выполниться, но ответа нет (таймаут, обрыв связи); повторять вслепую нельзя, сначала сверка; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей; **entitlement** — право на возможность (custom emoji, оплаченный доступ), которое проверяется отдельно от самого запроса; **fallback** — запасной вариант, если основная возможность недоступна.

Текущий каталог содержит 45 групп компонентов. Полный перечень публичных импортов и исполняемых примеров — в локальном [справочнике API](api-reference.md); исторические версии ниже показывают время добавления контрактов.

Именованные типы (с 0.7.0): core `Maturity`, `VerificationLevel`; aiogram `ButtonStyle`, `ChatType`, `UpdatePhase`; testing `Responder`; TypeScript `TextFieldControl`. SDK `Bot`/`Dispatcher` импортируйте из aiogram: wildcard library exports теперь явные, существующие документированные function/DTO imports сохранены.

Все группы пока experimental. [Maturity](maturity.md) наследуется их публичными символами; SDK/mock/browser/live — отдельный уровень доказательств. `RecipeCatalog.search` дополнительно принимает `maturity`, а `Recipe` содержит этот immutable field.

Локальный репозиторий/wheel/tarball; публикация в реестрах не подтверждена. Python >=3.11. TypeScript ESM с declarations; Node >=20 для tooling. Core Python/browser runtime без сторонних dependencies; aiogram extra >=3.31,<4 испытан на 3.31.0. Другую версию SDK проверяйте отдельно.

В 0.4.0 добавлены `inline_keyboard`, `reply_keyboard`, `input_prompt`, `remove_keyboard` для native rows/input; `method_catalog`, `build_request`, `InvalidAPIRequest`, `MethodSpec` для SDK requests; `event_router`, `UpdateObserver`, `UpdateTrace`, `update_kinds` для native updates. Все импортируются из `telegram_patterns.aiogram`. TypeScript: `TelegramNativeAPI`, `UnsupportedTelegramCapability`, `TELEGRAM_NATIVE_METHODS`, `TELEGRAM_NATIVE_EVENTS`, `TELEGRAM_NATIVE_EVENT_DETAILS` и соответствующие literal union types. Практические примеры/границы — [keyboard-recipes.md](keyboard-recipes.md). Request catalog не является доказательством live поддержки/прав, native call сохраняет unknown результат и callbacks SDK.

| Намерение | Публичный API | Граница |
| --- | --- | --- |
| Поиск примера | `from telegram_patterns import Recipe, RecipeCatalog`; `.search(query,category=None,language=None,verification=None,limit=20)`, `.get(id)` | Core без SDK; bundled snapshot, metadata scope; не исполняет код. [Поиск и CLI](developer-tools.md) |
| Новый проект | `from telegram_patterns import StarterPlan, create_starter`; `create_starter(target,library=...,template='bot',typescript=None,dry_run=False)` | Новый каталог из локального исходника или wheel; по желанию — tarball TypeScript той же версии. Ничего не устанавливает, не перезаписывает и не ходит в сеть; при ошибке ввода-вывода могут остаться частично созданные новые файлы |
| Doctor | `from telegram_patterns.cli import doctor`; `doctor(path,require_token=False)` | Только чтение локального окружения: импорты, манифест, формат токена; .env не читает; отсутствующий SDK — fail, токен по умолчанию — warn; готовность живого бота не проверяет |
| Mini App auth | `from telegram_patterns import validate_init_data`; `validate_init_data(raw, token, *, max_age_seconds=3600, future_tolerance_seconds=30, now=None)` | Сырой URL-encoded initData; HMAC исключает только hash; дубли/просрочка/невалидный user отклоняются. Возвращает VerifiedLaunch(user_id,auth_date,user); не OIDC/Ed25519/ACL |
| SQLite effect/replay | `from telegram_patterns import SQLiteOnce, OperationConflict`; `SQLiteOnce(path).initialize()`, `run(scope,key,payload,apply)` | Только синхронный effect на переданном connection; без network/COMMIT/ROLLBACK. Возвращает OnceResult(value,replayed), измененный payload — OperationConflict |
| /start | `from telegram_patterns.aiogram import start_router`; `start_router(text, keyboard=None)` | Добавить Router в существующий Dispatcher; stateless plain text |
| Кнопка | `action_keyboard(text,key,*,prefix='act:',style=None,custom_emoji_id=None,emoji_entitlement_verified=False)` из `telegram_patterns.aiogram` | Style primary/success/danger; key ASCII 1..48, callback_data <=64 bytes. Emoji исключен без server-verified capability целевого контекста |
| Callback | `callback_router(execute,notify,*,prefix='act:')` из `telegram_patterns.aiogram` | ACK до execute(Action(actor_id,key)); сервис проверяет owner/version/replay. notify(query,ActionResult(status,text)) выбирает канал, включая inline/inaccessible |
| Stars | `stars_invoice(title,description,payload,stars,*,monthly_subscription=False)` из `telegram_patterns.aiogram` | CreateInvoiceLink без запроса. XTR/один price; monthly period 2592000, максимум 10000 Stars. Consent/charge verification/grant — приложение |
| Настройки бота | `from telegram_patterns import BotSettings`; `BotSettings.from_env(token_var='BOT_TOKEN')` | Core без SDK. Формат token, repr без секрета; явная сериализация token не защищена |
| Меню | `ActionButton(text,key,style=None,custom_emoji_id=None)`, `action_menu(buttons,columns=2,prefix='act:',emoji_entitlement_verified=False)` из `telegram_patterns.aiogram` | До 100 кнопок, 1..8 колонок — лимиты компонента; уникальные keys, пустой список дает пустую keyboard |
| Страницы | `paginated_menu(buttons,page=0,page_size=6,columns=2,action_prefix='act:',page_prefix='page:',emoji_entitlement_verified=False)`; `page_number(data,prefix='page:')` | MenuPage(markup,page,page_count,total_items); 0-based, clamp старой страницы; malformed callback дает None. Это local sequence, не SQL cursor/ACL |
| Команды | `CommandReply(command,description,text,keyboard=None)`; `command_router(specs)`, `command_menu(specs)` из `telegram_patterns.aiogram` | Статический plain text, разные ответы/SDK mention filter; BotCommand DTO без API вызова. Динамические handlers и права остаются у проекта |
| Запуск | `await run_bot(dispatcher,settings,commands=None,session=None,workflow_data=None,...)` из `telegram_patterns.aiogram` | Текущий Dispatcher; владеет Bot session после preflight. Commands opt-in заменяет default scope; no webhook deletion/update dropping |
| Локальный transport | `from telegram_patterns.testing import StubSession`; `StubSession().respond(Method,response)` | Явные SDK response fixtures, calls/closed; unexpected method и streaming падают. Без HTTP fallback, не live Telegram |
| Текстовые формы | `TextField(name,label,prompt,max_length=128,validate=None)`, `InvalidField`, `FormSubmission`, `text_form_router(fields,on_submit,name='application',command='apply')` из `telegram_patterns.aiogram` | Обычный личный чат; FSM и изоляцию дает проект; /back, /cancel, проверка ответов и кнопка отправки. Надежный эффект, повтор и права доступа — на стороне сервиса; ID сохраняется при неизвестном результате |
| Bridge | `import {TelegramBridge} from '@awesome-telegram/patterns'`; `new TelegramBridge(app,lifecycle?)` | subscribe/start/dispose; ready один раз, pagehide/pageshow. Snapshot не аутентификация; host задает SDK |
| HTTP | `ApiClient, ApiError` из npm-пакета; `new ApiClient({baseUrl,headers?})`, `request(path,decode,{method?,body?,signal?,timeoutMs?})` | Decoder принимает unknown. Чужой origin/redirects отклоняются. Один вызов fetch библиотекой; ошибки записи outcome unknown; GET/HEAD read-failed |
| Черновик | `SelectionDraftStore` из npm-пакета; `new SelectionDraftStore(()=>storage,{namespace,scope,ttlMs})` | Только serviceId/slotId; schema/TTL/серверный scope. read: restored/missing/expired/corrupt/unavailable; write может вернуть false |
| UI | `createAppShell(host,title), createTextField(document,label,hint)` из npm-пакета; CSS subpath `@awesome-telegram/patterns/styles.css` | Оболочка с областями `content`, `summary`, `actions` и методами `applyTheme`, `setInsets`, `dispose`; у поля — `label`, `hint`, `error`. Состоянием и навигацией управляет проект |

Для SQLite scope включает проверенный tenant/actor/action. ACL проверяется и для replay. В async-сервисе синхронный storage требует thread boundary. Не заменяйте PostgreSQL SQLite ради helper. Ledger не имеет автоматического TTL: retention задается продуктом.

В 0.1.1 SQLite authorizer блокирует случайные COMMIT/ROLLBACK и неявный commit executescript до сохранения эффекта. Используйте execute/executemany; локальные savepoints разрешены. Callback — доверенный код проекта: не меняйте authorizer/режим транзакций и не закрывайте connection. Защита не изолирует произвольный Python-код и не покрывает внешний сетевой эффект.

Импортируйте `Action`/`ActionResult` из `telegram_patterns.aiogram`. Status accepted/denied/stale/replayed. Premium нажавшего пользователя не подтверждает emoji entitlement бота. Inline/inaccessible query не гарантирует доступного message/chat. ACK — снятие spinner, не сообщение об успешной записи.

Для новых bot tools используйте [рецепты](bot-recipes.md), сохраняя выбранный SDK и текущую композицию. CommandReply не является ACL/FSM. Run_bot предназначен для одного polling Bot; multibot/webhook/готовый Bot lifecycle остаются у SDK. Handle_as_tasks/concurrency влияют на обработку SDK, не создают durable acceptance. Статические меню не заменяют проверенную actor/tenant identity.

Для формы прочитайте [локальный рецепт](form-recipes.md). Dispatcher должен иметь включенную actor-scoped event isolation. Сервис получает bot_id/actor_id/chat_id, operation_id и immutable values; проверяет права до effect и replay. После ошибки отправки нельзя сменить ID, очистить pending или повторить side effect без сверки. MemoryStorage/SimpleEventIsolation не дают restart/multi-worker гарантий.

API decoder проверяет runtime данные; `as Order` недостаточно. Успешные HEAD/204/205 передают null; decoder должен разрешать этот ответ. Обрыв чтения тела — network, некорректный JSON/decoder — invalid-response. Auth/CSRF headers идут по контракту backend. После unknown сверяйте серверную операцию с тем же operation ID. AbortController не отменяет серверный effect. SelectionDraftStore не хранит recovery identity, auth, контакты или цены; retention неизвестной операции организуется отдельно от TTL выбора. Scope не берется из initDataUnsafe. Namespace/scope/TTL фиксируются при создании; смена проверенной сессии требует нового store.

Bridge использует optional platform: при unknown insideTelegram=false; без platform сохранена совместимость с адаптерами по наличию объекта. Флаг подходит только для UI. Ошибка первого subscriber не оставляет его в подписках; частичная неуспешная регистрация SDK очищается, start можно повторить. Shell использует optional семантические цвета ThemeParams и native color-scheme; ID поля/hint/error непрозрачны и проверяются против существующего DOM.

«Один запрос» здесь означает один вызов fetch библиотекой. Browser/proxy transport может повторить HTTP при обрыве; серверная идемпотентность нужна даже без прикладного retry. Устойчивый operation ID и проверка прав до replay принадлежат продукту.

System/content insets имеют разный смысл. Shell получает разрешенную host-геометрию, не угадывает сумму/max; без нее CSS env fallback. Состояние поля сохраняется при theme/resize. Контраст фактических Telegram colors, soft keyboard и physical QA проверяются в целевом клиенте.

Частично проверенные источники 3 октября 2026 года: [Bot API](https://core.telegram.org/bots/api), [Mini Apps/ThemeParams](https://core.telegram.org/bots/webapps#themeparams), [официальный WebApp SDK](https://telegram.org/js/telegram-web-app.js), [aiogram Router](https://docs.aiogram.dev/en/latest/dispatcher/router.html), [SQLite authorizer](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.set_authorizer), [executescript](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.executescript), [Response.json](https://developer.mozilla.org/en-US/docs/Web/API/Response/json), [204](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/204), [205](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/205), [color-scheme](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/color-scheme), [randomUUID](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID), [fetch](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch), [redirect](https://developer.mozilla.org/en-US/docs/Web/API/Request/redirect). Это сверка перечисленных контрактов, не live аккаунт/платеж.

Storage/transport/provider interfaces (с 0.9.0): OnceStore/AsyncTransport/ProviderAdapter/RefundProvider и KeyValueStorage/StorageFactory/FetchTransport. Параметры и проверки адаптера — в локальной [модели расширения](extensions.md).

Core starter (с 0.10.0): StarterComponent, StarterConflict, starter_components; create_starter components keyword и StarterPlan.components/requested_components. Закрытый набор и сценарии — [выбор компонентов](starter-selection.md).

Планы и локальный runner добавлены в 0.13.0: `RecipeRunPlan`, `RecipeRunResult`, `plan_recipe`, `run_recipe_offline` из Python root; [requirements/fixtures/границы](recipe-execution.md). В текущей 0.24.0 есть 213 Python fixtures и 99 native references без executor; offline_ready не означает live разрешение.

С 0.14.0 KeyboardLayout/KeyboardCapabilities и action_layout/inline_layout/reply_layout описаны в [композициях клавиатур](keyboard-layouts.md): плоский список кнопок, шаблон ширины рядов, проверка снимка и контекста, запасной вариант, если клиент не поддерживает возможность.

Навигация сообщений: `NavigationScreen`, `NavigationState`, `NavigationResult`, `MessageNavigation`, `navigation_router`; полный [контракт](message-navigation.md). Все пять public exports experimental; state локальный, business ACL и persistent state остаются у проекта.

Составные элементы выбора: `SelectionOption/Spec/Context/State/Result/SelectionMenu` из SDK-free root и `selection_keyboard/selection_router` из optional aiogram. [Server rules и confirmation](selection-controls.md) описывают границы локального намерения и бизнес-транзакции host.

Расширенные поля (с 0.18.0): `FieldValue`, `NumberField`, `EmailField`, `PhoneField`, `DateField`, `FileField`, `ContactField`, `LocationField`, `DialogSubmission`, `dialog_form_router` из optional aiogram. Полная [композиция и ограничения](dialog-fields.md); строковые старые формы сохраняют контракт.

## Сообщения

`MessageBuilder/FormattedText/TextEntity`, `EntityKind/TextPayload`, UTF-16/HTML/MarkdownV2 helpers и split_formatted — SDK-free API. [Полная композиция](message-text.md) сохраняет текущий Dispatcher и связывает literal user text, explicit parse_mode=None и lossless partition. Capability flag не проверяет custom emoji metadata/entitlement; host делает это отдельно.

Для optional aiogram медиа (с 0.20.0) — [полный контракт](media.md): загрузка байтов или `file_id` того же бота, подпись как обычный текст, альбом и редактирование, чтение файла с ограничением размера. Отправку, повторы, кодеки и права доступа библиотека не гарантирует; используется `Bot` проекта.

[Профили (с 0.21.0)](profiles.md): read observations и own-bot patch с host ACL; без hidden data/MTProto/Business и автоматического retry.

[Inline-поиск (с 0.22.0)](inline-search.md): `InlineSearch`, `InlineItem`, `InlinePage`, `InlineCachePolicy`, `inline_articles`, `inline_query_router` и типы host adapters импортируются из `telegram_patterns.aiogram`. Только явно shareable результаты, текущая host ACL, подписанный cursor и явная политика кеша. Персональный кеш не делает отправленное сообщение приватным; positive cache может пережить изменение прав без нового Update. Потерянный ответ не повторяется автоматически.

[Опросы (с 0.22.0)](polls.md): `PollSpec`, `PollChoice`, `poll_request`, `poll_state`, `poll_vote`, `poll_option_added`, `PollBinding`, `PollLocator`, `PollEvent`, `poll_events_router` и типы наблюдений/host adapters из `telegram_patterns.aiogram`. Современные multi-correct quiz и persistent option IDs; доступны только собственные зарегистрированные события. Host владеет правами, durable intent и receipts. Нет `getPoll`, полного списка скрытых голосующих или автоматического повторного создания опроса после unknown outcome.

## platform-operations

Импорт из `telegram_patterns.aiogram`: `PlatformContract`, `PlatformScope`, `PlatformPermit`, `PlatformAction`, `PlatformReceipt`, `PlatformResult`, `PlatformHooks`, `SecretToken`, `PlatformEvent`, `PlatformLookup`, `PlatformObserver`, `platform_contracts`, `execute_platform_action`, `managed_bot_link`, `platform_event`, `platform_events_router`, `StoryPhotoUpload`, `StoryVideoUpload`.

Темы, реакции, заявки, Business, stories, gifts и managed bots с текущими правами и durable host intent. [Контракт и полный пример](platform-operations.md).

- Закрытый список из 51 метода Bot API в семи семействах: нативные запросы SDK и текущие права конкретного метода, а не произвольный MTProto или история аккаунта.
- Текущие права, ресурс, ревизия, связи подключений и дочерних ботов, проверка медиа и допустимая активность принадлежат приложению.
- Запись требует атомарной долговечной заявки на отправку; бюджет, согласие и котировка перепроверяются до нативного ввода-вывода.
- Локальное резервирование и свежая котировка не гарантируют атомарного удаленного списания или финансовых расчетов.
- Неизвестный результат, квитанция или падение остаются тем же намерением: без автоматического повтора, отката, сверки и глобального inbox/outbox.
- Запрос на вступление использует исходное время получения и оставшийся срок; личные темы поддерживают только явно разрешенные методы.
- Создание управляемого бота требует подтверждения пользователя; repr токена скрыт, но хранение и сериализация секрета остаются на стороне приложения.
- Загрузка историй использует проверенный вложенный multipart SDK; кодек, размеры, содержимое и время жизни файла — обязанности приложения.
- События сохраняют неизвестные и анонимные факты; привязка, дедупликация, порядок и отзыв — на стороне приложения, без выведенного автора и истории.
- Доказательства автора (SDK, mock, браузер) отделены от живых прав, реальных устройств, удаленного списания и независимой приемки.

| Рестарт диалога | `FSMSnapshot`, `FSMConflict`, `SnapshotStore`, `AtomicFSMStorage`, `SnapshotFSMStorage`, `DialogLifetime` из optional aiogram | Хранилище проекта атомарно обновляет состояние и данные через CAS, с версией и сроком жизни; просроченный черновик — не то же самое, что незавершенный эффект. [Самостоятельный пример](dialog-restart.md); `MemoryStorage` не переживает рестарт, распределенную и живую проверку проводите отдельно. |
