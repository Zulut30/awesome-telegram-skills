"""Core components; importing these does not require a Telegram SDK."""
from .initdata import InvalidInitData, VerifiedLaunch, validate_init_data
from .sqlite_once import OnceResult, OperationConflict, SQLiteOnce
from .settings import BotSettings
from .recipes import Recipe, RecipeCatalog
from .starter import StarterPlan, create_starter

__all__ = ["InvalidInitData", "VerifiedLaunch", "validate_init_data", "OnceResult", "OperationConflict", "SQLiteOnce", "BotSettings", "Recipe", "RecipeCatalog", "StarterPlan", "create_starter"]
