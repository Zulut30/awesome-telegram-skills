# awesome-telegram-patterns — Python

Семь типов полей: `NumberField/EmailField/PhoneField/DateField/FileField/ContactField/LocationField`, `FieldValue`, `DialogSubmission` и `dialog_form_router` из optional aiogram. [Готовая композиция](../../docs/dialog-fields.md): текущий автор/вопрос, native candidate confirmation, back/cancel и unknown receipt с тем же intent. Прежние текстовые формы сохраняют контракт.

Календарь и UTC/DST: `CalendarMonth`, `TimeSlot`, `resolve_local_time`; current ACL и atomic booking/replay: `SlotSchedule`, `SlotBooking`, `SQLiteSlotStore`; optional aiogram: `calendar_keyboard`, `time_slot_keyboard`. IANA data на Windows — extra `calendar` (проверено tzdata 2026.5). [Контракт и пример](../../docs/calendar-slots.md). UI snapshot не резервирует ресурс; receipt отличается от current booking status.


`plan_recipe` / `run_recipe_offline` и CLI `run-recipe` показывают требования всех 310 cookbook recipes и запускают 210 известных Python fixtures без токена. Core SQLite работает без SDK; 99 native references отклоняются без host/аргументов. [План, effects и ограничения](../../docs/recipe-execution.md). Требуется установленный пакет; runner не выполняет найденный recipe.code.

RecipeCatalog.search добавляет optional task/context/sdk/sdk_version/api_version. Recipe хранит immutable metadata и repository source/check links; legacy schema 1 defaults сохранены. Поиск SDK-free, без исполнения: [навигация рецептов](../../docs/gallery-navigation.md).

Справочник публичных imports и полные примеры: [Python core](../../docs/api-reference-core.md), [bot и test transport](../../docs/api-reference-bot.md), [индекс API](../../docs/api-reference.md). Эти ссылки доступны в source checkout; при передаче wheel отдельно приложите portable references навыка telegram-code-patterns. Пакет не зависит от документации при выполнении.

[Поставка](../../docs/distribution-contract.md): архивы и установленные consumer-проекты проверяются отдельно; прежние публичные API сохранены.

[Адаптеры проекта](../../docs/extension-model.md): публичные structural interfaces для storage/transport/provider, без новой runtime dependency и смены стека.

[Модель ошибок](../../docs/error-model.md): безопасный ErrorReport, категории и recovery без автоматического повтора записи; прежние обработчики исключений сохранены.

Root экспортирует `Maturity`, `VerificationLevel`; aiogram — `ButtonStyle`, `ChatType`, `UpdatePhase`; testing — `Responder`. [Структура API](../../docs/api-structure.md) определяет явные exports и migration wildcard SDK imports.

Все текущие группы experimental, request-only/native fragments reference. [Политика зрелости](../../docs/v1-maturity.md) не зависит от проверки: `Recipe.maturity`, `RecipeCatalog.search(maturity=...)`, CLI `recipes --maturity ...`. Старые schema-1 records читаются с conservative default.

Общие компоненты для бота и backend, версия 0.24.0. Пакет пока поставляется из этого репозитория/локального wheel; публикации на PyPI нет. Python >=3.11. Core использует стандартную библиотеку; адаптер aiogram и тестовый транспорт — отдельный extra.

[Медиа](../../docs/media.md): `MediaFile`/`MediaItem`, `media_request`, `media_album`, `media_edit`, `download_media` и typed результаты. Byte upload, same-bot file_id, literal caption/entities, совместимый альбом и bounded explicit download через текущий Bot. Host проверяет codec/content, ACL и delivery; downloader не записывает файлы и не закрывает host session.

[Галерея 310 рецептов](../../gallery/index.html) работает без токенов и сети. В wheel входят `RecipeCatalog`, шаблоны новых проектов и CLI `telegram-patterns recipes/init/doctor`. [Использование и границы](../../docs/developer-tools-review.md).

Новое: [клавиатуры и ввод](../../recipes/bot-api/keyboards.md), [отслеживание Update](../../recipes/bot-api/events.md), [185 Bot API request-рецептов](../../recipes/bot-api/README.md). [Бот-пример](../../examples/python/keyboards_bot.py) показывает строки/цвета, обработку/редактирование и input UI; [offline-сценарий](../../examples/python/offline_keyboards.py) проверяет ту же композицию. Native SDK выполняет транспорт; request-only рецепты содержат искусственные данные, не отправляйте их без замены.

Из корня репозитория в окружение целевого проекта:

```powershell
python -m pip install ./packages/python
python -m pip install "./packages/python[aiogram]"
```

Первый вариант достаточен для `BotSettings`, `validate_init_data`, `SQLiteOnce`, `RecipeCatalog` и `create_starter`. Второй нужен для импорта `telegram_patterns.aiogram` и `telegram_patterns.testing`, запуска бота и успешной SDK-проверки doctor. Сохраняйте существующий SDK, если бот уже построен на другой библиотеке.

Doctor 0.11.0 проверяет установленный adapter в фиксированном Python `-I -B` probe вне каталога проекта. Он отклоняет подмену aiogram import, сохраняет конфигурацию и показывает reason/remediation с отдельными argv рекомендациями. HTTP-проверки и автоматического исполнения исправлений нет.

| Компонент | API | Контракт |
| --- | --- | --- |
| Поиск рецепта | `RecipeCatalog().search(query,category=None,language=None,verification=None,limit=20)`; `.get(id)`; `.recipes` | Bundled snapshot, все слова запроса, SDK/mock/reference/live scope; без исполнения кода и SDK dependency |
| Новый проект | `create_starter(target,library=local_path,template='bot',typescript=None,dry_run=False)` | Новый каталог, локальные артефакты; StarterPlan и список файлов; без install/network/overwrite |
| Диагностика | `telegram-patterns doctor [project] [--require-token]`; `telegram_patterns.cli.doctor(path)` | Read-only проверки с reason/remediation и argv рекомендациями; target/manifest failures контролируются, .env/token contents не читаются/не отражаются; предлагаемые команды не исполняются |
| Native клавиатуры | `inline_keyboard(rows,chat_type='private',business=False,invoice=False,force_reply=False,emoji_entitlement_verified=False)`; `reply_keyboard(rows,...,placeholder=None)` | SDK button models / reply strings, копии строк; caller сообщает фактический context и entitlement. Не все права/контекстные ограничения Telegram проверяются локально |
| Ввод | `input_prompt(placeholder=None,selective=False)`; `remove_keyboard(selective=False)` | ForceReply / ReplyKeyboardRemove без HTTP; host связывает actor/chat/prompt и проверяет ответ |
| Все SDK методы | `method_catalog()`; `build_request(name,parameters=None)` | MethodSpec / native TelegramMethod; неизвестные top-level fields отклоняются, nested rules — SDK. HTTP только при `await existing_bot(request)` |
| События | `event_router(handlers)`; `UpdateObserver(record,include_ids=False)`; `update_kinds(update)` | Native Router и best-effort metadata received/handled/unhandled/failed/cancelled. Middleware не создает подписок или durable audit |
| Проверка запуска | `validate_init_data(raw, bot_token, *, max_age_seconds, now)` | Сырой initData, HMAC и freshness; возвращает подписанные user_id, `start_param`, `chat_type`, `chat_instance`, `query_id`, `chat`, `receiver` (глубоко read-only, копия — `.as_dict()`). Не OIDC/Ed25519 и не объектные права |
| Однократная операция | `SQLiteOnce(path).initialize(); run(scope, key, payload, apply)` | Effect и replay result в одной SQLite transaction. Payload — только JSON-значения со строковыми ключами (tuple и `{1: ...}` отклоняются). Scope/права проверяет сервис |
| Команда старта | `start_router(text, keyboard=None)` | Небольшой /start с plain text; добавить Router в текущий Dispatcher |
| Кнопка | `action_keyboard(text, key, style=..., ...)` | Opaque callback key, style, проверенный entitlement либо emoji fallback |
| Callback | `callback_router(execute, notify)` | ACK до прикладной работы. `execute` проверяет owner/version/replay; `notify` выбирает безопасный канал |
| Stars invoice | `stars_invoice(title, description, payload, stars, monthly_subscription=False)` | Готовый `CreateInvoiceLink`, без сетевого запроса и выдачи доступа |
| Настройки | `BotSettings.from_env(token_var='BOT_TOKEN')` из core | Формат token/непустое окружение проверяются; token исключен из repr, остается доступным явно |
| Меню кнопок | `ActionButton(text,key,style=None,custom_emoji_id=None)` + `action_menu(buttons,columns=2,prefix='act:')` | Уникальные keys, rows и emoji fallback; до 100 кнопок, 1..8 колонок — ограничения компонента |
| Пагинация | `paginated_menu(buttons,page=0,page_size=6,...)`; `page_number(data,prefix='page:')` | MenuPage с markup/page/page_count/total_items; разные префиксы действий и навигации |
| Статические команды | `CommandReply(command,description,text,keyboard=None)` + `command_router(specs)` / `command_menu(specs)` | Один список для Router и BotCommand DTO; plain text, SDK фильтрует чужой mention |
| Polling | `await run_bot(dispatcher,settings,...)` | Текущий Dispatcher, workflow data, закрытие Bot session; команды устанавливаются только явно |
| Локальные тесты | `StubSession().respond(Method,response)` из `telegram_patterns.testing` | Реальный SDK/Dispatcher, список calls, проверка возвращаемого типа; нет HTTP fallback |
| Текстовая форма | `TextField`, `InvalidField`, `FormSubmission`, `text_form_router(fields,on_submit,name='application',command='apply')` | Личный чат, проверка/возврат/отмена/подтверждение; host FSM isolation, стабильный ID для сервиса |

## Бот с двумя командами

Установи extra aiogram, передай BOT_TOKEN своего тестового бота в окружение и запусти файл:

```python
import asyncio
from aiogram import Dispatcher
from telegram_patterns import BotSettings
from telegram_patterns.aiogram import CommandReply, command_menu, command_router, run_bot

commands = [CommandReply("start", "Начать", "Привет!"),
            CommandReply("help", "Помощь", "Этот бот поддерживает /start и /help.")]
dispatcher = Dispatcher()
dispatcher.include_router(command_router(commands))
asyncio.run(run_bot(dispatcher, BotSettings.from_env(), commands=command_menu(commands)))
```

Для текущего проекта подключи Router к его Dispatcher. `CommandReply` предназначен для статического plain text; динамические ответы, FSM, права и локализованное меню остаются в SDK/сервисах проекта. Command/description имеют лимиты Bot API; reply ограничен 4096 UTF-16 units консервативно. Router сохраняет snapshot клавиатуры и отключает parse mode для этих ответов. `command_menu` только строит DTO: `bot.set_my_commands(..., scope=..., language_code=...)` остается явным действием.

## Кнопки и каталог

```python
from telegram_patterns.aiogram import ActionButton, action_menu, paginated_menu, page_number

buttons = [ActionButton("Тарифы", "plans", style="primary"),
           ActionButton("Помощь", "help")]
keyboard = action_menu(buttons, columns=2)
page = paginated_menu(buttons, page=0, page_size=6, page_prefix="catalog-page:")
target = page_number(callback_data, prefix="catalog-page:")  # None при неверных данных
```

Builders не подключают handlers: для действий используй `callback_router(execute,notify)` или текущие SDK handlers. В [полном примере](../../examples/python/bot.py) связаны /start, /help, страницы, ACK и выбор элемента. Пагинация принимает локальную последовательность; для большого SQL-каталога нужен собственный query/cursor. Индекс страницы начинается с 0; page_size 1..98 оставляет место для двух navigation buttons. После уменьшения списка запрос старой страницы ограничивается последней; пустой список дает page=0/page_count=1/total_items=0 и пустую клавиатуру. Неверный callback возвращает None; он не дает права на объект. Проверяй tenant/actor/revision перед частной выдачей или изменением.

## Lifecycle и проверка без Telegram

`run_bot` создает один Bot и владеет его session, включая явно переданную session; после успешного preflight она закрывается при нормальном завершении, ошибке регистрации меню, ошибке polling и cancellation. При отмене сначала используется SDK stop_polling: прямой cancel внешней SDK задачи может оставить polling child активным. Ожидание ограничивает shutdown_timeout (по умолчанию 10 секунд), в том числе при зависшем startup-hook. При отказе preflight переданная session остается у caller. Используй Dispatcher эксклюзивно для одного polling entrypoint. Dispatcher/routers/middleware/FSM проекта сохраняются. `workflow_data={'service': service}` передает прикладные зависимости; SDK параметры в нем запрещены, для polling есть явные kwargs.

По умолчанию commands=None сохраняет меню. Переданный список устанавливает DEFAULT scope, пустой список очищает этот scope; для других scopes/languages вызывай SDK явно. Helper не удаляет webhook и не выбрасывает updates. Для webhook/multibot или готового Bot lifecycle используй существующий SDK entrypoint. `handle_as_tasks` повторяет default SDK; его отключение и лимит concurrency не заменяют durable acceptance/идемпотентность. Application resources и завершение прикладных handler tasks организуй через lifecycle своего проекта; runner управляет Bot session и polling, без общего task-drain. `.env` loader не требуется и автоматически не запускается. `BotSettings` скрывает token в repr/ошибках проверки формата; `settings.token` и `dataclasses.asdict` содержат секрет, их нельзя логировать.

```python
from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery
from telegram_patterns.testing import StubSession

session = StubSession().respond(AnswerCallbackQuery, True)
# В async test:
# async with Bot("100:TEST_FIXTURE", session=session) as bot:
#     await bot.answer_callback_query("fixture-query")
# assert isinstance(session.calls[0], AnswerCallbackQuery)
```

Ответ может быть SDK моделью/словарем либо sync/async функцией от TelegramMethod. Возвращаемый тип проверяется через SDK/Pydantic, включая integer timestamps. Незарегистрированный метод падает, file streaming запрещен, HTTP fallback отсутствует. Это synthetic API fixtures; доставка, серверные права и поведение настоящего Telegram ими не подтверждаются.

Готовый [offline-сценарий](../../examples/python/offline_bot.py) использует тот же create_app, что и live пример: команда → страница → выбор → ответ, с проверкой исходящих методов:

```powershell
uv run --with-editable "./packages/python[aiogram]" python examples/python/offline_bot.py
```

## Формы заявок и многошаговые диалоги

```python
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from telegram_patterns.aiogram import TextField, text_form_router

# Для НОВОГО простого бота. В существующем проекте сохраняйте его Dispatcher,
# storage и включенную actor-scoped event isolation.
dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
dispatcher.include_router(text_form_router([
    TextField("topic", "Тема", "Какую тему выбрать?"),
    TextField("brief", "Задача", "Опишите задачу.", max_length=256),
], applications.submit))  # Существующий async сервис проекта, см. контракт ниже.
```

Пользователь вызывает /apply, отвечает на поля, проверяет сводку и нажимает «Отправить». /back удаляет ответы начиная с предыдущего шага; /cancel очищает форму. Команды другого бота и чужое FSM состояние не перехватываются; /help проходит к handlers проекта. Router подключается перед общим catch-all handler.

`TextField(name,label,prompt,max_length=128,validate=None)` обрезает пробелы и проверяет длину в UTF-16 units; 1..10 уникальных полей, максимум 256 units на значение. Синхронный validator возвращает нормализованную строку или выбрасывает `InvalidField` с понятным сообщением. Неожиданные ошибки не выдаются за неверный ввод. Ответы и сводка идут в plain text, даже при глобальном HTML parse mode. Пароли/token в форму не собирайте. Values исключены из repr FormSubmission, явная сериализация по-прежнему содержит ответы.

`on_submit(submission: FormSubmission) -> awaitable[str]` получает bot_id/actor_id/chat_id из серверного update, immutable values и operation_id. Сервис отдельно проверяет права/значения и надежно сохраняет effect + replay result под этим ID. Handler ACK выполняется до сервиса; кнопка связана с текущими owner/operation/message. После успешного результата форма очищается до отправки ответа. При exception/cancellation сохраняются values/ID; /back, /cancel и новый /apply блокируются до сверки той же заявки через повтор кнопки. Router не выполняет автоматический сетевой retry. Ошибка сервиса передается error handling проекта; пользователю отправляется контролируемый текст без деталей exception.

FSM и event isolation обязательны; обычный Dispatcher с DisabledEventIsolation отклоняется до изменения данных. SimpleEventIsolation работает в одном процессе. MemoryStorage не переживает рестарт и не удаляет бездействующие черновики по времени; для требований restart/multi-worker/retention настройте storage, lock и восстановление в проекте. Незавершенный effect требует отдельного durable operation record/сверки; очистка draft по TTL не должна потерять identity неизвестного результата. При изменении схемы несовместимое состояние отклоняется без автоматического сброса. Компонент рассчитан на обычные личные чаты бота; группы и Business исключены. Подходящий SDK dialog остается у проекта, если нужны contact/media/сложные ветвления.

Готовый [бот заявки](../../examples/python/form_bot.py) сочетает этот Router с авторизованным create-only сервисом и SQLiteOnce. Бизнес-запись долговечна; FSM примера находится в памяти. БД и ее schema принадлежат примеру, существующую PostgreSQL БД заменять не нужно. Проверить тот же create_app без сети:

```powershell
uv run --with-editable "./packages/python[aiogram]" python examples/python/offline_form.py
```

Для тестового бота с BOT_TOKEN: `uv run --with-editable "./packages/python[aiogram]" python examples/python/form_bot.py ./applications.sqlite`. Пример явно устанавливает default command menu тестового бота. Полный [контракт и проверка](../../docs/form-tools-review.md).

Для нового form API 3 октября 2026 сверены [aiogram FSM](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/index.html), [storage](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html) и [Dispatcher/FSM isolation](https://docs.aiogram.dev/en/latest/_modules/aiogram/dispatcher/dispatcher.html), а также установленный код aiogram 3.31.0. Эта сверка относится к форме и не обновляет остальные исторические источники.

## Backend компоненты

```python
from telegram_patterns import validate_init_data

launch = validate_init_data(raw_init_data, server_bot_token, max_age_seconds=300)
actor_id = launch.user_id  # Затем создать/проверить сессию и права конкретного объекта.
```

```python
from telegram_patterns import SQLiteOnce

once = SQLiteOnce("app.sqlite")
once.initialize()  # В существующем проекте включить схему в его миграции.
result = once.run(
    "tenant:1:user:42:booking", "server-issued-operation-key", {"slot": "slot-1"},
    lambda db: {"id": db.execute(
        "INSERT INTO bookings(slot) VALUES (?)", ("slot-1",)
    ).lastrowid},
)
```

Таблица `bookings` и ее constraints принадлежат приложению. Не выполняйте network calls, COMMIT/ROLLBACK или изменения других БД в `apply`. В 0.1.1 authorizer блокирует управление транзакцией до сохранения эффекта, включая неявный COMMIT от `executescript`; при нарушении SQLite выбрасывает DatabaseError и операция откатывается. Для нескольких SQL-команд используйте `execute`/`executemany`. Локальные savepoints разрешены. Callback — доверенный код приложения: он не должен заменять authorizer, закрывать connection или менять режим транзакций. Это защита от случайного нарушения контракта, без изоляции произвольного Python-кода.

Уже сохраненный результат возвращается при том же scope/key/payload; новый payload дает OperationConflict. Записи ledger автоматически не истекают. Хранение/очистка и допустимое окно повторов задаются продуктом. SQLite не заменяет текущую PostgreSQL БД. Синхронную операцию в async-сервисе вызывайте через подходящий thread boundary, например `asyncio.to_thread`.

Auth freshness по умолчанию: 3600 секунд, граница `age < max_age_seconds`, допуск будущего 30 секунд. Политика настраивается сервером. Data size ограничен 16384 символами/64 полями, URL декодируется один раз, дубли отклоняются. Некодируемые данные запуска отклоняются как `InvalidInitData`. Секрет остается на сервере; ошибки не включают его или raw данные. Подписанные optional поля не дают прикладных полномочий.

Aiogram протестирован на 3.31.0. Кнопочный entitlement передавайте только после проверки возможности для целевого контекста; Premium нажимающего не является доказательством. Условия/согласие перед Stars покупкой, pre-checkout, успешное списание, возврат и выдача доступа реализуются в сервисе. Helper invoice не объявляет покупку оплаченной.

Источники: [BotCommand](https://core.telegram.org/bots/api#botcommand), [Bot API](https://core.telegram.org/bots/api), [Mini App validation](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app), [aiogram Command](https://docs.aiogram.dev/en/latest/dispatcher/filters/command.html), [polling](https://docs.aiogram.dev/en/latest/dispatcher/long_polling.html), [BaseSession](https://docs.aiogram.dev/en/latest/api/session/base.html), [keyboard builder](https://docs.aiogram.dev/en/latest/_modules/aiogram/utils/keyboard.html), [SQLite authorizer в Python 3.13](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.set_authorizer), [executescript](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.executescript), [SQLite authorizer](https://www.sqlite.org/c3ref/set_authorizer.html). [Фиксированный initData-вектор upstream](https://github.com/aiogram/aiogram/blob/v3.31.0/tests/test_utils/test_web_app.py) используется как независимая fixture. Перечисленные контракты сверены 3 октября 2026 года; фактически установлен aiogram 3.31.0. Живые Telegram данные/платежи не использовались.

В 0.11.0: `telegram-patterns init --list-components`, повторяемый `--component`, preflight conflicts и точный dry-run. Новые core exports: StarterComponent/StarterConflict/starter_components; компоненты подключаются к созданному app/frontend, существующие проекты не перезаписываются.

## Flat клавиатуры 0.14.0

`from telegram_patterns.aiogram import KeyboardLayout, KeyboardCapabilities, action_layout, inline_layout, reply_layout`. Передайте список и `KeyboardLayout([2,3,1], repeat=False)`; default capabilities сохраняет обычный текстовый fallback. `styles=True` и подтверждённый emoji entitlement задаёт host для текущего контекста. Native payload/контекст проверяется до fallback, inputs не меняются. Полные сигнатуры и примеры: [keyboard-layouts](../../docs/keyboard-layouts.md). Прежние builders сохраняются.

## Навигация сообщений 0.15.0


`NavigationScreen`, `NavigationState`, `NavigationResult`, `MessageNavigation` и `navigation_router` импортируются из `telegram_patterns.aiogram`. Экраны/history/back/refresh редактируют одно owner/bot/chat/thread/message-bound сообщение с revision и TTL guards. ACK предшествует lock/edit. Unknown edit блокирует переходы до explicit owner `/menu`; unknown initial send не повторяется автоматически. State одного процесса/event loop, не durable FSM; SDK sessions и tasks принадлежат host. Полный [контракт](../../docs/message-navigation.md), [готовый бот](../../examples/python/navigation_bot.py) и [offline проверка](../../examples/python/offline_navigation.py).

## Составной выбор 0.16.0

Составной выбор 0.16.0: `SelectionOption`, `SelectionSpec`, `SelectionContext`, `SelectionState`, `SelectionResult`, `SelectionMenu` из SDK-free root и `selection_keyboard`/`selection_router` из optional `telegram_patterns.aiogram`. Toggle, multiselect, quantity/filter, server rules и revision-bound confirmation; host владеет бизнес-транзакцией и durable receipt. [Контракт](../../docs/selection-controls.md), [бот](../../examples/python/selection_bot.py), [offline сценарий](../../examples/python/offline_selection.py).

## Безопасные сообщения

`MessageBuilder/FormattedText/TextEntity` и `EntityKind/TextPayload` доступны из SDK-free `telegram_patterns`; там же `utf16_length`, `escape_html`, `escape_markdown_v2`, `split_formatted`. [Контракты и пример](../../docs/message-text.md): literal insertions, explicit parse_mode=None, validated ranges/nesting, lossless split и default regular emoji fallback. Delivery, link trust, sticker metadata и eligibility проверяет проект; full Unicode UAX29 и live rendering не заявлены.

[Профили](../../docs/profiles.md): nullable факты, фотографии и локализованные own-bot изменения с текущими правами; без MTProto/Business login.

[Inline-поиск](../../docs/inline-search.md): shareable articles, scoped pagination и явный cache policy. [Опросы](../../docs/polls.md): modern quiz и собственные scoped observations; durable intent/receipt остается у host.

[Специальные операции](../../docs/platform-operations.md): 51 reviewed native метод по семи семействам; current host ACL, fresh Telegram rights, durable SQLite intent/budget example, scoped observers, managed secrets и story upload bridge. Experimental; реальные права, расход Stars и пригодность медиа проверяются отдельно.

## Диалог после рестарта — 0.24.0

[Atomic FSM snapshot](../../docs/dialog-restart.md) сохраняет шаг, form version, исходный deadline и pending operation ID. `SnapshotFSMStorage` принимает project SnapshotStore; текущий storage может добавить AtomicFSMStorage. `DialogLifetime` включается явно, MemoryStorage остается демонстрацией. Text/mixed формы используют CAS без замены Dispatcher/чужих data. Project SQLite пример и три отдельных процесса показывают восстановление и тот же effect/replay после unknown ответа.
