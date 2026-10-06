# Справочник API 0.24.0

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
| `validate_init_data` | `from telegram_patterns import validate_init_data` | [ref.core_identity](api-reference-core.md#ref-core_identity) | HMAC и freshness raw initData |
| `EntityKind` | `from telegram_patterns import EntityKind` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Literal одиннадцати поддерживаемых outgoing entity типов |
| `TextEntity` | `from telegram_patterns import TextEntity` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Frozen range и проверенные metadata |
| `TextPayload` | `from telegram_patterns import TextPayload` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | TypedDict JSON text/entities/parse_mode=None |
| `FormattedText` | `from telegram_patterns import FormattedText` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Immutable snapshot и kwargs/split |
| `MessageBuilder` | `from telegram_patterns import MessageBuilder` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Immutable fluent literal composition и rebased entities |
| `utf16_length` | `from telegram_patterns import utf16_length` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Валидация scalars и подсчет UTF-16 units |
| `escape_html` | `from telegram_patterns import escape_html` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Literal HTML text/attribute escaping |
| `escape_markdown_v2` | `from telegram_patterns import escape_markdown_v2` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Literal escaping в text/code/link контексте |
| `split_formatted` | `from telegram_patterns import split_formatted` | [ref.core_message_text](api-reference-core.md#ref-core_message_text) | Lossless partition, clipping styles/code и atomic links/quotes/emoji |
| `OnceResult` | `from telegram_patterns import OnceResult` | [ref.core_storage](api-reference-core.md#ref-core_storage) | Результат эффекта с replay flag |
| `OperationConflict` | `from telegram_patterns import OperationConflict` | [ref.core_storage](api-reference-core.md#ref-core_storage) | Тот же scoped key с другим payload |
| `SQLiteOnce` | `from telegram_patterns import SQLiteOnce` | [ref.core_storage](api-reference-core.md#ref-core_storage) | Инициализация и атомарный run в файле SQLite |
| `OnceStore` | `from telegram_patterns import OnceStore` | [ref.core_storage](api-reference-core.md#ref-core_storage) | Структурный контракт initialize/run storage проекта |
| `PatternError` | `from telegram_patterns import PatternError` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Базовое исключение с безопасным report |
| `ValidationFailure` | `from telegram_patterns import ValidationFailure` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Известный локальный отказ validation |
| `InvalidType` | `from telegram_patterns import InvalidType` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Локальный type отказ, совместимый с TypeError |
| `AuthenticationRequired` | `from telegram_patterns import AuthenticationRequired` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Известный отказ до эффекта из-за отсутствия auth |
| `PermissionDenied` | `from telegram_patterns import PermissionDenied` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Известный отказ до эффекта по правам |
| `UnsupportedCapability` | `from telegram_patterns import UnsupportedCapability` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Отсутствующая capability и fallback |
| `ConflictFailure` | `from telegram_patterns import ConflictFailure` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Локальный конфликт операции |
| `TimeoutFailure` | `from telegram_patterns import TimeoutFailure` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Ожидание истекло, outcome зависит от операции |
| `TransportFailure` | `from telegram_patterns import TransportFailure` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Ошибка transport без обещания отмены записи |
| `UnknownOutcome` | `from telegram_patterns import UnknownOutcome` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Эффект пока не подтвержден |
| `InvalidCompletion` | `from telegram_patterns import InvalidCompletion` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Невалидный feedback после возможного эффекта |
| `safe_error_report` | `from telegram_patterns import safe_error_report` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Классификация без raw exception payload |
| `ErrorReport` | `from telegram_patterns import ErrorReport` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Неизменяемые code/category/outcome/recovery/message |
| `ErrorCategory` | `from telegram_patterns import ErrorCategory` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Literal категории ошибки |
| `ErrorCode` | `from telegram_patterns import ErrorCode` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Literal известных кодов |
| `ErrorOutcome` | `from telegram_patterns import ErrorOutcome` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Literal rejected/read-failed/unknown |
| `RecoveryAction` | `from telegram_patterns import RecoveryAction` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Literal следующего действия |
| `OperationKind` | `from telegram_patterns import OperationKind` | [ref.core_errors](api-reference-core.md#ref-core_errors) | Literal read/write для реальной операции |
| `AsyncTransport` | `from telegram_patterns import AsyncTransport` | [ref.core_extensions](api-reference-core.md#ref-core_extensions) | Типизированный async send транспорта host |
| `ProviderAdapter` | `from telegram_patterns import ProviderAdapter` | [ref.core_extensions](api-reference-core.md#ref-core_extensions) | Контракт create/get/verify_event |
| `RefundProvider` | `from telegram_patterns import RefundProvider` | [ref.core_extensions](api-reference-core.md#ref-core_extensions) | Необязательный отдельный refund контракт |
| `Maturity` | `from telegram_patterns import Maturity` | [ref.core_recipes](api-reference-core.md#ref-core_recipes) | Literal stable/experimental/reference |
| `VerificationLevel` | `from telegram_patterns import VerificationLevel` | [ref.core_recipes](api-reference-core.md#ref-core_recipes) | Literal sdk/mock/browser/live/not_run |
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
| `ActionButton` | `from telegram_patterns.aiogram import ActionButton` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Label/key/style/custom emoji descriptor |
| `ButtonStyle` | `from telegram_patterns.aiogram import ButtonStyle` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Literal Telegram button style |
| `MenuPage` | `from telegram_patterns.aiogram import MenuPage` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Markup и page/page_count/total_items |
| `action_keyboard` | `from telegram_patterns.aiogram import action_keyboard` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Одна callback-кнопка |
| `action_menu` | `from telegram_patterns.aiogram import action_menu` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Равномерные строки по 2/3 и другое число |
| `paginated_menu` | `from telegram_patterns.aiogram import paginated_menu` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Локальная страница с отдельной навигацией |
| `page_number` | `from telegram_patterns.aiogram import page_number` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Безопасный разбор callback страницы |
| `ChatType` | `from telegram_patterns.aiogram import ChatType` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Literal настоящего контекста чата |
| `inline_keyboard` | `from telegram_patterns.aiogram import inline_keyboard` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Явные строки native inline-кнопок |
| `reply_keyboard` | `from telegram_patterns.aiogram import reply_keyboard` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Reply rows/input placeholder |
| `input_prompt` | `from telegram_patterns.aiogram import input_prompt` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | ForceReply для ввода |
| `remove_keyboard` | `from telegram_patterns.aiogram import remove_keyboard` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Снять reply keyboard |
| `KeyboardLayout` | `from telegram_patterns.aiogram import KeyboardLayout` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Immutable 2/3/mixed width pattern with last/cycle tail |
| `KeyboardCapabilities` | `from telegram_patterns.aiogram import KeyboardCapabilities` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Explicit context and presentation hints; unknown uses standard text fallback |
| `action_layout` | `from telegram_patterns.aiogram import action_layout` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Unique callback descriptors composed by width pattern |
| `inline_layout` | `from telegram_patterns.aiogram import inline_layout` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Flat native inline buttons with context checks and fallback |
| `reply_layout` | `from telegram_patterns.aiogram import reply_layout` | [ref.bot_keyboards](api-reference-bot.md#ref-bot_keyboards) | Flat reply buttons with request validation and fallback |
| `Action` | `from telegram_patterns.aiogram import Action` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Actor/key для авторизованного сервиса |
| `ActionResult` | `from telegram_patterns.aiogram import ActionResult` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Статус и публичный plain ответ сервиса |
| `callback_router` | `from telegram_patterns.aiogram import callback_router` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | ACK перед execute и notify |
| `start_router` | `from telegram_patterns.aiogram import start_router` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Небольшой /start без состояния |
| `CommandReply` | `from telegram_patterns.aiogram import CommandReply` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Command/description/plain text/keyboard |
| `command_menu` | `from telegram_patterns.aiogram import command_menu` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Native BotCommand list без регистрации |
| `command_router` | `from telegram_patterns.aiogram import command_router` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Reply handlers с SDK mention filtering |
| `Responder` | `from telegram_patterns.testing import Responder` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Typed fixture value или sync/async callable |
| `StubSession` | `from telegram_patterns.testing import StubSession` | [ref.bot_actions](api-reference-bot.md#ref-bot_actions) | Явные responses, calls, close без HTTP fallback |
| `run_bot` | `from telegram_patterns.aiogram import run_bot` | [ref.bot_runner](api-reference-bot.md#ref-bot_runner) | Owned polling/task/session lifecycle |
| `stars_invoice` | `from telegram_patterns.aiogram import stars_invoice` | [ref.bot_runner](api-reference-bot.md#ref-bot_runner) | Native XTR CreateInvoiceLink request |
| `TextField` | `from telegram_patterns.aiogram import TextField` | [ref.bot_form](api-reference-bot.md#ref-bot_form) | Конфигурация и нормализация/validation read |
| `InvalidField` | `from telegram_patterns.aiogram import InvalidField` | [ref.bot_form](api-reference-bot.md#ref-bot_form) | Bounded plain ошибка пользователя без секретов |
| `FormSubmission` | `from telegram_patterns.aiogram import FormSubmission` | [ref.bot_form](api-reference-bot.md#ref-bot_form) | Server-derived identity и copied values |
| `text_form_router` | `from telegram_patterns.aiogram import text_form_router` | [ref.bot_form](api-reference-bot.md#ref-bot_form) | Многошаговый FSM с back/cancel/review |
| `UpdatePhase` | `from telegram_patterns.aiogram import UpdatePhase` | [ref.bot_events](api-reference-bot.md#ref-bot_events) | Literal фаз received/handled/unhandled/failed/cancelled |
| `UpdateTrace` | `from telegram_patterns.aiogram import UpdateTrace` | [ref.bot_events](api-reference-bot.md#ref-bot_events) | Неизменяемая metadata события |
| `UpdateObserver` | `from telegram_patterns.aiogram import UpdateObserver` | [ref.bot_events](api-reference-bot.md#ref-bot_events) | Emit и outer middleware наблюдения |
| `update_kinds` | `from telegram_patterns.aiogram import update_kinds` | [ref.bot_events](api-reference-bot.md#ref-bot_events) | Присутствующие native Update kinds |
| `event_router` | `from telegram_patterns.aiogram import event_router` | [ref.bot_events](api-reference-bot.md#ref-bot_events) | Handlers по точным SDK kind names |
| `MethodSpec` | `from telegram_patterns.aiogram import MethodSpec` | [ref.bot_methods](api-reference-bot.md#ref-bot_methods) | Name/class/fields/required/official URL |
| `InvalidAPIRequest` | `from telegram_patterns.aiogram import InvalidAPIRequest` | [ref.bot_methods](api-reference-bot.md#ref-bot_methods) | Контролируемый отказ без SDK payload dump |
| `method_catalog` | `from telegram_patterns.aiogram import method_catalog` | [ref.bot_methods](api-reference-bot.md#ref-bot_methods) | Текущие SDK request methods |
| `build_request` | `from telegram_patterns.aiogram import build_request` | [ref.bot_methods](api-reference-bot.md#ref-bot_methods) | Native request без HTTP |
| `TelegramBridge` | `import {TelegramBridge} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Snapshot/subscribe/start/dispose lifecycle |
| `TelegramWebApp` | `import type {TelegramWebApp} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Readonly subset SDK для bridge |
| `Insets` | `import type {Insets} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Readonly top/right/bottom/left coordinates |
| `BridgeSnapshot` | `import type {BridgeSnapshot} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Неизменяемая theme/geometry metadata |
| `createAppShell` | `import {createAppShell} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Owned content/summary/actions composition |
| `AppShell` | `import type {AppShell} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Typed shell slots/theme/insets/dispose |
| `createTextField` | `import {createTextField} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Связанные label/hint/error без HTML injection |
| `TextFieldControl` | `import type {TextFieldControl} from "@awesome-telegram/patterns"` | [ref.bridge](api-reference-typescript.md#ref-bridge) | Typed root/input/setError |
| `ApiClient` | `import {ApiClient} from "@awesome-telegram/patterns"` | [ref.client](api-reference-typescript.md#ref-client) | Один request с runtime decoder |
| `ApiError` | `import {ApiError} from "@awesome-telegram/patterns"` | [ref.client](api-reference-typescript.md#ref-client) | Kind/status/outcome без response body |
| `FailureKind` | `import type {FailureKind} from "@awesome-telegram/patterns"` | [ref.client](api-reference-typescript.md#ref-client) | Literal HTTP/network/timeout/abort/response failure |
| `ClientOptions` | `import type {ClientOptions} from "@awesome-telegram/patterns"` | [ref.client](api-reference-typescript.md#ref-client) | Base/headers/owned fetch transport |
| `RequestOptions` | `import type {RequestOptions} from "@awesome-telegram/patterns"` | [ref.client](api-reference-typescript.md#ref-client) | Method/body/signal/timeout options |
| `FetchTransport` | `import type {FetchTransport} from "@awesome-telegram/patterns"` | [ref.client](api-reference-typescript.md#ref-client) | Typed Fetch-compatible adapter host |
| `SelectionDraftStore` | `import {SelectionDraftStore} from "@awesome-telegram/patterns"` | [ref.draft](api-reference-typescript.md#ref-draft) | Scoped read/write/clear и key |
| `SelectionDraft` | `import type {SelectionDraft} from "@awesome-telegram/patterns"` | [ref.draft](api-reference-typescript.md#ref-draft) | Readonly nullable identifiers |
| `DraftRead` | `import type {DraftRead} from "@awesome-telegram/patterns"` | [ref.draft](api-reference-typescript.md#ref-draft) | Discriminated status с value только restored |
| `DraftOptions` | `import type {DraftOptions} from "@awesome-telegram/patterns"` | [ref.draft](api-reference-typescript.md#ref-draft) | Namespace/scope/TTL/clock |
| `KeyValueStorage` | `import type {KeyValueStorage} from "@awesome-telegram/patterns"` | [ref.draft](api-reference-typescript.md#ref-draft) | Sync storage contract |
| `StorageFactory` | `import type {StorageFactory} from "@awesome-telegram/patterns"` | [ref.draft](api-reference-typescript.md#ref-draft) | Lazy owned storage factory |
| `TelegramNativeAPI` | `import {TelegramNativeAPI} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Supports/call/listen/dispose с gates |
| `UnsupportedTelegramCapability` | `import {UnsupportedTelegramCapability} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Контролируемое отсутствие/disposed native capability |
| `TELEGRAM_NATIVE_METHODS` | `import {TELEGRAM_NATIVE_METHODS} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Readonly path/minVersion/source catalog |
| `TELEGRAM_NATIVE_EVENTS` | `import {TELEGRAM_NATIVE_EVENTS} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Readonly имена native events |
| `TELEGRAM_NATIVE_EVENT_DETAILS` | `import {TELEGRAM_NATIVE_EVENT_DETAILS} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Readonly event version/source metadata |
| `TelegramNativeMethod` | `import type {TelegramNativeMethod} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Literal известных native paths |
| `TelegramNativeEvent` | `import type {TelegramNativeEvent} from "@awesome-telegram/patterns"` | [ref.native](api-reference-typescript.md#ref-native) | Literal известных event names |
| `PatternError` | `import {PatternError} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Base code/outcome с report |
| `ValidationFailure` | `import {ValidationFailure} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Известная local validation rejection |
| `InvalidType` | `import {InvalidType} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | TypeError-compatible known local rejection |
| `AuthenticationRequired` | `import {AuthenticationRequired} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Известный auth refusal |
| `PermissionDenied` | `import {PermissionDenied} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Известный permission refusal |
| `UnsupportedCapability` | `import {UnsupportedCapability} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Известная unavailable capability |
| `UnknownOutcome` | `import {UnknownOutcome} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Неподтвержденный effect |
| `safeErrorReport` | `import {safeErrorReport} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Allowlisted error metadata без raw exception |
| `ErrorReport` | `import type {ErrorReport} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Readonly code/category/outcome/recovery/message |
| `ErrorCategory` | `import type {ErrorCategory} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Literal категории ошибки |
| `ErrorCode` | `import type {ErrorCode} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Literal известных кодов |
| `ErrorOutcome` | `import type {ErrorOutcome} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Literal outcome |
| `OperationKind` | `import type {OperationKind} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Literal read/write |
| `RecoveryAction` | `import type {RecoveryAction} from "@awesome-telegram/patterns"` | [ref.errors](api-reference-typescript.md#ref-errors) | Literal следующего действия |
| `NavigationScreen` | `from telegram_patterns.aiogram import NavigationScreen` | [ref.bot_navigation](api-reference-bot.md#ref-bot_navigation) | Immutable plain screen with declared links/layout |
| `NavigationState` | `from telegram_patterns.aiogram import NavigationState` | [ref.bot_navigation](api-reference-bot.md#ref-bot_navigation) | Frozen scoped history/revision/phase snapshot |
| `NavigationResult` | `from telegram_patterns.aiogram import NavigationResult` | [ref.bot_navigation](api-reference-bot.md#ref-bot_navigation) | Safe accepted/denied/stale/unavailable/unknown feedback |
| `MessageNavigation` | `from telegram_patterns.aiogram import MessageNavigation` | [ref.bot_navigation](api-reference-bot.md#ref-bot_navigation) | Bounded open/get_state/handle/discard lifecycle for one owned message |
| `navigation_router` | `from telegram_patterns.aiogram import navigation_router` | [ref.bot_navigation](api-reference-bot.md#ref-bot_navigation) | SDK Router with ACK-first guarded navigation and optional feedback |
| `SelectionOption` | `from telegram_patterns import SelectionOption` | [ref.core_selection](api-reference-core.md#ref-core_selection) | Immutable keyed option and filter membership |
| `SelectionSpec` | `from telegram_patterns import SelectionSpec` | [ref.core_selection](api-reference-core.md#ref-core_selection) | Current server values, field bounds and resource version |
| `SelectionContext` | `from telegram_patterns import SelectionContext` | [ref.core_selection](api-reference-core.md#ref-core_selection) | Host-derived owner/bot/chat/thread/message identity |
| `SelectionState` | `from telegram_patterns import SelectionState` | [ref.core_selection](api-reference-core.md#ref-core_selection) | Immutable draft snapshot, summary and bounded callback code |
| `SelectionResult` | `from telegram_patterns import SelectionResult` | [ref.core_selection](api-reference-core.md#ref-core_selection) | Guarded selection decision with safe feedback |
| `SelectionMenu` | `from telegram_patterns import SelectionMenu` | [ref.core_selection](api-reference-core.md#ref-core_selection) | Atomic server draft, rule refresh and revision-bound one-time confirmation |
| `selection_keyboard` | `from telegram_patterns.aiogram import selection_keyboard` | [ref.bot_selection](api-reference-bot.md#ref-bot_selection) | Render toggle/multiselect/quantity/filter and confirmation markup with capability fallback |
| `selection_router` | `from telegram_patterns.aiogram import selection_router` | [ref.bot_selection](api-reference-bot.md#ref-bot_selection) | ACK-first composition with fresh server spec, safe callback guards and host-owned hooks |
| `CalendarMonth` | `from telegram_patterns import CalendarMonth` | [ref.core_calendar](api-reference-core.md#ref-core_calendar) | Immutable Monday-first month, available/blocked dates and plain summary |
| `TimeSlot` | `from telegram_patterns import TimeSlot` | [ref.core_calendar](api-reference-core.md#ref-core_calendar) | Half-open UTC interval and local offset display |
| `resolve_local_time` | `from telegram_patterns import resolve_local_time` | [ref.core_calendar](api-reference-core.md#ref-core_calendar) | Naive wall time to UTC, DST gap rejection and explicit ambiguous fold |
| `SlotSchedule` | `from telegram_patterns import SlotSchedule` | [ref.core_calendar](api-reference-core.md#ref-core_calendar) | Immutable resource/revision/sorted uniquely keyed slots |
| `SlotBooking` | `from telegram_patterns import SlotBooking` | [ref.core_calendar](api-reference-core.md#ref-core_calendar) | Current owner-bound booking status and immutable times |
| `SQLiteSlotStore` | `from telegram_patterns import SQLiteSlotStore` | [ref.core_calendar](api-reference-core.md#ref-core_calendar) | Explicit schema, schedule CAS, current ACL, atomic reserve/cancel and replay |
| `calendar_keyboard` | `from telegram_patterns.aiogram import calendar_keyboard` | [ref.bot_calendar](api-reference-bot.md#ref-bot_calendar) | Available-date fallback or native disabled month grid with explicit navigation |
| `time_slot_keyboard` | `from telegram_patterns.aiogram import time_slot_keyboard` | [ref.bot_calendar](api-reference-bot.md#ref-bot_calendar) | Enabled UTC intervals displayed with local offset, native layout/validation |
| `FieldValue` | `from telegram_patterns.aiogram import FieldValue` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | JSON-compatible string or flat metadata |
| `NumberField` | `from telegram_patterns.aiogram import NumberField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Exact bounded decimal string |
| `EmailField` | `from telegram_patterns.aiogram import EmailField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | ASCII mailbox format |
| `PhoneField` | `from telegram_patterns.aiogram import PhoneField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Explicit international number |
| `DateField` | `from telegram_patterns.aiogram import DateField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Existing calendar date with bounds |
| `FileField` | `from telegram_patterns.aiogram import FileField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Bounded opaque document metadata |
| `ContactField` | `from telegram_patterns.aiogram import ContactField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Own or explicitly third-party contact candidate |
| `LocationField` | `from telegram_patterns.aiogram import LocationField` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Finite static coordinate candidate |
| `DialogSubmission` | `from telegram_patterns.aiogram import DialogSubmission` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Immutable identity and values; fresh as_dict |
| `dialog_form_router` | `from telegram_patterns.aiogram import dialog_form_router` | [ref.bot_dialog_fields](api-reference-bot.md#ref-bot_dialog_fields) | Mixed router with owner/step guards, back/cancel and confirmation |
| `MediaKind` | `from telegram_patterns.aiogram import MediaKind` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Literal photo/video/audio/document; исходный тип file_id проверяет host |
| `MediaSendRequest` | `from telegram_patterns.aiogram import MediaSendRequest` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Union четырех native send request типов |
| `MediaFile` | `from telegram_patterns.aiogram import MediaFile` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Immutable bytes/filename или same-bot file_id, bounds и fresh multipart input |
| `MediaItem` | `from telegram_patterns.aiogram import MediaItem` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Immutable typed source, literal FormattedText caption и presentation flags |
| `DownloadedMedia` | `from telegram_patterns.aiogram import DownloadedMedia` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Frozen bounded bytes и bot-scoped identifiers без URL/file_path |
| `media_request` | `from telegram_patterns.aiogram import media_request` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Один native send request без отправки |
| `media_album` | `from telegram_patterns.aiogram import media_album` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Один native 2..10-item homogeneous/visual album без batching |
| `media_edit` | `from telegram_patterns.aiogram import media_edit` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Exclusive chat/message или inline address и album type guard |
| `download_media` | `from telegram_patterns.aiogram import download_media` | [ref.bot_media](api-reference-bot.md#ref-bot_media) | Явное hosted чтение с actual byte bound, total deadline и stream close |
| `ProfileSource` | `from telegram_patterns.aiogram import ProfileSource` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Literal update/getMe — объявленный источник наблюдения, не authorization proof |
| `ProfileAuthorizer` | `from telegram_patterns.aiogram import ProfileAuthorizer` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Async host ACL(actor_id, bot_id, method) → bool; read и точные setMy*/removeMy* имена |
| `UserProfile` | `from telegram_patterns.aiogram import UserProfile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Frozen numeric identity, optional text/Premium/capabilities и aware source observation |
| `ChatProfile` | `from telegram_patterns.aiogram import ChatProfile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Frozen выбранные getChat данные, фото/permissions/birthdate и nullable facts |
| `ProfilePhotoSize` | `from telegram_patterns.aiogram import ProfilePhotoSize` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Frozen bot/user-scoped photo identifiers; as_media только для message reuse |
| `ProfilePhotos` | `from telegram_patterns.aiogram import ProfilePhotos` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Immutable видимая страница, total_count/offset/limit и observation time |
| `BotProfile` | `from telegram_patterns.aiogram import BotProfile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Fresh getMe/localized texts, optional own-bot ProfilePhotos; не atomic snapshot |
| `BotProfilePatch` | `from telegram_patterns.aiogram import BotProfilePatch` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | None omission/empty clear, bounds и новый static JPG/animated MPEG4 upload либо removal |
| `ProfileEditIncomplete` | `from telegram_patterns.aiogram import ProfileEditIncomplete` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | UnknownOutcome с safe confirmed prefix и pending phase; требуется сверка |
| `user_profile` | `from telegram_patterns.aiogram import user_profile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Копирование User без I/O, nullable flags и ownership snapshot |
| `chat_profile` | `from telegram_patterns.aiogram import chat_profile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Копирование selected ChatFullInfo без I/O; default permissions не actor role |
| `read_profile_photos` | `from telegram_patterns.aiogram import read_profile_photos` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Один explicit getUserProfilePhotos, immutable sizes, без отрицательных privacy выводов |
| `read_bot_profile` | `from telegram_patterns.aiogram import read_bot_profile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Fresh getMe плюс три locale reads; optional own-bot photos, unrequested None |
| `update_bot_profile` | `from telegram_patterns.aiogram import update_bot_profile` | [ref.bot_profiles](api-reference-bot.md#ref-bot_profiles) | Текущий host ACL перед каждым выбранным own-bot методом и fresh readback; без retry/rollback |
| `InlineChatType` | `from telegram_patterns.aiogram import InlineChatType` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Literal inline chat context, including explicit unknown None |
| `InlineAuthorizer` | `from telegram_patterns.aiogram import InlineAuthorizer` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Async current host ACL(actor,item) → strict bool |
| `InlineSearchProvider` | `from telegram_patterns.aiogram import InlineSearchProvider` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Async host provider of a fresh immutable catalog |
| `InlineCachePolicy` | `from telegram_patterns.aiogram import InlineCachePolicy` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Explicit bounded cache_time/is_personal policy |
| `InlineItem` | `from telegram_patterns.aiogram import InlineItem` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Frozen article identity and literal/entities text; shareable=False by default |
| `InlinePage` | `from telegram_patterns.aiogram import InlinePage` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Frozen page bound to the original query; answer_request builds one native request |
| `InlineSearch` | `from telegram_patterns.aiogram import InlineSearch` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Bounded immutable search snapshot with HMAC cursor and fixed chain expiry |
| `inline_articles` | `from telegram_patterns.aiogram import inline_articles` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Fresh native article/text models with explicit parse_mode=None |
| `inline_query_router` | `from telegram_patterns.aiogram import inline_query_router` | [ref.bot_inline_search](api-reference-bot.md#ref-bot_inline_search) | Host Dispatcher router with provider/ACL deadline, stale rejection and one native answer |
| `PollKind` | `from telegram_patterns.aiogram import PollKind` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Literal regular/quiz |
| `PollChoice` | `from telegram_patterns.aiogram import PollChoice` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Frozen literal option and cloned native SDK rich media |
| `PollSpec` | `from telegram_patterns.aiogram import PollSpec` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Frozen validated modern creation parameters |
| `PollOptionState` | `from telegram_patterns.aiogram import PollOptionState` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Persistent option identity and raw reported count |
| `PollState` | `from telegram_patterns.aiogram import PollState` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Immutable native Poll snapshot with nullable answers and full JSON details |
| `PollVote` | `from telegram_patterns.aiogram import PollVote` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Selected persistent/ordinal IDs and exact user/chat identity; empty means retraction |
| `PollOptionAddition` | `from telegram_patterns.aiogram import PollOptionAddition` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Option service observation with possibly unknown poll association and preserved details |
| `PollBinding` | `from telegram_patterns.aiogram import PollBinding` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Bot/poll/chat/message/thread/business binding of an own confirmed response |
| `PollLocator` | `from telegram_patterns.aiogram import PollLocator` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Host lookup identity or exact address, always bot scoped |
| `PollObservation` | `from telegram_patterns.aiogram import PollObservation` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Union of available state/vote/option observations |
| `PollEvent` | `from telegram_patterns.aiogram import PollEvent` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Update ID, binding and one immutable observation |
| `PollObserver` | `from telegram_patterns.aiogram import PollObserver` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Async host observer; owns durable dedup/state policy |
| `PollLookup` | `from telegram_patterns.aiogram import PollLookup` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Async current host binding lookup, no hidden authorization |
| `poll_request` | `from telegram_patterns.aiogram import poll_request` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | One native SendPoll request; literal entities, modern fields and no IO |
| `poll_state` | `from telegram_patterns.aiogram import poll_state` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Copy native Poll without count inference |
| `poll_vote` | `from telegram_patterns.aiogram import poll_vote` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Copy native PollAnswer without inventing user identity |
| `poll_option_added` | `from telegram_patterns.aiogram import poll_option_added` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Copy Message.poll_option_added, including inaccessible/omitted address |
| `poll_events_router` | `from telegram_patterns.aiogram import poll_events_router` | [ref.bot_polls](api-reference-bot.md#ref-bot_polls) | Scoped Poll/PollAnswer/message/business_message routing; no count/retry/getPoll |
| `PlatformContract` | `from telegram_patterns.aiogram import PlatformContract` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Frozen native метод/семейство/right/version/source/evidence |
| `PlatformScope` | `from telegram_patterns.aiogram import PlatformScope` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Immutable server bot/actor/intent/revision и точные chat/thread/owner/child bindings |
| `PlatformPermit` | `from telegram_patterns.aiogram import PlatformPermit` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Текущие host policy facts, consent/quote и дополнительные права |
| `PlatformAction` | `from telegram_patterns.aiogram import PlatformAction` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Копия exact native request, проверка scope/params и immutable fingerprint |
| `PlatformReceipt` | `from telegram_patterns.aiogram import PlatformReceipt` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Безопасный method/outcome/result ID для прежнего intent |
| `PlatformResult` | `from telegram_patterns.aiogram import PlatformResult` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Receipt и native result; payload скрыт в repr |
| `PlatformHooks` | `from telegram_patterns.aiogram import PlatformHooks` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Async host authorize/atomic claim/durable record contract |
| `SecretToken` | `from telegram_patterns.aiogram import SecretToken` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Repr-hidden managed token с явным reveal для secret store |
| `PlatformEvent` | `from telegram_patterns.aiogram import PlatformEvent` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Immutable native Update facts и preserved raw JSON; payload скрыт в repr |
| `PlatformLookup` | `from telegram_patterns.aiogram import PlatformLookup` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Async current host binding по событию |
| `PlatformObserver` | `from telegram_patterns.aiogram import PlatformObserver` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Async host observer; owns dedup/order/revocation policy |
| `platform_contracts` | `from telegram_patterns.aiogram import platform_contracts` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | 51 разрешенный native метод с current method-specific rights и SDK sources |
| `execute_platform_action` | `from telegram_patterns.aiogram import execute_platform_action` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Authorize/fresh rights/one claim/one SDK call/receipt без automatic retry |
| `managed_bot_link` | `from telegram_patterns.aiogram import managed_bot_link` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Native user-confirmed создание; без I/O или получения token |
| `platform_event` | `from telegram_patterns.aiogram import platform_event` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Копирование native facts без guessed identity/history |
| `platform_events_router` | `from telegram_patterns.aiogram import platform_events_router` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Observers для разрешенных native events в текущем Dispatcher |
| `StoryPhotoUpload` | `from telegram_patterns.aiogram import StoryPhotoUpload` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Validated new photo InputFile bridge к SDK nested multipart |
| `StoryVideoUpload` | `from telegram_patterns.aiogram import StoryVideoUpload` | [ref.bot_platform](api-reference-bot.md#ref-bot_platform) | Validated new video InputFile/duration bridge к SDK nested multipart |
| `FSMSnapshot` | `from telegram_patterns.aiogram import FSMSnapshot` | [ref.bot_fsm_storage](api-reference-bot.md#ref-bot_fsm_storage) | Immutable revision and detached JSON answers |
| `FSMConflict` | `from telegram_patterns.aiogram import FSMConflict` | [ref.bot_fsm_storage](api-reference-bot.md#ref-bot_fsm_storage) | Stale CAS refused before effects |
| `SnapshotStore` | `from telegram_patterns.aiogram import SnapshotStore` | [ref.bot_fsm_storage](api-reference-bot.md#ref-bot_fsm_storage) | Host-owned durable snapshot transaction contract |
| `AtomicFSMStorage` | `from telegram_patterns.aiogram import AtomicFSMStorage` | [ref.bot_fsm_storage](api-reference-bot.md#ref-bot_fsm_storage) | Optional atomic capability on current project storage |
| `SnapshotFSMStorage` | `from telegram_patterns.aiogram import SnapshotFSMStorage` | [ref.bot_fsm_storage](api-reference-bot.md#ref-bot_fsm_storage) | aiogram BaseStorage facade over supplied host store |
| `DialogLifetime` | `from telegram_patterns.aiogram import DialogLifetime` | [ref.bot_fsm_storage](api-reference-bot.md#ref-bot_fsm_storage) | Absolute draft deadline without expiring pending effects |

## CLI и CSS

`python -m telegram_patterns recipes "две кнопки"` читает cookbook, не исполняет код. `python -m telegram_patterns init "<NEW_PATH>" --library "<PROVIDED_WHEEL>" --dry-run` показывает все файлы; без dry-run создает новый каталог. `python -m telegram_patterns doctor "<PROJECT>"` делает local diagnosis без repairs/HTTP. `python -m telegram_patterns run-recipe demo-recovery` показывает requirements; явный `--offline` запускает закрытый installed fixture без токена. Native references требуют host/аргументов. Изменение существующего проекта и live запуск — отдельные действия. Commands/exit codes проверяются installed CLI.

CSS entry: `@awesome-telegram/patterns/styles.css`. В bundler: `import "@awesome-telegram/patterns/styles.css";`; в browser consumer подключите link к скопированному CSS из resolved subpath. CSS не создает UI и не заменяет host state. Import resolution и настоящий browser stylesheet проверяются отдельно.

Type-only TypeScript exports существуют в declarations, без runtime JavaScript binding. Imports типов используют `type`. Python Literal/Protocol annotations проверяются Mypy; это не runtime validation внешнего JSON.
