"""Англоязычный вход полон: все скиллы описаны, команды проверяются, текст на английском."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGLISH = ('README.en.md', 'docs/en/quickstart.md', 'docs/en/for-agents.md')
CYRILLIC = re.compile('[А-Яа-яЁё]')


def blocks(text):
    return re.findall(r'<!-- (quickstart(?:-bash)?:[\w-]+) -->\n```(powershell|bash)\n', text)


class EnglishDocsTests(unittest.TestCase):
    def test_every_skill_has_an_english_summary(self):
        readme = (ROOT / 'README.en.md').read_text(encoding='utf-8')
        listed = set(re.findall(r'^\| \[(telegram-[a-z-]+)\]\(\.agents/skills/\1/SKILL\.md\) \| [A-Z]', readme, re.M))
        self.assertEqual(listed, {p.name for p in (ROOT / '.agents/skills').iterdir() if (p / 'SKILL.md').is_file()})

    def test_english_quickstart_has_the_same_verified_blocks(self):
        russian = (ROOT / 'docs/quickstart.md').read_text(encoding='utf-8')
        english = (ROOT / 'docs/en/quickstart.md').read_text(encoding='utf-8')
        self.assertEqual(blocks(english), blocks(russian))
        self.assertEqual(len(blocks(english)), 12)

    def test_pages_are_written_in_english(self):
        # Intentional Russian: language switch links, a Russian heading anchor and a Russian search query example.
        allowed = ('Русская версия', '#политика-поддержки', 'две кнопки')
        for name in ENGLISH:
            text = (ROOT / name).read_text(encoding='utf-8')
            for value in allowed:
                text = text.replace(value, '')
            with self.subTest(page=name):
                self.assertEqual(CYRILLIC.findall(text), [])


if __name__ == '__main__':
    unittest.main()
