# Справочник API 0.14.0

Публичные imports, самостоятельные минимальные композиции и границы каждого символа. Все группы experimental. Рецепты ref.* принадлежат этому справочнику; cookbook RecipeCatalog отдельно содержит Telegram requests/layouts. Исполненные fixtures не доказывают live/device/provider acceptance.

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

## CLI и CSS

`python -m telegram_patterns recipes "две кнопки"` читает cookbook, не исполняет код. `python -m telegram_patterns init "<NEW_PATH>" --library "<PROVIDED_WHEEL>" --dry-run` показывает все файлы; без dry-run создает новый каталог. `python -m telegram_patterns doctor "<PROJECT>"` делает local diagnosis без repairs/HTTP. `python -m telegram_patterns run-recipe demo-recovery` показывает requirements; явный `--offline` запускает закрытый installed fixture без токена. Native references требуют host/аргументов. Изменение существующего проекта и live запуск — отдельные действия. Commands/exit codes проверяются installed CLI.

CSS entry: `@awesome-telegram/patterns/styles.css`. В bundler: `import "@awesome-telegram/patterns/styles.css";`; в browser consumer подключите link к скопированному CSS из resolved subpath. CSS не создает UI и не заменяет host state. Import resolution и настоящий browser stylesheet проверяются отдельно.

Type-only TypeScript exports существуют в declarations, без runtime JavaScript binding. Imports типов используют `type`. Python Literal/Protocol annotations проверяются Mypy; это не runtime validation внешнего JSON.
