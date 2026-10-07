"""Check lines in every skill name the Bot API, SDK and library versions the repository is built on."""
import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SkillCheckLineTests(unittest.TestCase):
    def setUp(self):
        self.lines = {}
        for path in sorted((ROOT / '.agents/skills').glob('*/SKILL.md')):
            found = re.findall(r'^Проверено: (\d{4}-\d{2}-\d{2}), (.+)$', path.read_text(encoding='utf-8'), re.M)
            self.assertEqual(len(found), 1, path.parent.name)
            self.lines[path.parent.name] = found[0]

    def test_versions_match_the_indexes_they_were_checked_against(self):
        bot_api = json.loads((ROOT / '.agents/skills/telegram-bot-api/references/api-index.json').read_text(encoding='utf-8'))['bot_api_version']
        sdk = json.loads((ROOT / 'catalog/telegram-capabilities.json').read_text(encoding='utf-8'))['sdk']
        library = json.loads((ROOT / 'components.json').read_text(encoding='utf-8'))['library_version']
        for name, (_, scope) in self.lines.items():
            with self.subTest(skill=name):
                for version in re.findall(r'Bot API (\d+\.\d+)', scope):
                    self.assertEqual(version, bot_api, 'Bot API changed: recheck the skill and its date')
                for version in re.findall(r'aiogram (\d+\.\d+\.\d+)', scope):
                    self.assertEqual(f'aiogram {version}', sdk, 'SDK changed: recheck the skill and its date')
                for version in re.findall(r'awesome-telegram-patterns (\d+\.\d+\.\d+)', scope):
                    self.assertEqual(version, library)

    def test_telegram_names_in_skills_exist_in_current_indexes(self):
        spec = importlib.util.spec_from_file_location('check_skill_sources', ROOT / 'scripts/check_skill_sources.py')
        checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
        report = checker.offline(ROOT / '.agents/skills')
        known = checker.telegram_names()
        self.assertIn('sendMessageDraft', known)
        self.assertEqual(set(report), set(self.lines))
        for name, entry in report.items():
            self.assertTrue(set(entry['telegram']) <= known, name)
            self.assertTrue(entry['links'], f'{name} links its sources')


if __name__ == '__main__':
    unittest.main()
