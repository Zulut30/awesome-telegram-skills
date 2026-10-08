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

    def template(self, algorithm='Do the thing.', sources=None, mistakes='- One.\n- Two.\n- Three.\n'):
        return ('# Sample\n\n## Когда использовать\n\nA sample task.\n\n## Когда не использовать\n\nAnother task.\n\n'
                f'## Алгоритм\n\n{algorithm}\n\n## Проверка\n\nRun it.\n\n## Типичные ошибки\n\n{mistakes}\n'
                + (self.SOURCES if sources is None else sources))

    def skill(self, frontmatter, name='telegram-sample', body=None):
        folder = self.root / '.agents/skills' / name
        (folder / 'agents').mkdir(parents=True, exist_ok=True)
        (folder / 'agents/openai.yaml').write_text(
            'interface:\n  display_name: Sample\n  short_description: A sample skill used by validator tests\n'
            f'  default_prompt: Use ${name} for a sample task.\n', encoding='utf-8')
        body = self.template() if body is None else body
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
        intro = self.template(sources='')
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
                self.assertTrue(any("'## Источники'" in error or 'check date' in error for error in self.errors()), label)
        self.assertIsNone(self.validator.check_sources(self.SOURCES, today=self.validator.date(2026, 10, 6)),
                          'one day of slack for time zones')

    def test_skill_follows_the_template(self):
        base = self.template()
        cases = {
            'section missing': base.replace('## Когда не использовать\n\nAnother task.\n\n', ''),
            'wrong order': base.replace('## Проверка\n\nRun it.\n\n## Типичные ошибки\n\n- One.\n- Two.\n- Three.\n',
                                        '## Типичные ошибки\n\n- One.\n- Two.\n- Three.\n\n## Проверка\n\nRun it.\n'),
            'section twice': base.replace('## Проверка\n\nRun it.', '## Проверка\n\nRun it.\n\n## Проверка\n\nAgain.'),
            'extra section after the check': base.replace('## Типичные ошибки', '## Заметки\n\nText.\n\n## Типичные ошибки'),
            'extra section before the algorithm': base.replace('## Алгоритм', '## Обзор\n\nText.\n\n## Алгоритм'),
            'empty section': base.replace('## Проверка\n\nRun it.', '## Проверка\n'),
            'two mistakes': self.template(mistakes='- One.\n- Two.\n'),
            'heading after the sources': base + '\n### Еще\n\nText.\n',
        }
        self.skill(self.BASE)
        self.assertEqual(self.errors(), [])
        for label, body in cases.items():
            with self.subTest(label):
                self.skill(self.BASE, body=body)
                self.assertTrue(any('section' in error or 'sources' in error for error in self.errors()), label)
        for label, body in {
            'example between the algorithm and the check': base.replace('## Проверка', '## Пример\n\nCode.\n\n## Проверка'),
            'subsections inside the algorithm': self.template('Intro.\n\n### Шаг\n\nText.'),
            'heading inside a code block': self.template('```markdown\n## Заметки\n```'),
        }.items():
            with self.subTest(label):
                self.skill(self.BASE, body=body)
                self.assertEqual(self.errors(), [], label)

    def reference(self, text, name='notes.md', raw=None):
        path = self.root / '.agents/skills/telegram-sample/references' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw if raw is not None else text.encode('utf-8'))
        return path

    def test_skill_files_use_lf(self):
        self.skill(self.BASE)
        self.reference('', raw=b'# Notes\r\n\r\nText.\r\n')
        self.assertTrue(any('CRLF' in error for error in self.errors()))
        self.reference('# Notes\n\nText.\n')
        self.assertEqual(self.errors(), [])

    def test_paths_in_code_must_exist_where_the_reader_looks(self):
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts/verify.py').write_text('', encoding='utf-8')
        self.skill(self.BASE, body=self.template('Run `scripts/verify.py`.'))
        self.assertTrue(any('not inside the skill folder' in error for error in self.errors()),
                        'SKILL.md is the standalone entry point')
        own = self.root / '.agents/skills/telegram-sample/scripts/verify.py'
        own.parent.mkdir(); own.write_text('', encoding='utf-8')
        self.assertEqual(self.errors(), [])
        cases = {
            'missing repository script': '```bash\npython scripts/removed.py\n```\n',
            'old output version': 'Report: `output/pattern-library-0.13.0/report.json`.\n',
            'old artifact': '```bash\npip install output/release/awesome_telegram_patterns-0.13.0-py3-none-any.whl\n```\n',
        }
        for label, text in cases.items():
            with self.subTest(label):
                self.reference(text)
                self.assertTrue(self.errors(), label)
        self.reference('Run `scripts/verify.py`, write `output/check` and `output/pattern-library-9.9.9/report.json`; '
                       'copy `examples/app/.env.example` to `examples/app/.env`.\n'
                       'Ссылка вне кода на scripts/removed.py не проверяется.\n')
        (self.root / 'examples/app').mkdir(parents=True)
        (self.root / 'examples/app/.env.example').write_text('', encoding='utf-8')
        self.assertEqual(self.errors(), [])

    def test_named_skills_must_exist(self):
        self.skill(self.BASE)
        self.reference('Для оплаты открой telegram-payments-v2.\n')
        self.assertTrue(any('unknown skill telegram-payments-v2' in error for error in self.errors()))
        self.reference('Соседний скилл telegram-other; CLI `telegram-patterns`; пакет `awesome-telegram-patterns`.\n')
        self.assertEqual(self.errors(), [])

    def test_repository_skills_pass(self):
        count, errors = self.validator.validate(ROOT)
        self.assertEqual(errors, [])
        self.assertEqual(count, len(list((ROOT / '.agents/skills').glob('*/SKILL.md'))))


if __name__ == '__main__':
    unittest.main()
