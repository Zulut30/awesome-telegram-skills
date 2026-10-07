"""Counts quoted in README and current-state docs match the catalogs they describe."""
from collections import Counter
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def facts() -> dict[str, int]:
    recipes = json.loads((ROOT / 'catalog/recipe-gallery.json').read_text(encoding='utf-8'))['recipes']
    verification = Counter(recipe['verification'] for recipe in recipes)
    kinds = Counter(recipe['execution']['kind'] for recipe in recipes)
    return {'recipes': len(recipes), 'sdk': verification['sdk'], 'mock': verification['mock'],
            'reference': kinds['reference'], 'executors': len(recipes) - kinds['reference'],
            'dispatcher': kinds['dispatcher'],
            'symbols': len(json.loads((ROOT / 'catalog/api-reference-index.json').read_text(encoding='utf-8'))['symbols']),
            'groups': len(json.loads((ROOT / 'components.json').read_text(encoding='utf-8'))['components']),
            'skills': len(list((ROOT / '.agents/skills').glob('*/SKILL.md')))}


# (file, pattern, names of the facts its groups quote, in order)
QUOTES = [
    ('README.md', r'skills-(\d+)-', ['skills']),
    ('README.md', r'\| (\d+) скилла? для ИИ-агентов', ['skills']),
    ('README.md', r'\*\*(\d+) скилла?\*\*', ['skills']),
    ('README.md', r'все (\d+) скилла? ставятся', ['skills']),
    ('README.md', r'Рецепты \((\d+)\) \| [^|]+\| (\d+) — на настоящем SDK без сети, (\d+) — на заглушках, (\d+) — справочные',
     ['recipes', 'sdk', 'mock', 'reference']),
    ('README.md', r'\*\*(\d+) рецептов', ['recipes']),
    ('README.md', r'\*\*(\d+) групп[аы]? компонентов\*\*', ['groups']),
    ('.agents/skills/telegram-code-patterns/references/components.md', r'Текущий каталог содержит (\d+) групп[аы]? компонентов', ['groups']),
    ('.agents/skills/telegram-code-patterns/references/maturity.md', r'В поставке [\d.]+: (\d+) групп[аы]? experimental', ['groups']),
    ('README.en.md', r'skills-(\d+)-', ['skills']),
    ('README.en.md', r'\| (\d+) skills for AI agents', ['skills']),
    ('README.en.md', r'all (\d+) skills install', ['skills']),
    ('README.en.md', r'Recipes \((\d+)\) \| [^|]+\| (\d+) run on the real SDK offline, (\d+) on stubs, (\d+) are reference',
     ['recipes', 'sdk', 'mock', 'reference']),
    ('.claude-plugin/marketplace.json', r'"(\d+) skills for Telegram', ['skills']),
    ('docs/component-library.md', r'(\d+) групп[аы]? компонентов, (\d+) публичных Python/TypeScript-символ(?:а|ов)? и (\d+) рецептов?\. '
     r'(\d+) Python fixtures', ['groups', 'symbols', 'recipes', 'executors']),
    ('docs/library-roadmap-100.md', r'(\d+) групп[аы]? компонентов, (\d+) публичных Python/TypeScript-символ(?:а|ов)?, (\d+) навыка и (\d+) рецептов?',
     ['groups', 'symbols', 'skills', 'recipes']),
    ('docs/recipe-execution.md', r'У всех (\d+) cookbook-рецептов', ['recipes']),
    ('docs/recipe-execution.md', r'(\d+) Python-рецептов имеют локальный исполнитель', ['executors']),
    ('docs/recipe-execution.md', r'все (\d+) Python fixtures', ['executors']),
    ('.agents/skills/telegram-code-patterns/references/components.md', r'есть (\d+) Python fixtures и (\d+) native references',
     ['executors', 'reference']),
]


class CurrentNumbersTests(unittest.TestCase):
    def test_quoted_counts_match_catalogs(self):
        current = facts()
        for file, pattern, names in QUOTES:
            with self.subTest(file=file, pattern=pattern):
                match = re.search(pattern, (ROOT / file).read_text(encoding='utf-8'))
                self.assertIsNotNone(match, 'the sentence changed: update QUOTES')
                self.assertEqual(dict(zip(names, map(int, match.groups()))), {name: current[name] for name in names})


if __name__ == '__main__':
    unittest.main()
