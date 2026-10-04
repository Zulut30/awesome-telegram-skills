"""Только поиск и чтение; найденный код здесь не исполняется."""
import json
from telegram_patterns import Maturity, VerificationLevel, Recipe, RecipeCatalog

maturity: Maturity = 'experimental'
verification: VerificationLevel = 'sdk'
catalog = RecipeCatalog()
recipe: Recipe = catalog.search('две кнопки', maturity=maturity, verification=verification)[0]
assert recipe.id == 'two-columns' and catalog.get(recipe.id) == recipe
assert len(catalog.recipes) == 298 and catalog.library_version
preview = recipe.preview
assert preview is not None and [len(row) for row in preview['inline_keyboard']] == [2, 2]
preview['inline_keyboard'][0][0]['text'] = 'local-copy'
assert catalog.get(recipe.id).preview != preview
# SDK evidence не делает API stable и не доказывает appearance в Telegram.
print(json.dumps({'passed': True, 'case': 'core_recipes', 'network': False}))
