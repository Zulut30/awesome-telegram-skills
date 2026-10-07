"""Skills label library versions as 'доступно с X, проверено на <current>' and never point at old artifacts."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CURRENT = re.search(r'^version = "([^"]+)"', (ROOT / 'packages/python/pyproject.toml').read_text(encoding='utf-8'), re.M).group(1)
KNOWN = set(re.findall(r'\b0\.\d+\.\d+\b', (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')))
VERSION = r'(0\.\d+\.\d+)'
# A version right after these words reads as "you need exactly this one": only the current version may follow.
PINNED = re.compile(r'(?i)(?:(?:wheel|tarball|поставк\w*|библиотек\w*|CLI этой версии)[`*\s]*'
                    r'|`?awesome-telegram-patterns(?:\[[\w,]+\])?`?\s+)' + VERSION + r'\b')
ARTIFACT = re.compile(r'(?:awesome[_-]telegram[_-]patterns-|output/pattern-library-)' + VERSION)


def key(version: str) -> tuple[int, ...]:
    return tuple(map(int, version.split('.')))


def skill_texts():
    for path in sorted((ROOT / '.agents/skills').rglob('*.md')):
        yield path.relative_to(ROOT).as_posix(), path.read_text(encoding='utf-8')


class SkillVersionLabelTests(unittest.TestCase):
    def test_checked_on_is_the_current_version_and_available_since_is_real(self):
        labels = 0
        for name, text in skill_texts():
            for version in re.findall(r'проверено на ' + VERSION, text):
                labels += 1
                self.assertEqual(version, CURRENT, f'{name}: recheck against {CURRENT} and update the label')
            for version in re.findall(r'(?:[Дд]оступно с|\(с) ' + VERSION, text):
                self.assertIn(version, KNOWN, f'{name}: {version} is not a released version')
                self.assertLessEqual(key(version), key(CURRENT), name)
        self.assertGreaterEqual(labels, 20)

    def test_no_old_version_is_required_or_linked(self):
        for name, text in skill_texts():
            for pattern in (PINNED, ARTIFACT):
                for match in pattern.finditer(text):
                    with self.subTest(file=name, text=match.group(0)):
                        self.assertEqual(match.group(1), CURRENT, 'use "доступно с X, проверено на ' + CURRENT +
                                         '" or <WHEEL>/<TARBALL> instead of an old exact version')

    def test_rules_catch_the_old_forms(self):
        for sample in ('Локальная поставка **0.17.0**: SDK-free', 'Установите wheel 0.17.0 в отдельное окружение',
                       'awesome_telegram_patterns-0.11.0-py3-none-any.whl', 'output/pattern-library-0.13.0/report.json',
                       'предоставленный wheel `awesome-telegram-patterns` 0.14.0;',
                       'требуют `awesome-telegram-patterns[aiogram]` 0.14.0 и aiogram'):
            with self.subTest(sample=sample):
                self.assertTrue(any(match.group(1) != CURRENT for pattern in (PINNED, ARTIFACT)
                                    for match in pattern.finditer(sample)))

    def test_typescript_imports_in_references_are_current_exports(self):
        index = (ROOT / 'packages/typescript/src/index.ts').read_text(encoding='utf-8')
        exported = {name.strip() for match in re.finditer(r'export (?:type )?\{([^}]+)\}', index)
                    for name in match.group(1).split(',')}
        seen = set()
        for name, text in skill_texts():
            for block in re.findall(r'```(?:typescript|ts|javascript|js)\n(.*?)```', text, re.S):
                for match in re.finditer(r'import\s*(?:type\s*)?\{([^}]+)\}\s*from\s*[\'"]@awesome-telegram/patterns[\'"]', block, re.S):
                    for item in match.group(1).split(','):
                        symbol = item.strip().removeprefix('type ').split(' as ')[0].strip()
                        if symbol:
                            seen.add(symbol)
                            self.assertIn(symbol, exported, f'{name}: {symbol} is not exported by {CURRENT}')
        self.assertGreaterEqual(len(seen), 30)

    def test_copies_of_docs_pages_are_identical(self):
        for path in sorted((ROOT / '.agents/skills').glob('*/references/*.md')):
            source = ROOT / 'docs' / path.name
            if source.is_file():
                with self.subTest(copy=path.relative_to(ROOT).as_posix()):
                    self.assertEqual(path.read_bytes(), source.read_bytes())


if __name__ == '__main__':
    unittest.main()
