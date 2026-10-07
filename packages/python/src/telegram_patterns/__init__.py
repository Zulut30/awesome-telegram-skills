"""Core components; importing these does not require a Telegram SDK."""
from .initdata import TELEGRAM_PUBLIC_KEYS, InvalidInitData, VerifiedLaunch, validate_init_data, validate_init_data_signature
from .sqlite_once import OnceResult, OperationConflict, SQLiteOnce
from .calendar import CalendarMonth, TimeSlot, resolve_local_time
from .slots import SlotBooking, SlotSchedule, SQLiteSlotStore
from .settings import BotSettings
from .message_text import EntityKind, TextEntity, TextPayload, FormattedText, MessageBuilder, utf16_length, escape_html, escape_markdown_v2, split_formatted
from .rich_message import RichButton, RichButtonStyle, RichMessage, RichMessageBuilder, RichSpan, RichText
from .ephemeral import EphemeralMessageRef, EphemeralNotAllowed, EphemeralTrigger, ephemeral_parameters
from .stars_subscription import STARS_SUBSCRIPTION_PERIOD, RenewalState, StarsCharge, StarsSubscription, SubscriptionEventRejected
from .selection import SelectionOption, SelectionSpec, SelectionContext, SelectionState, SelectionResult, SelectionMenu
from .recipes import Maturity, Recipe, RecipeCatalog, VerificationLevel
from .execution import RecipeRunPlan, RecipeRunResult, plan_recipe, run_recipe_offline
from .starter import StarterPlan, create_starter
from .starter_components import StarterComponent, StarterConflict, starter_components
from .extensions import AsyncTransport, OnceStore, ProviderAdapter, RefundProvider
from .errors import (
    AuthenticationRequired, ConflictFailure, ErrorCategory, ErrorCode, ErrorOutcome, ErrorReport,
    InvalidCompletion, InvalidType, OperationKind, PatternError, PermissionDenied, RecoveryAction,
    TimeoutFailure, TransportFailure, UnknownOutcome, UnsupportedCapability, ValidationFailure, safe_error_report,
)

__all__ = [
    "BotSettings", "InvalidInitData", "VerifiedLaunch", "validate_init_data", "validate_init_data_signature", "TELEGRAM_PUBLIC_KEYS",
    "EntityKind", "TextEntity", "TextPayload", "FormattedText", "MessageBuilder", "utf16_length", "escape_html", "escape_markdown_v2", "split_formatted",
    "RichMessageBuilder", "RichMessage", "RichButton", "RichButtonStyle", "RichSpan", "RichText",
    "EphemeralTrigger", "EphemeralMessageRef", "EphemeralNotAllowed", "ephemeral_parameters",
    "StarsSubscription", "StarsCharge", "RenewalState", "SubscriptionEventRejected", "STARS_SUBSCRIPTION_PERIOD",
    "SelectionOption", "SelectionSpec", "SelectionContext", "SelectionState", "SelectionResult", "SelectionMenu",
    "OnceResult", "OperationConflict", "SQLiteOnce",
    "CalendarMonth", "TimeSlot", "resolve_local_time", "SlotBooking", "SlotSchedule", "SQLiteSlotStore",
    "Maturity", "VerificationLevel", "Recipe", "RecipeCatalog",
    "RecipeRunPlan", "RecipeRunResult", "plan_recipe", "run_recipe_offline",
    "StarterPlan", "create_starter",
    "StarterComponent", "StarterConflict", "starter_components",
    "AsyncTransport", "OnceStore", "ProviderAdapter", "RefundProvider",
    "AuthenticationRequired", "ConflictFailure", "ErrorCategory", "ErrorCode", "ErrorOutcome", "ErrorReport",
    "InvalidCompletion", "InvalidType", "OperationKind", "PatternError", "PermissionDenied", "RecoveryAction",
    "TimeoutFailure", "TransportFailure", "UnknownOutcome", "UnsupportedCapability", "ValidationFailure", "safe_error_report",
]
