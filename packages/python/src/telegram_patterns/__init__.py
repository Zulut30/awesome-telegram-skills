"""Core components; importing these does not require a Telegram SDK."""
from .initdata import InvalidInitData, VerifiedLaunch, validate_init_data
from .sqlite_once import OnceResult, OperationConflict, SQLiteOnce
from .settings import BotSettings
from .recipes import Maturity, Recipe, RecipeCatalog, VerificationLevel
from .starter import StarterPlan, create_starter

__all__ = [
    "BotSettings", "InvalidInitData", "VerifiedLaunch", "validate_init_data",
    "OnceResult", "OperationConflict", "SQLiteOnce",
    "Maturity", "VerificationLevel", "Recipe", "RecipeCatalog",
    "StarterPlan", "create_starter",
]
