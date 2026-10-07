"""The skill validator enforces the Agent Skills specification on real temporary trees."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

try:
    import yaml  # noqa: F401  (the validator needs PyYAML; CI installs it)
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(yaml is None, 'PyYAML is not installed')
class ValidateSkillsTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('validate_skills', ROOT / 'scripts/validate_skills.py')
        self.validator = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.validator)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'components.json').write_text(json.dumps({'library_version': '9.9.9'}), encoding='utf-8')
        self.skill('name: telegram-other\ndescription: "Other task. Не для примера → telegram-sample."\nlicense: MIT\nmetadata:\n  version: "9.9.9"', name='telegram-other')

    SOURCES = '## Источники\n\n[Bot API](https://core.telegram.org/bots/api).\n\nПроверено: 2026-10-07, Bot API 10.3.\n'

    def skill(self, frontmatter, name='telegram-sample', body=None):
        folder = self.root / '.agents/skills' / name
        (folder / 'agents').mkdir(parents=True, exist_ok=True)
        (folder / 'agents/openai.yaml').write_text(
            'interface:\n  display_name: Sample\n  short_description: A sample skill used by validator tests\n'
            f'  default_prompt: Use ${name} for a sample task.\n', encoding='utf-8')
        body = f'# Sample\n\nDo the thing.\n\n{self.SOURCES}' if body is None else body
        (folder / 'SKILL.md').write_text(f'---\n{frontmatter}\n---\n\n{body}', encoding='utf-8')

    def errors(self):
        return self.validator.validate(self.root)[1]

    BASE = ('name: telegram-sample\ndescription: "Does a sample task. Use it in tests. Не для другой задачи → telegram-other."'
            '\nlicense: MIT\nmetadata:\n  version: "9.9.9"')

    def test_specification_compliant_skill_passes(self):
        self.skill(self.BASE + '\ncompatibility: "Requires Python 3.11+"\nallowed-tools: Read Bash(git:*)')
        self.assertEqual(self.errors(), [])

    def test_each_rule_is_enforced(self):
        cases = {
            'metadata version': self.BASE.replace('9.9.9', '1.0'),
            'metadata missing': self.BASE.split('\nmetadata:')[0],
            'metadata non-string': self.BASE.replace('"9.9.9"', '9'),
            'license missing': self.BASE.replace('license: MIT\n', ''),
            'compatibility too long': self.BASE + '\ncompatibility: "' + 'x' * 501 + '"',
            'compatibility empty': self.BASE + '\ncompatibility: ""',
            'allowed-tools list': self.BASE + '\nallowed-tools: [Read]',
            'unknown field': self.BASE + '\nversion: "1"',
            'description too long': self.BASE.replace('Does a sample task. Use it in tests.', 'x' * 1025),
            'name mismatch': self.BASE.replace('name: telegram-sample', 'name: telegram-other'),
            'consecutive hyphens': self.BASE.replace('name: telegram-sample', 'name: telegram--sample'),
            'boundary missing': self.BASE.replace(' Не для другой задачи → telegram-other.', ''),
            'boundary to unknown skill': self.BASE.replace('telegram-other', 'telegram-missing'),
            'boundary to itself': self.BASE.replace('→ telegram-other', '→ telegram-sample'),
        }
        self.skill(self.BASE)
        self.assertEqual(self.errors(), [], 'the base case is clean, so each error below comes from its rule')
        for label, frontmatter in cases.items():
            with self.subTest(label):
                self.skill(frontmatter)
                self.assertTrue(self.errors(), label)

    def test_sources_section_and_check_date_are_required(self):
        intro = '# Sample\n\nDo the thing.\n\n'
        cases = {
            'section missing': intro,
            'section not last': intro + self.SOURCES + '\n## Проверка\n\nRun it.\n',
            'no source link': intro + '## Источники\n\nДокументация.\n\nПроверено: 2026-10-07, Bot API 10.3.\n',
            'check line missing': intro + '## Источники\n\n[Bot API](https://core.telegram.org/bots/api).\n',
            'date not ISO': intro + self.SOURCES.replace('2026-10-07', '7 октября 2026'),
            'impossible date': intro + self.SOURCES.replace('2026-10-07', '2026-02-30'),
            'future date': intro + self.SOURCES.replace('2026-10-07', '2999-01-01'),
            'scope missing': intro + self.SOURCES.replace(', Bot API 10.3.', ''),
            'two check lines': intro + self.SOURCES + '\nПроверено: 2026-10-06, aiogram 3.31.0.\n',
        }
        self.skill(self.BASE)
        self.assertEqual(self.errors(), [])
        for label, body in cases.items():
            with self.subTest(label):
                self.skill(self.BASE, body=body)
                self.assertTrue(any('Источники' in error or 'check date' in error for error in self.errors()), label)
        self.assertIsNone(self.validator.check_sources(self.SOURCES, today=self.validator.date(2026, 10, 6)),
                          'one day of slack for time zones')

    def test_repository_skills_pass(self):
        count, errors = self.validator.validate(ROOT)
        self.assertEqual(errors, [])
        self.assertEqual(count, 42)


if __name__ == '__main__':
    unittest.main()
