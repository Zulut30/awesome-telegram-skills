"""Core components; importing these does not require a Telegram SDK."""
from .initdata import InvalidInitData, VerifiedLaunch, validate_init_data
from .sqlite_once import OnceResult, OperationConflict, SQLiteOnce
from .settings import BotSettings
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
    "BotSettings", "InvalidInitData", "VerifiedLaunch", "validate_init_data",
    "OnceResult", "OperationConflict", "SQLiteOnce",
    "Maturity", "VerificationLevel", "Recipe", "RecipeCatalog",
    "RecipeRunPlan", "RecipeRunResult", "plan_recipe", "run_recipe_offline",
    "StarterPlan", "create_starter",
    "StarterComponent", "StarterConflict", "starter_components",
    "AsyncTransport", "OnceStore", "ProviderAdapter", "RefundProvider",
    "AuthenticationRequired", "ConflictFailure", "ErrorCategory", "ErrorCode", "ErrorOutcome", "ErrorReport",
    "InvalidCompletion", "InvalidType", "OperationKind", "PatternError", "PermissionDenied", "RecoveryAction",
    "TimeoutFailure", "TransportFailure", "UnknownOutcome", "UnsupportedCapability", "ValidationFailure", "safe_error_report",
]
