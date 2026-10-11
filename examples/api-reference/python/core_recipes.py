"""Только поиск и чтение; найденный код здесь не исполняется."""
import json
from telegram_patterns import Maturity, VerificationLevel, Recipe, RecipeCatalog

maturity: Maturity = 'experimental'
verification: VerificationLevel = 'sdk'
catalog = RecipeCatalog()
recipe: Recipe = catalog.search('две кнопки', maturity=maturity, verification=verification,
                               task='keyboards', context='private', sdk='aiogram', sdk_version='3.31.0', api_version='bot:10.3')[0]
assert recipe.id == 'two-columns' and catalog.get(recipe.id) == recipe
assert len(catalog.recipes) == 311 and catalog.library_version
assert recipe.source_files and recipe.check_files and 'keyboards' in recipe.tasks
lost = catalog.search('потерянный ответ', task='recovery', context='backend')[0]
assert lost.id == 'demo-recovery' and lost.sdk == 'python-core' and lost.api_version == 'none'
preview = recipe.preview
assert preview is not None and [len(row) for row in preview['inline_keyboard']] == [2, 2]
preview['inline_keyboard'][0][0]['text'] = 'local-copy'
assert catalog.get(recipe.id).preview != preview
# SDK evidence не делает API stable и не доказывает appearance в Telegram.
print(json.dumps({'passed': True, 'case': 'core_recipes', 'network': False}))
