"""Static consumer of installed wheel: positive and expected negative type cases."""
from telegram_patterns import Maturity, VerificationLevel, RecipeCatalog
from telegram_patterns.aiogram import ActionButton, ButtonStyle, ChatType, UpdatePhase, action_menu

maturity: Maturity = 'experimental'
verification: VerificationLevel = 'sdk'
style: ButtonStyle = 'primary'
context: ChatType = 'private'
phase: UpdatePhase = 'handled'

recipes = RecipeCatalog().search(maturity=maturity, verification=verification)
markup = action_menu([ActionButton('Open', 'open', style=style)])

# warn_unused_ignores ensures these are actually rejected by installed types.
bad_maturity: Maturity = 'sdk'  # type: ignore[assignment]
bad_phase: UpdatePhase = 'clicked'  # type: ignore[assignment]
bad_style: ButtonStyle = 'red'  # type: ignore[assignment]
bad_filter = RecipeCatalog().search(maturity='sdk')  # type: ignore[arg-type]
