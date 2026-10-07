"""Таблица статуса в README совпадает с каталогом компонентов и рецептов."""
import json
import re
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReadmeStatusTests(unittest.TestCase):
    def test_status_numbers_match_catalogs(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        section = readme.split('## Можно ли брать в production', 1)[1].split('\n## ', 1)[0]
        components = json.loads((ROOT / 'components.json').read_text(encoding='utf-8'))['components']
        languages = Counter(item['language'] for item in components)
        recipes = Counter(item['verification'] for item in
                          json.loads((ROOT / 'catalog/recipe-gallery.json').read_text(encoding='utf-8'))['recipes'])
        skills = len(list((ROOT / '.agents/skills').glob('*/SKILL.md')))
        self.assertIn(f'{skills} скилл', section)
        self.assertIn(f"Python-компоненты ({languages['python']} групп)", section)
        self.assertIn(f"TypeScript-компоненты ({languages['typescript']} групп)", section)
        self.assertIn(f'Рецепты ({sum(recipes.values())})', section)
        self.assertIn(f"{recipes['sdk']} — на настоящем SDK", section)
        self.assertIn(f"{recipes['mock']} — на заглушках", section)
        self.assertIn(f"{recipes['not_run']} — справочные", section)
        stable = sum(item['maturity'] == 'stable' for item in components)
        self.assertEqual(stable == 0, 'стабильных (stable) компонентов пока нет' in section)


if __name__ == '__main__':
    unittest.main()
