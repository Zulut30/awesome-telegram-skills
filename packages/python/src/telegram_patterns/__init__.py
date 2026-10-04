"""Core components; importing these does not require a Telegram SDK."""
from .initdata import InvalidInitData, VerifiedLaunch, validate_init_data
from .sqlite_once import OnceResult, OperationConflict, SQLiteOnce
from .settings import BotSettings
from .recipes import Maturity, Recipe, RecipeCatalog, VerificationLevel
from .starter import StarterPlan, create_starter
from .errors import (
    AuthenticationRequired, ConflictFailure, ErrorCategory, ErrorCode, ErrorOutcome, ErrorReport,
    InvalidCompletion, InvalidType, OperationKind, PatternError, PermissionDenied, RecoveryAction,
    TimeoutFailure, TransportFailure, UnknownOutcome, UnsupportedCapability, ValidationFailure, safe_error_report,
)

__all__ = [
    "BotSettings", "InvalidInitData", "VerifiedLaunch", "validate_init_data",
    "OnceResult", "OperationConflict", "SQLiteOnce",
    "Maturity", "VerificationLevel", "Recipe", "RecipeCatalog",
    "StarterPlan", "create_starter",
    "AuthenticationRequired", "ConflictFailure", "ErrorCategory", "ErrorCode", "ErrorOutcome", "ErrorReport",
    "InvalidCompletion", "InvalidType", "OperationKind", "PatternError", "PermissionDenied", "RecoveryAction",
    "TimeoutFailure", "TransportFailure", "UnknownOutcome", "UnsupportedCapability", "ValidationFailure", "safe_error_report",
]
