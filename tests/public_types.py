"""Static consumer of installed wheel: positive and expected negative type cases."""
from telegram_patterns import Maturity, VerificationLevel, RecipeCatalog, ErrorReport, OperationKind, safe_error_report
from telegram_patterns import AsyncTransport, OnceStore, ProviderAdapter, RefundProvider, SQLiteOnce
from telegram_patterns import StarterComponent, StarterPlan, StarterConflict, starter_components, create_starter
from telegram_patterns import RecipeRunPlan, RecipeRunResult, plan_recipe, run_recipe_offline
import sqlite3
from telegram_patterns.aiogram import ActionButton, ButtonStyle, ChatType, UpdatePhase, action_menu

maturity: Maturity = 'experimental'
verification: VerificationLevel = 'sdk'
style: ButtonStyle = 'primary'
context: ChatType = 'private'
phase: UpdatePhase = 'handled'

recipes = RecipeCatalog().search(maturity=maturity, verification=verification)
markup = action_menu([ActionButton('Open', 'open', style=style)])
operation: OperationKind = 'write'
report: ErrorReport = safe_error_report(TimeoutError(), operation=operation)
store: OnceStore[sqlite3.Connection] = SQLiteOnce('fixture.sqlite')
component: StarterComponent = starter_components('bot')[0]
plan: StarterPlan = create_starter('new-project',library='supplied.whl',components=['text-form'],dry_run=True)
selected: tuple[str, ...] = plan.components
execution: RecipeRunPlan = plan_recipe('demo-recovery')
offline_checks: tuple[str, ...] = RecipeRunResult('demo-recovery', '0.13.0', 'sqlite', ('sqlite-one-effect',)).checks
offline_ready: bool = execution.offline_ready

# warn_unused_ignores ensures these are actually rejected by installed types.
bad_maturity: Maturity = 'sdk'  # type: ignore[assignment]
bad_phase: UpdatePhase = 'clicked'  # type: ignore[assignment]
bad_style: ButtonStyle = 'red'  # type: ignore[assignment]
bad_filter = RecipeCatalog().search(maturity='sdk')  # type: ignore[arg-type]
bad_operation: OperationKind = 'retry'  # type: ignore[assignment]
bad_recovery = safe_error_report(RuntimeError(), operation='retry')  # type: ignore[arg-type]
bad_store: OnceStore[sqlite3.Connection] = object()  # type: ignore[assignment]
bad_execution: RecipeRunPlan = object()  # type: ignore[assignment]
bad_recipe_run = run_recipe_offline('demo-recovery', timeout='fast')  # type: ignore[arg-type]
