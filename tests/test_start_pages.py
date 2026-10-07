"""Стартовые страницы по ролям: четыре страницы, каждая на один экран, все доступны из README."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ('first-bot', 'existing-aiogram-bot', 'mini-app', 'ai-agent')


class StartPagesTests(unittest.TestCase):
    def test_hub_links_every_role_page_and_readme_links_the_hub(self):
        hub = (ROOT / 'docs/start.md').read_text(encoding='utf-8')
        for page in PAGES:
            self.assertIn(f'(start/{page}.md)', hub)
        self.assertIn('(docs/start.md)', (ROOT / 'README.md').read_text(encoding='utf-8'))

    def test_each_page_fits_one_screen_and_ends_with_next_steps(self):
        for page in PAGES:
            text = (ROOT / f'docs/start/{page}.md').read_text(encoding='utf-8')
            prose = re.sub(r'```.*?```', '', text, flags=re.S)
            with self.subTest(page=page):
                self.assertLessEqual(len(prose.split()), 330, 'one screen of prose')
                self.assertIn('## Что дальше', text)
                self.assertTrue(text.startswith('# '))


if __name__ == '__main__':
    unittest.main()
