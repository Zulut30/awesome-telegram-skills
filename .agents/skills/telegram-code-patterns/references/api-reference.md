# Справочник API 0.24.0

Термины: **ACK** — ответ на нажатие кнопки через `answerCallbackQuery`: клиент убирает индикатор ожидания; это не сообщение об успехе операции; **CAS** — сравнение с заменой: запись сохраняется, только если версия не изменилась с момента чтения; квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей; **fallback** — запасной вариант, если основная возможность недоступна.

Публичные imports, самостоятельные минимальные композиции и границы каждого символа. Все группы experimental. Рецепты ref.* принадлежат этому справочнику; cookbook RecipeCatalog отдельно содержит Telegram requests/layouts. Исполненные fixtures не доказывают live/device/provider acceptance.

В index example_sha256 относится к исполняемому fenced-блоку с LF и одной завершающей новой строкой; example_source_sha256 отдельно фиксирует исходные байты файла, включая окончания строк.

Выберите раздел; не подключайте SDK/фреймворк ради core или узкой правки:

- [Python core](api-reference-core.md)
- [Python bot и test transport](api-reference-bot.md)
- [TypeScript Mini App](api-reference-typescript.md)

| Символ | Импорт | Минимальная композиция / рецепт | Назначение |
| --- | --- | --- | --- |
| `BotSettings` | `from telegram_patterns import BotSettings` | [ref.core_identity](api-reference-core.md#ref-core_identity) | Конфигурация из явного environ без dotenv |
| `InvalidInitData` | `from telegram_patterns import InvalidInitData` | [ref.core_identity](api-reference-core.md#ref-core_identity) | Контролируемый отказ подписи/кодировки/freshness |
| `VerifiedLaunch` | `from telegram_patterns import VerifiedLaunch` | [ref.core_identity](api-reference-core.md#ref-core_identity) | Подписанные user_id/auth_date/user |
| `validate_init_data` | `from telegram_patterns import validate_init_data` | [ref.core_identity](api-reference-core.md#ref-core_identity) | HMAC-подпись и свежесть сырой initData |
| `validate_init_data_signature` | `from telegram_patterns import validate_init_data_signature` | [ref.core_identity](api-reference-core.md#ref-core_identity) | Ed25519-подпись initData без токена бота: проверка для третьей стороны |
| `TELEGRAM_PUBLIC_KEYS` | `from telegram_patterns import TELEGRAM_PUBLIC_KEYS` | [ref.core_identity](api-reference-core.md#ref-core_identity) | Опубликованные Telegram ключи Ed25519 для production и test, только чтение |
| `EntityKind` | `from telegram_patterns import EntityKind` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Literal одиннадцати поддерживаемых outgoing entity типов |
| `TextEntity` | `from telegram_patterns import TextEntity` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Frozen range и проверенные metadata |
| `TextPayload` | `from telegram_patterns import TextPayload` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | TypedDict с JSON-полями text, entities и parse_mode=None |
| `FormattedText` | `from telegram_patterns import FormattedText` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Неизменяемый снимок текста; kwargs и разбиение на части |
| `MessageBuilder` | `from telegram_patterns import MessageBuilder` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Пошаговая сборка буквального текста с пересчетом entities |
| `utf16_length` | `from telegram_patterns import utf16_length` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Валидация scalars и подсчет UTF-16 units |
| `escape_html` | `from telegram_patterns import escape_html` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Экранирование буквального текста и атрибутов для HTML |
| `escape_markdown_v2` | `from telegram_patterns import escape_markdown_v2` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Literal escaping в text/code/link контексте |
| `split_formatted` | `from telegram_patterns import split_formatted` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Разбиение без потерь: стили и код обрезаются по границе, ссылки, цитаты и emoji не делятся |
| `RichMessageBuilder` | `from telegram_patterns import RichMessageBuilder` | [ref.core_rich_message](api-reference-core.md#ref-core_rich_message) | Блоки по порядку; вложенное содержимое details берется из другого конструктора |
| `RichMessage` | `from telegram_patterns import RichMessage` | [ref.core_rich_message](api-reference-core.md#ref-core_rich_message) | Готовое сообщение: as_input(), счетчики блоков и медиа, fallback() и fallback_keyboard() |
| `RichButton` | `from telegram_patterns import RichButton` | [ref.core_rich_message](api-reference-core.md#ref-core_rich_message) | Кнопка rich-сообщения: url или callback_data, стиль, link только для callback |
| `RichButtonStyle` | `from telegram_patterns import RichButtonStyle` | [ref.core_rich_message](api-reference-core.md#ref-core_rich_message) | Literal стиля: danger, success, primary, link |
| `RichSpan` | `from telegram_patterns import RichSpan` | [ref.core_rich_message](api-reference-core.md#ref-core_rich_message) | Встроенное форматирование: bold, italic, code или ссылка HTTP(S) |
| `RichText` | `from telegram_patterns import RichText` | [ref.core_rich_message](api-reference-core.md#ref-core_rich_message) | Строка, RichSpan или их последовательность |
| `ephemeral_parameters` | `from telegram_patterns import ephemeral_parameters` | [ref.core_ephemeral](api-reference-core.md#ref-core_ephemeral) | Параметры ephemeral_message_parameters и reply_parameters для send* или отказ с причиной |
| `EphemeralTrigger` | `from telegram_patterns import EphemeralTrigger` | [ref.core_ephemeral](api-reference-core.md#ref-core_ephemeral) | Повод ответа: нажатие кнопки или эфемерная команда и время получения |
| `EphemeralMessageRef` | `from telegram_patterns import EphemeralMessageRef` | [ref.core_ephemeral](api-reference-core.md#ref-core_ephemeral) | Адрес отправленного эфемерного сообщения для editEphemeralMessage* и deleteEphemeralMessage |
| `EphemeralNotAllowed` | `from telegram_patterns import EphemeralNotAllowed` | [ref.core_ephemeral](api-reference-core.md#ref-core_ephemeral) | Отказ: не группа, получатель-бот, окно 15 секунд прошло или замена недоступна |
| `StarsSubscription` | `from telegram_patterns import StarsSubscription` | [ref.core_stars_subscription](api-reference-core.md#ref-core_stars_subscription) | Состояние подписки: record_payment, record_update, record_refund, has_access, access_until, renews, as_dict/from_dict |
| `StarsCharge` | `from telegram_patterns import StarsCharge` | [ref.core_stars_subscription](api-reference-core.md#ref-core_stars_subscription) | Одно списание и оплаченный им период |
| `RenewalState` | `from telegram_patterns import RenewalState` | [ref.core_stars_subscription](api-reference-core.md#ref-core_stars_subscription) | pending, active, canceled или failed |
| `SubscriptionEventRejected` | `from telegram_patterns import SubscriptionEventRejected` | [ref.core_stars_subscription](api-reference-core.md#ref-core_stars_subscription) | Событие чужого пользователя или payload, не XTR, разовая оплата, неизвестное состояние или конфликт charge |
| `STARS_SUBSCRIPTION_PERIOD` | `from telegram_patterns import STARS_SUBSCRIPTION_PERIOD` | [ref.core_stars_subscription](api-reference-core.md#ref-core_stars_subscription) | 2592000 секунд — единственный период подписки, который сейчас принимает Telegram |
| `inline_button` | `from telegram_patterns import inline_button` | [ref.core_markup](api-reference-core.md#ref-core_markup) | Inline-кнопка с ровно одним действием: callback_data, url, web_app, copy_text, switch_inline_query или disabled |
| `reply_button` | `from telegram_patterns import reply_button` | [ref.core_markup](api-reference-core.md#ref-core_markup) | Кнопка reply-клавиатуры: текст или один запрос (контакт, геопозиция, Mini App) |
| `layout_rows` | `from telegram_patterns import layout_rows` | [ref.core_markup](api-reference-core.md#ref-core_markup) | Ряды из плоского списка по ширинам 1–8, как KeyboardLayout |
| `inline_markup` | `from telegram_patterns import inline_markup` | [ref.core_markup](api-reference-core.md#ref-core_markup) | InlineKeyboardMarkup JSON с проверкой контекста чата |
| `reply_markup` | `from telegram_patterns import reply_markup` | [ref.core_markup](api-reference-core.md#ref-core_markup) | ReplyKeyboardMarkup JSON; строки становятся текстовыми кнопками |
| `force_reply_markup` | `from telegram_patterns import force_reply_markup` | [ref.core_markup](api-reference-core.md#ref-core_markup) | ForceReply JSON с подсказкой поля ввода |
| `remove_markup` | `from telegram_patterns import remove_markup` | [ref.core_markup](api-reference-core.md#ref-core_markup) | ReplyKeyboardRemove JSON |
| `paginated_markup` | `from telegram_patterns import paginated_markup` | [ref.core_markup](api-reference-core.md#ref-core_markup) | Страница длинного меню с кнопками «← Назад» и «Далее →», как paginated_menu |
| `MarkupPage` | `from telegram_patterns import MarkupPage` | [ref.core_markup](api-reference-core.md#ref-core_markup) | Результат paginated_markup: markup, page, page_count, total_items |
| `markup_page_number` | `from telegram_patterns import markup_page_number` | [ref.core_markup](api-reference-core.md#ref-core_markup) | Номер страницы из канонического callback или None |
| `selection_markup` | `from telegram_patterns import selection_markup` | [ref.core_markup](api-reference-core.md#ref-core_markup) | Клавиатура SelectionMenu как JSON, как selection_keyboard |
| `OnceResult` | `from telegram_patterns import OnceResult` | [ref.core_storage](api-reference-core.md#ref-core_storage) | Результат эффекта с replay flag |
| `OperationConflict` | `from telegram_patterns import OperationConflict` | [ref.core_storage](api-reference-core.md#ref-core_storage) | Тот же scoped key с другим payload |
| `SQLiteOnce` | `from telegram_patterns import SQLiteOnce` | [ref.core_storage](api-reference-core.md#ref-core_storage) | Инициализация и атомарный run в файле SQLite |
| `OnceStore` | `from telegram_patterns import OnceStore` | [ref.core_storage](api-reference-core.md#ref-core_storage) | Структурный контракт initialize/run storage проекта |
| `PatternError` | `from telegram_patterns import PatternError` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Базовая ошибка с кодом, исходом и отчетом |
| `ValidationFailure` | `from telegram_patterns import ValidationFailure` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Известный локальный отказ validation |
| `InvalidType` | `from telegram_patterns import InvalidType` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Совместимый с TypeError известный локальный отказ |
| `AuthenticationRequired` | `from telegram_patterns import AuthenticationRequired` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Известный отказ до эффекта из-за отсутствия auth |
| `PermissionDenied` | `from telegram_patterns import PermissionDenied` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Известный отказ до эффекта по правам |
| `UnsupportedCapability` | `from telegram_patterns import UnsupportedCapability` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Отсутствующая capability и fallback |
| `ConflictFailure` | `from telegram_patterns import ConflictFailure` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Локальный конфликт операции |
| `TimeoutFailure` | `from telegram_patterns import TimeoutFailure` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Ожидание истекло, outcome зависит от операции |
| `TransportFailure` | `from telegram_patterns import TransportFailure` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Ошибка transport без обещания отмены записи |
| `UnknownOutcome` | `from telegram_patterns import UnknownOutcome` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Эффект пока не подтвержден |
| `InvalidCompletion` | `from telegram_patterns import InvalidCompletion` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Невалидный feedback после возможного эффекта |
| `safe_error_report` | `from telegram_patterns import safe_error_report` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Классификация без raw exception payload |
| `ErrorReport` | `from telegram_patterns import ErrorReport` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Код, категория, исход, способ восстановления и сообщение, только чтение |
| `ErrorCategory` | `from telegram_patterns import ErrorCategory` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Literal категории ошибки |
| `ErrorCode` | `from telegram_patterns import ErrorCode` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Literal известных кодов |
| `ErrorOutcome` | `from telegram_patterns import ErrorOutcome` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Literal-исход: rejected, read-failed или unknown |
| `RecoveryAction` | `from telegram_patterns import RecoveryAction` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Literal следующего действия |
| `OperationKind` | `from telegram_patterns import OperationKind` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Literal read/write |
| `AsyncTransport` | `from telegram_patterns import AsyncTransport` | [ref.core_extensions](api-reference-core.md#ref-core_extensions) | Типизированный async send транспорта host |
| `ProviderAdapter` | `from telegram_patterns import ProviderAdapter` | [ref.core_extensions](api-reference-core.md#ref-core_extensions) | Контракт create/get/verify_event |
| `RefundProvider` | `from telegram_patterns import RefundProvider` | [ref.core_extensions](api-reference-core.md#ref-core_extensions) | Необязательный отдельный refund контракт |
| `Maturity` | `from telegram_patterns import Maturity` | [ref.core_recipes](api-reference-core.md#ref-core_recipes) | Literal-зрелость: stable, experimental или reference |
| `VerificationLevel` | `from telegram_patterns import VerificationLevel` | [ref.core_recipes](api-reference-core.md#ref-core_recipes) | Literal-уровень проверки: sdk, mock, browser, live или not_run |
| `Recipe` | `from telegram_patterns import Recipe` | [ref.core_recipes](api-reference-core.md#ref-core_recipes) | Неизменяемая запись и копия preview |
| `RecipeCatalog` | `from telegram_patterns import RecipeCatalog` | [ref.core_recipes](api-reference-core.md#ref-core_recipes) | Версия, recipes, get/search с фильтрами |
| `RecipeRunPlan` | `from telegram_patterns import RecipeRunPlan` | [ref.core_execution](api-reference-core.md#ref-core_execution) | Неизменяемые требования offline/live и причины недоступности |
| `RecipeRunResult` | `from telegram_patterns import RecipeRunResult` | [ref.core_execution](api-reference-core.md#ref-core_execution) | Результат известной локальной fixture без Telegram requests |
| `plan_recipe` | `from telegram_patterns import plan_recipe` | [ref.core_execution](api-reference-core.md#ref-core_execution) | Read-only план всех cookbook рецептов |
| `run_recipe_offline` | `from telegram_patterns import run_recipe_offline` | [ref.core_execution](api-reference-core.md#ref-core_execution) | Явный изолированный запуск известной Python fixture |
| `StarterPlan` | `from telegram_patterns import StarterPlan` | [ref.core_starter](api-reference-core.md#ref-core_starter) | Target/version/files/created и выбранные группы |
| `StarterComponent` | `from telegram_patterns import StarterComponent` | [ref.core_starter](api-reference-core.md#ref-core_starter) | Описание группы и зависимости/minimum API |
| `StarterConflict` | `from telegram_patterns import StarterConflict` | [ref.core_starter](api-reference-core.md#ref-core_starter) | Безопасная известная preflight причина |
| `starter_components` | `from telegram_patterns import starter_components` | [ref.core_starter](api-reference-core.md#ref-core_starter) | Каталог closed starter групп для шаблона |
| `create_starter` | `from telegram_patterns import create_starter` | [ref.core_starter](api-reference-core.md#ref-core_starter) | Dry-run и исключительное создание нового проекта |
| `doctor` | `from telegram_patterns.cli import doctor` | [ref.core_doctor](api-reference-core.md#ref-core_doctor) | Локальные checks с reason/remediation и exit readiness |
| `ActionButton` | `from telegram_patterns.aiogram import ActionButton` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Описание кнопки: текст, ключ, стиль и custom emoji |
| `ButtonStyle` | `from telegram_patterns.aiogram import ButtonStyle` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Literal-стиль кнопки Telegram |
| `MenuPage` | `from telegram_patterns.aiogram import MenuPage` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Разметка и номер страницы, число страниц и элементов |
| `action_keyboard` | `from telegram_patterns.aiogram import action_keyboard` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Одна callback-кнопка |
| `action_menu` | `from telegram_patterns.aiogram import action_menu` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Равномерные строки по 2/3 и другое число |
| `paginated_menu` | `from telegram_patterns.aiogram import paginated_menu` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Локальная страница с отдельной навигацией |
| `page_number` | `from telegram_patterns.aiogram import page_number` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Безопасный разбор callback страницы |
| `ChatType` | `from telegram_patterns.aiogram import ChatType` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Literal настоящего контекста чата |
| `inline_keyboard` | `from telegram_patterns.aiogram import inline_keyboard` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Явные строки native inline-кнопок |
| `reply_keyboard` | `from telegram_patterns.aiogram import reply_keyboard` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Строки reply-клавиатуры и подсказка в поле ввода |
| `input_prompt` | `from telegram_patterns.aiogram import input_prompt` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | ForceReply для ввода |
| `remove_keyboard` | `from telegram_patterns.aiogram import remove_keyboard` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Снять reply keyboard |
| `KeyboardLayout` | `from telegram_patterns.aiogram import KeyboardLayout` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Неизменяемая раскладка по 2, по 3 или смешанная, с правилом для последней строки |
| `KeyboardCapabilities` | `from telegram_patterns.aiogram import KeyboardCapabilities` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Явный контекст и подсказки оформления; при неизвестном контексте — обычный текст |
| `action_layout` | `from telegram_patterns.aiogram import action_layout` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Уникальные callback-кнопки, разложенные по шаблону ширины |
| `inline_layout` | `from telegram_patterns.aiogram import inline_layout` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Inline-кнопки с проверкой контекста и запасным оформлением |
| `reply_layout` | `from telegram_patterns.aiogram import reply_layout` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Reply-кнопки с проверкой запросов и запасным оформлением |
| `Action` | `from telegram_patterns.aiogram import Action` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Actor/key для авторизованного сервиса |
| `ActionResult` | `from telegram_patterns.aiogram import ActionResult` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Статус и публичный plain ответ сервиса |
| `callback_router` | `from telegram_patterns.aiogram import callback_router` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | ACK до вызова execute и notify |
| `start_router` | `from telegram_patterns.aiogram import start_router` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Небольшой /start без состояния |
| `CommandReply` | `from telegram_patterns.aiogram import CommandReply` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Команда, описание, текст ответа и клавиатура |
| `command_menu` | `from telegram_patterns.aiogram import command_menu` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Native BotCommand list без регистрации |
| `command_router` | `from telegram_patterns.aiogram import command_router` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Обработчики команд с фильтром упоминания бота из SDK |
| `Responder` | `from telegram_patterns.testing import Responder` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Ответ заглушки: значение или синхронная/асинхронная функция |
| `StubSession` | `from telegram_patterns.testing import StubSession` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Явные responses, calls, close без HTTP fallback |
| `create_bot` | `from telegram_patterns.aiogram import create_bot` | [ref.bot_runner](api-reference-bot.md#ref-bot_runner) | Bot из BotSettings; test_environment → /bot<token>/test/<method> |
| `run_bot` | `from telegram_patterns.aiogram import run_bot` | [ref.bot_runner](api-reference-bot.md#ref-bot_runner) | Polling, задачи и сессия бота под управлением библиотеки |
| `stars_invoice` | `from telegram_patterns.aiogram import stars_invoice` | [ref.bot_runner](api-reference-bot.md#ref-bot_runner) | Нативный запрос CreateInvoiceLink в XTR |
| `TextField` | `from telegram_patterns.aiogram import TextField` | [ref.bot_form](api-reference-bot.md#ref-bot_form) | Конфигурация и нормализация/validation read |
| `InvalidField` | `from telegram_patterns.aiogram import InvalidField` | [ref.bot_form](api-reference-bot.md#ref-bot_form) | Bounded plain ошибка пользователя без секретов |
| `FormSubmission` | `from telegram_patterns.aiogram import FormSubmission` | [ref.bot_form](api-reference-bot.md#ref-bot_form) | Личность, полученная на сервере, и копии ответов |
| `text_form_router` | `from telegram_patterns.aiogram import text_form_router` | [ref.bot_form](api-reference-bot.md#ref-bot_form) | Многошаговый FSM с back/cancel/review |
| `UpdatePhase` | `from telegram_patterns.aiogram import UpdatePhase` | [ref.bot_events](api-reference-bot.md#ref-bot_events) | Literal фаз received/handled/unhandled/failed/cancelled |
| `UpdateTrace` | `from telegram_patterns.aiogram import UpdateTrace` | [ref.bot_events](api-reference-bot.md#ref-bot_events) | Неизменяемая metadata события |
| `UpdateObserver` | `from telegram_patterns.aiogram import UpdateObserver` | [ref.bot_events](api-reference-bot.md#ref-bot_events) | Emit и outer middleware наблюдения |
| `update_kinds` | `from telegram_patterns.aiogram import update_kinds` | [ref.bot_events](api-reference-bot.md#ref-bot_events) | Присутствующие native Update kinds |
| `event_router` | `from telegram_patterns.aiogram import event_router` | [ref.bot_events](api-reference-bot.md#ref-bot_events) | Handlers по точным SDK kind names |
| `MethodSpec` | `from telegram_patterns.aiogram import MethodSpec` | [ref.bot_methods](api-reference-bot.md#ref-bot_methods) | Имя, класс, поля, обязательные поля и ссылка на документацию |
| `InvalidAPIRequest` | `from telegram_patterns.aiogram import InvalidAPIRequest` | [ref.bot_methods](api-reference-bot.md#ref-bot_methods) | Контролируемый отказ без SDK payload dump |
| `method_catalog` | `from telegram_patterns.aiogram import method_catalog` | [ref.bot_methods](api-reference-bot.md#ref-bot_methods) | Текущие методы запросов SDK |
| `build_request` | `from telegram_patterns.aiogram import build_request` | [ref.bot_methods](api-reference-bot.md#ref-bot_methods) | Нативный запрос без HTTP |
| `TelegramBridge` | `import {TelegramBridge} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Снимок, подписка, запуск и освобождение моста |
| `TelegramWebApp` | `import type {TelegramWebApp} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Подмножество SDK для моста, только чтение |
| `Insets` | `import type {Insets} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Отступы сверху, справа, снизу и слева, только чтение |
| `BridgeSnapshot` | `import type {BridgeSnapshot} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Неизменяемая theme/geometry metadata |
| `createAppShell` | `import {createAppShell} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Каркас с содержимым, итогом и действиями |
| `AppShell` | `import type {AppShell} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Типизированные слоты каркаса, тема, отступы и освобождение |
| `createTextField` | `import {createTextField} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Связанные label/hint/error без HTML injection |
| `TextFieldControl` | `import type {TextFieldControl} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Типизированные корень, поле и setError |
| `ApiClient` | `import {ApiClient} from "@awesome-telegram/patterns"` | [ref.client](api-reference-typescript.md#ref-client) | Один запрос с проверкой ответа во время выполнения |
| `ApiError` | `import {ApiError} from "@awesome-telegram/patterns"` | [ref.client](api-reference-typescript.md#ref-client) | Вид, статус и исход ошибки без тела ответа |
| `FailureKind` | `import type {FailureKind} from "@awesome-telegram/patterns"` | [ref.client](api-reference-typescript.md#ref-client) | Literal-вид сбоя: HTTP, сеть, таймаут, отмена или ответ |
| `ClientOptions` | `import type {ClientOptions} from "@awesome-telegram/patterns"` | [ref.client](api-reference-typescript.md#ref-client) | Базовый адрес, заголовки и свой транспорт fetch |
| `RequestOptions` | `import type {RequestOptions} from "@awesome-telegram/patterns"` | [ref.client](api-reference-typescript.md#ref-client) | Метод, тело, сигнал отмены и таймаут |
| `FetchTransport` | `import type {FetchTransport} from "@awesome-telegram/patterns"` | [ref.client](api-reference-typescript.md#ref-client) | Типизированный адаптер, совместимый с fetch |
| `SelectionDraftStore` | `import {SelectionDraftStore} from "@awesome-telegram/patterns"` | [ref.draft](api-reference-typescript.md#ref-draft) | Чтение, запись и очистка черновика в своей области и ключ |
| `SelectionDraft` | `import type {SelectionDraft} from "@awesome-telegram/patterns"` | [ref.draft](api-reference-typescript.md#ref-draft) | Идентификаторы выбора, допускающие null, только чтение |
| `DraftRead` | `import type {DraftRead} from "@awesome-telegram/patterns"` | [ref.draft](api-reference-typescript.md#ref-draft) | Статус чтения; значение есть только у restored |
| `DraftOptions` | `import type {DraftOptions} from "@awesome-telegram/patterns"` | [ref.draft](api-reference-typescript.md#ref-draft) | Пространство имен, область, TTL и часы |
| `KeyValueStorage` | `import type {KeyValueStorage} from "@awesome-telegram/patterns"` | [ref.draft](api-reference-typescript.md#ref-draft) | Контракт синхронного хранилища |
| `StorageFactory` | `import type {StorageFactory} from "@awesome-telegram/patterns"` | [ref.draft](api-reference-typescript.md#ref-draft) | Ленивая фабрика своего хранилища |
| `TelegramNativeAPI` | `import {TelegramNativeAPI} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Проверка поддержки, вызов, подписка и освобождение с проверкой версии |
| `UnsupportedTelegramCapability` | `import {UnsupportedTelegramCapability} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Контролируемое отсутствие/disposed native capability |
| `TELEGRAM_NATIVE_METHODS` | `import {TELEGRAM_NATIVE_METHODS} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Каталог путей, минимальных версий и источников, только чтение |
| `TELEGRAM_NATIVE_EVENTS` | `import {TELEGRAM_NATIVE_EVENTS} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Имена нативных событий, только чтение |
| `TELEGRAM_NATIVE_EVENT_DETAILS` | `import {TELEGRAM_NATIVE_EVENT_DETAILS} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Версии и источники событий, только чтение |
| `TelegramNativeMethod` | `import type {TelegramNativeMethod} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Literal известных native paths |
| `TelegramNativeEvent` | `import type {TelegramNativeEvent} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Literal известных event names |
| `PatternError` | `import {PatternError} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Базовая ошибка с кодом, исходом и отчетом |
| `ValidationFailure` | `import {ValidationFailure} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Известная local validation rejection |
| `InvalidType` | `import {InvalidType} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Совместимый с TypeError известный локальный отказ |
| `AuthenticationRequired` | `import {AuthenticationRequired} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Известный auth refusal |
| `PermissionDenied` | `import {PermissionDenied} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Известный permission refusal |
| `UnsupportedCapability` | `import {UnsupportedCapability} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Известная unavailable capability |
| `UnknownOutcome` | `import {UnknownOutcome} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Неподтвержденный effect |
| `safeErrorReport` | `import {safeErrorReport} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Метаданные ошибки по списку разрешенных, без сырого исключения |
| `ErrorReport` | `import type {ErrorReport} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Код, категория, исход, способ восстановления и сообщение, только чтение |
| `ErrorCategory` | `import type {ErrorCategory} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Literal категории ошибки |
| `ErrorCode` | `import type {ErrorCode} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Literal известных кодов |
| `ErrorOutcome` | `import type {ErrorOutcome} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Literal-исход: rejected, read-failed или unknown |
| `OperationKind` | `import type {OperationKind} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Literal read/write |
| `RecoveryAction` | `import type {RecoveryAction} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Literal следующего действия |
| `verifyInitDataSignature` | `import {verifyInitDataSignature} from "@awesome-telegram/patterns"` | [ref.init_data](api-reference-typescript.md#ref-init_data) | Асинхронная проверка подписи Ed25519, свежести и подписанного пользователя |
| `InvalidInitData` | `import {InvalidInitData} from "@awesome-telegram/patterns"` | [ref.init_data](api-reference-typescript.md#ref-init_data) | Контролируемый отказ данных запуска без сырого ввода в сообщении |
| `TELEGRAM_PUBLIC_KEYS` | `import {TELEGRAM_PUBLIC_KEYS} from "@awesome-telegram/patterns"` | [ref.init_data](api-reference-typescript.md#ref-init_data) | Опубликованные ключи Ed25519 в hex: production и test |
| `SignedLaunch` | `import type {SignedLaunch} from "@awesome-telegram/patterns"` | [ref.init_data](api-reference-typescript.md#ref-init_data) | Подписанные userId, authDate, user и необязательные поля запуска, только чтение |
| `SignedObject` | `import type {SignedObject} from "@awesome-telegram/patterns"` | [ref.init_data](api-reference-typescript.md#ref-init_data) | Замороженный JSON-объект из подписанных данных |
| `InitDataSignatureOptions` | `import type {InitDataSignatureOptions} from "@awesome-telegram/patterns"` | [ref.init_data](api-reference-typescript.md#ref-init_data) | Окружение или свой ключ, текущее время, лимиты свежести и размера, WebCrypto |
| `NavigationScreen` | `from telegram_patterns.aiogram import NavigationScreen` | [ref.bot_navigation](api-reference-bot.md#ref-bot_navigation) | Неизменяемый экран с объявленными переходами и раскладкой |
| `NavigationState` | `from telegram_patterns.aiogram import NavigationState` | [ref.bot_navigation](api-reference-bot.md#ref-bot_navigation) | Неизменяемый снимок истории, ревизии и фазы в своей области |
| `NavigationResult` | `from telegram_patterns.aiogram import NavigationResult` | [ref.bot_navigation](api-reference-bot.md#ref-bot_navigation) | Безопасный ответ: принято, отказано, устарело, недоступно или неизвестно |
| `MessageNavigation` | `from telegram_patterns.aiogram import MessageNavigation` | [ref.bot_navigation](api-reference-bot.md#ref-bot_navigation) | Открытие, состояние, обработка и сброс для одного своего сообщения |
| `navigation_router` | `from telegram_patterns.aiogram import navigation_router` | [ref.bot_navigation](api-reference-bot.md#ref-bot_navigation) | Router SDK: сначала ACK, проверки перехода и необязательный ответ |
| `SelectionOption` | `from telegram_patterns import SelectionOption` | [ref.core_selection](api-reference-core.md#ref-core_selection) | Неизменяемый вариант с ключом и принадлежностью к фильтрам |
| `SelectionSpec` | `from telegram_patterns import SelectionSpec` | [ref.core_selection](api-reference-core.md#ref-core_selection) | Текущие значения сервера, границы полей и версия ресурса |
| `SelectionContext` | `from telegram_patterns import SelectionContext` | [ref.core_selection](api-reference-core.md#ref-core_selection) | Владелец, бот, чат, тема и сообщение, определенные приложением |
| `SelectionState` | `from telegram_patterns import SelectionState` | [ref.core_selection](api-reference-core.md#ref-core_selection) | Неизменяемый снимок черновика, итог и ограниченный код callback |
| `SelectionResult` | `from telegram_patterns import SelectionResult` | [ref.core_selection](api-reference-core.md#ref-core_selection) | Решение по выбору после проверок с безопасным ответом |
| `SelectionMenu` | `from telegram_patterns import SelectionMenu` | [ref.core_selection](api-reference-core.md#ref-core_selection) | Атомарный черновик на сервере, обновление правил и одноразовое подтверждение по ревизии |
| `selection_keyboard` | `from telegram_patterns.aiogram import selection_keyboard` | [ref.bot_selection](api-reference-bot.md#ref-bot_selection) | Разметка переключателей, множественного выбора, количества, фильтров и подтверждения с запасным оформлением |
| `selection_router` | `from telegram_patterns.aiogram import selection_router` | [ref.bot_selection](api-reference-bot.md#ref-bot_selection) | Сначала ACK, свежая спецификация с сервера, проверки callback и хуки приложения |
| `CalendarMonth` | `from telegram_patterns import CalendarMonth` | [ref.core_calendar](api-reference-core.md#ref-core_calendar) | Неизменяемый месяц с понедельника, доступные и закрытые даты и краткий итог |
| `TimeSlot` | `from telegram_patterns import TimeSlot` | [ref.core_calendar](api-reference-core.md#ref-core_calendar) | Полуоткрытый интервал UTC и отображение со смещением местного времени |
| `resolve_local_time` | `from telegram_patterns import resolve_local_time` | [ref.core_calendar](api-reference-core.md#ref-core_calendar) | Перевод местного времени в UTC: отказ при пропуске из-за перехода на летнее время и явный выбор при двусмысленности |
| `SlotSchedule` | `from telegram_patterns import SlotSchedule` | [ref.core_calendar](api-reference-core.md#ref-core_calendar) | Неизменяемые ресурс, ревизия и отсортированные слоты с уникальными ключами |
| `SlotBooking` | `from telegram_patterns import SlotBooking` | [ref.core_calendar](api-reference-core.md#ref-core_calendar) | Текущий статус записи владельца и неизменяемое время |
| `SQLiteSlotStore` | `from telegram_patterns import SQLiteSlotStore` | [ref.core_calendar](api-reference-core.md#ref-core_calendar) | Явная схема, CAS расписания, текущие права, атомарные бронь и отмена, повтор |
| `calendar_keyboard` | `from telegram_patterns.aiogram import calendar_keyboard` | [ref.bot_calendar](api-reference-bot.md#ref-bot_calendar) | Только доступные даты или нативная сетка месяца с неактивными днями и явной навигацией |
| `time_slot_keyboard` | `from telegram_patterns.aiogram import time_slot_keyboard` | [ref.bot_calendar](api-reference-bot.md#ref-bot_calendar) | Доступные интервалы UTC со смещением местного времени, нативная раскладка и проверка |
| `FieldValue` | `from telegram_patterns.aiogram import FieldValue` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Строка или плоские метаданные, совместимые с JSON |
| `NumberField` | `from telegram_patterns.aiogram import NumberField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Точное десятичное число в границах, строкой |
| `EmailField` | `from telegram_patterns.aiogram import EmailField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Формат ASCII-адреса почты |
| `PhoneField` | `from telegram_patterns.aiogram import PhoneField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Номер в международном формате |
| `DateField` | `from telegram_patterns.aiogram import DateField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Существующая календарная дата в границах |
| `FileField` | `from telegram_patterns.aiogram import FileField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Ограниченные непрозрачные метаданные документа |
| `ContactField` | `from telegram_patterns.aiogram import ContactField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Свой или явно чужой контакт-кандидат |
| `LocationField` | `from telegram_patterns.aiogram import LocationField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Конечные статичные координаты-кандидат |
| `DialogSubmission` | `from telegram_patterns.aiogram import DialogSubmission` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Неизменяемые личность и ответы; новый as_dict при каждом вызове |
| `dialog_form_router` | `from telegram_patterns.aiogram import dialog_form_router` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Смешанная форма с проверкой владельца и шага, назад, отменой и подтверждением |
| `MediaKind` | `from telegram_patterns.aiogram import MediaKind` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Literal photo/video/audio/document; исходный тип file_id проверяет host |
| `MediaSendRequest` | `from telegram_patterns.aiogram import MediaSendRequest` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Union четырех native send request типов |
| `MediaFile` | `from telegram_patterns.aiogram import MediaFile` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Неизменяемые байты и имя файла или file_id того же бота, границы и новый multipart |
| `MediaItem` | `from telegram_patterns.aiogram import MediaItem` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Неизменяемый типизированный источник, буквальная подпись FormattedText и флаги оформления |
| `DownloadedMedia` | `from telegram_patterns.aiogram import DownloadedMedia` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Ограниченные байты и идентификаторы этого бота без URL и file_path |
| `media_request` | `from telegram_patterns.aiogram import media_request` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Один native send request без отправки |
| `media_album` | `from telegram_patterns.aiogram import media_album` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Один нативный однородный альбом из 2–10 элементов без разбиения на пачки |
| `media_edit` | `from telegram_patterns.aiogram import media_edit` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Замена по чату и сообщению либо по inline-адресу с проверкой типа альбома |
| `download_media` | `from telegram_patterns.aiogram import download_media` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Явное hosted чтение с actual byte bound, total deadline и stream close |
| `ProfileSource` | `from telegram_patterns.aiogram import ProfileSource` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Literal update/getMe — объявленный источник наблюдения, не authorization proof |
| `ProfileAuthorizer` | `from telegram_patterns.aiogram import ProfileAuthorizer` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Async host ACL(actor_id, bot_id, method) → bool; read и точные setMy*/removeMy* имена |
| `UserProfile` | `from telegram_patterns.aiogram import UserProfile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Неизменяемые ID, необязательные текст, Premium и возможности, источник и время наблюдения |
| `ChatProfile` | `from telegram_patterns.aiogram import ChatProfile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Frozen выбранные getChat данные, фото/permissions/birthdate и nullable facts |
| `ProfilePhotoSize` | `from telegram_patterns.aiogram import ProfilePhotoSize` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Frozen bot/user-scoped photo identifiers; as_media только для message reuse |
| `ProfilePhotos` | `from telegram_patterns.aiogram import ProfilePhotos` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Immutable видимая страница, total_count/offset/limit и observation time |
| `BotProfile` | `from telegram_patterns.aiogram import BotProfile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Свежие getMe и локализованные тексты, необязательные фото своего бота; это не атомарный снимок |
| `BotProfilePatch` | `from telegram_patterns.aiogram import BotProfilePatch` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | None omission/empty clear, bounds и новый static JPG/animated MPEG4 upload либо removal |
| `ProfileEditIncomplete` | `from telegram_patterns.aiogram import ProfileEditIncomplete` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | UnknownOutcome с safe confirmed prefix и pending phase; требуется сверка |
| `user_profile` | `from telegram_patterns.aiogram import user_profile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Копирование User без I/O, nullable flags и ownership snapshot |
| `chat_profile` | `from telegram_patterns.aiogram import chat_profile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Копирование selected ChatFullInfo без I/O; default permissions не actor role |
| `read_profile_photos` | `from telegram_patterns.aiogram import read_profile_photos` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Один explicit getUserProfilePhotos, immutable sizes, без отрицательных privacy выводов |
| `read_bot_profile` | `from telegram_patterns.aiogram import read_bot_profile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Свежий getMe и три чтения по локалям; фото своего бота по запросу, иначе None |
| `update_bot_profile` | `from telegram_patterns.aiogram import update_bot_profile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Текущий host ACL перед каждым выбранным own-bot методом и fresh readback; без retry/rollback |
| `InlineChatType` | `from telegram_patterns.aiogram import InlineChatType` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Literal-тип чата inline, включая явный неизвестный None |
| `InlineAuthorizer` | `from telegram_patterns.aiogram import InlineAuthorizer` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Асинхронная проверка текущих прав приложения (пользователь, элемент) → строгий bool |
| `InlineSearchProvider` | `from telegram_patterns.aiogram import InlineSearchProvider` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Асинхронный поставщик свежего неизменяемого каталога |
| `InlineCachePolicy` | `from telegram_patterns.aiogram import InlineCachePolicy` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Явная политика cache_time и is_personal в границах |
| `InlineItem` | `from telegram_patterns.aiogram import InlineItem` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Неизменяемая статья и буквальный текст с entities; по умолчанию shareable=False |
| `InlinePage` | `from telegram_patterns.aiogram import InlinePage` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Неизменяемая страница исходного запроса; answer_request строит один нативный запрос |
| `InlineSearch` | `from telegram_patterns.aiogram import InlineSearch` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Ограниченный неизменяемый снимок поиска с курсором под HMAC и фиксированным сроком цепочки |
| `inline_articles` | `from telegram_patterns.aiogram import inline_articles` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Свежие нативные модели статей с явным parse_mode=None |
| `inline_query_router` | `from telegram_patterns.aiogram import inline_query_router` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Router для Dispatcher приложения: срок поставщика и прав, отказ устаревшим и один нативный ответ |
| `PollKind` | `from telegram_patterns.aiogram import PollKind` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Literal regular/quiz |
| `PollChoice` | `from telegram_patterns.aiogram import PollChoice` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Неизменяемый буквальный вариант и копия rich media SDK |
| `PollSpec` | `from telegram_patterns.aiogram import PollSpec` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Неизменяемые проверенные параметры создания |
| `PollOptionState` | `from telegram_patterns.aiogram import PollOptionState` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Постоянный ID варианта и сырой счетчик голосов |
| `PollState` | `from telegram_patterns.aiogram import PollState` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Неизменяемый снимок Poll с допускающими null ответами и полным JSON |
| `PollVote` | `from telegram_patterns.aiogram import PollVote` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Выбранные постоянные и порядковые ID и точная личность голосующего; пустой выбор — отзыв голоса |
| `PollOptionAddition` | `from telegram_patterns.aiogram import PollOptionAddition` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Служебное событие о новом варианте; связь с опросом может быть неизвестна |
| `PollBinding` | `from telegram_patterns.aiogram import PollBinding` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Привязка бота, опроса, чата, сообщения, темы и Business к подтвержденному ответу своего бота |
| `PollLocator` | `from telegram_patterns.aiogram import PollLocator` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Ключ поиска в приложении или точный адрес, всегда в рамках бота |
| `PollObservation` | `from telegram_patterns.aiogram import PollObservation` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Объединение доступных наблюдений: состояние, голос или вариант |
| `PollEvent` | `from telegram_patterns.aiogram import PollEvent` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | ID update, привязка и одно неизменяемое наблюдение |
| `PollObserver` | `from telegram_patterns.aiogram import PollObserver` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Асинхронный наблюдатель приложения; отвечает за долговечную дедупликацию и состояние |
| `PollLookup` | `from telegram_patterns.aiogram import PollLookup` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Асинхронный поиск текущей привязки без скрытой авторизации |
| `poll_request` | `from telegram_patterns.aiogram import poll_request` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Один нативный запрос SendPoll: буквальные entities, современные поля, без ввода-вывода |
| `poll_state` | `from telegram_patterns.aiogram import poll_state` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Копия нативного Poll без вычисления счетчиков |
| `poll_vote` | `from telegram_patterns.aiogram import poll_vote` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Копия нативного PollAnswer без выдуманной личности |
| `poll_option_added` | `from telegram_patterns.aiogram import poll_option_added` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Копия Message.poll_option_added, включая недоступный или пропущенный адрес |
| `poll_events_router` | `from telegram_patterns.aiogram import poll_events_router` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Маршрутизация Poll, PollAnswer, message и business_message; без подсчета, повторов и getPoll |
| `PlatformContract` | `from telegram_patterns.aiogram import PlatformContract` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Frozen native метод/семейство/right/version/source/evidence |
| `PlatformScope` | `from telegram_patterns.aiogram import PlatformScope` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Неизменяемые бот, пользователь, намерение и ревизия на сервере и точные привязки чата, темы, владельца и дочернего бота |
| `PlatformPermit` | `from telegram_patterns.aiogram import PlatformPermit` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Текущие host policy facts, consent/quote и дополнительные права |
| `PlatformAction` | `from telegram_patterns.aiogram import PlatformAction` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Копия exact native request, проверка scope/params и immutable fingerprint |
| `PlatformReceipt` | `from telegram_patterns.aiogram import PlatformReceipt` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Безопасный method/outcome/result ID для прежнего intent |
| `PlatformResult` | `from telegram_patterns.aiogram import PlatformResult` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Квитанция и нативный результат; данные скрыты в repr |
| `PlatformHooks` | `from telegram_patterns.aiogram import PlatformHooks` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Асинхронный контракт приложения: авторизация, атомарная заявка и долговечная запись |
| `SecretToken` | `from telegram_patterns.aiogram import SecretToken` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Repr-hidden managed token с явным reveal для secret store |
| `PlatformEvent` | `from telegram_patterns.aiogram import PlatformEvent` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Неизменяемые факты нативного Update и сохраненный сырой JSON; данные скрыты в repr |
| `PlatformLookup` | `from telegram_patterns.aiogram import PlatformLookup` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Асинхронно возвращает текущую привязку из хранилища проекта по событию |
| `PlatformObserver` | `from telegram_patterns.aiogram import PlatformObserver` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Асинхронный наблюдатель приложения; отвечает за дедупликацию, порядок и отзыв |
| `platform_contracts` | `from telegram_patterns.aiogram import platform_contracts` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | 51 разрешенный native метод с current method-specific rights и SDK sources |
| `execute_platform_action` | `from telegram_patterns.aiogram import execute_platform_action` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Авторизация, свежие права, одна заявка, один вызов SDK и квитанция без автоматического повтора |
| `managed_bot_link` | `from telegram_patterns.aiogram import managed_bot_link` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Native user-confirmed создание; без I/O или получения token |
| `platform_event` | `from telegram_patterns.aiogram import platform_event` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Копирование native facts без guessed identity/history |
| `platform_events_router` | `from telegram_patterns.aiogram import platform_events_router` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Observers для разрешенных native events в текущем Dispatcher |
| `StoryPhotoUpload` | `from telegram_patterns.aiogram import StoryPhotoUpload` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Проверенный новый InputFile фото для вложенного multipart SDK |
| `StoryVideoUpload` | `from telegram_patterns.aiogram import StoryVideoUpload` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Проверенный новый InputFile видео с длительностью для вложенного multipart SDK |
| `FSMSnapshot` | `from telegram_patterns.aiogram import FSMSnapshot` | [ref.bot_fsm_storage](api-reference-bot.md#ref-bot_fsm_storage) | Неизменяемая ревизия и отдельная копия ответов в JSON |
| `FSMConflict` | `from telegram_patterns.aiogram import FSMConflict` | [ref.bot_fsm_storage](api-reference-bot.md#ref-bot_fsm_storage) | Устаревшая запись CAS отклонена до эффектов |
| `SnapshotStore` | `from telegram_patterns.aiogram import SnapshotStore` | [ref.bot_fsm_storage](api-reference-bot.md#ref-bot_fsm_storage) | Контракт долговечной транзакции снимка в хранилище приложения |
| `AtomicFSMStorage` | `from telegram_patterns.aiogram import AtomicFSMStorage` | [ref.bot_fsm_storage](api-reference-bot.md#ref-bot_fsm_storage) | Необязательная атомарная возможность текущего хранилища проекта |
| `SnapshotFSMStorage` | `from telegram_patterns.aiogram import SnapshotFSMStorage` | [ref.bot_fsm_storage](api-reference-bot.md#ref-bot_fsm_storage) | Фасад aiogram BaseStorage над хранилищем приложения |
| `DialogLifetime` | `from telegram_patterns.aiogram import DialogLifetime` | [ref.bot_fsm_storage](api-reference-bot.md#ref-bot_fsm_storage) | Абсолютный срок черновика, при котором ожидающие эффекты не истекают |
| `ptb_markup` | `from telegram_patterns.ptb import ptb_markup` | [ref.ptb_adapter](api-reference-bot.md#ref-ptb_adapter) | Объект PTB для reply_markup JSON: inline, reply, remove или force reply |
| `ptb_inline_markup` | `from telegram_patterns.ptb import ptb_inline_markup` | [ref.ptb_adapter](api-reference-bot.md#ref-ptb_adapter) | InlineKeyboardMarkup для правок сообщения |
| `ptb_text` | `from telegram_patterns.ptb import ptb_text` | [ref.ptb_adapter](api-reference-bot.md#ref-ptb_adapter) | text, entities и parse_mode=None из FormattedText для send_message |
| `StubRequest` | `from telegram_patterns.ptb import StubRequest` | [ref.ptb_adapter](api-reference-bot.md#ref-ptb_adapter) | Офлайн-транспорт PTB: ответы по методам, ошибки Telegram, журнал вызовов |
| `offline_application` | `from telegram_patterns.ptb import offline_application` | [ref.ptb_adapter](api-reference-bot.md#ref-ptb_adapter) | Application без updater поверх StubRequest, с Defaults проекта |

## CLI и CSS

`python -m telegram_patterns recipes "две кнопки"` читает cookbook, не исполняет код. `python -m telegram_patterns init "<NEW_PATH>" --library "<PROVIDED_WHEEL>" --dry-run` показывает все файлы; без dry-run создает новый каталог. `python -m telegram_patterns doctor "<PROJECT>"` делает local diagnosis без repairs/HTTP. `python -m telegram_patterns run-recipe demo-recovery` показывает requirements; явный `--offline` запускает закрытый installed fixture без токена. Native references требуют host/аргументов. Изменение существующего проекта и live запуск — отдельные действия. Commands/exit codes проверяются installed CLI.

CSS entry: `@awesome-telegram/patterns/styles.css`. В bundler: `import "@awesome-telegram/patterns/styles.css";`; в browser consumer подключите link к скопированному CSS из resolved subpath. CSS не создает UI и не заменяет host state. Import resolution и настоящий browser stylesheet проверяются отдельно.

Type-only TypeScript exports существуют в declarations, без runtime JavaScript binding. Imports типов используют `type`. Python Literal/Protocol annotations проверяются Mypy; это не runtime validation внешнего JSON.
