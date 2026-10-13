"""telegram-code-patterns stays a short intent table whose links reach every reference."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / '.agents/skills/telegram-code-patterns'


class CodePatternsSkillTests(unittest.TestCase):
    def test_short_and_every_reference_linked_directly(self):
        text = (SKILL / 'SKILL.md').read_text(encoding='utf-8')
        # 400 words of intent table plus the shared SKILL.md template (headings, scope, three mistakes);
        # each reference adds one short intent line, so the cap grows by its words only. «Проверка» adds the grep
        # search for a known symbol and the direct links to the API sections, after the table so routing stays as is.
        self.assertLessEqual(len(text.split()), 540)
        # One level deep (agentskills.io): no reference is reached only through another one.
        direct = set(re.findall(r'\(references/([a-z0-9-]+\.md)\)', text))
        self.assertEqual({path.name for path in (SKILL / 'references').glob('*.md')} - direct, set())
        self.assertIn('grep -n', text, 'a known symbol is found without reading the reference whole')

    def test_routing_cases_name_existing_references(self):
        import json
        existing = {path.name for path in (SKILL / 'references').glob('*.md')}
        for name in ('telegram-code-patterns-routing.json', 'telegram-code-patterns-routing-holdout.json'):
            cases = json.loads((ROOT / 'evaluations' / name).read_text(encoding='utf-8'))['cases']
            self.assertGreaterEqual(len(cases), 12)
            for case in cases:
                self.assertTrue(set(case['expected']) <= existing, case)


if __name__ == '__main__':
    unittest.main()
