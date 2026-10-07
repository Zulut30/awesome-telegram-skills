"""telegram-code-patterns stays a short intent table whose links reach every reference."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / '.agents/skills/telegram-code-patterns'


class CodePatternsSkillTests(unittest.TestCase):
    def test_short_and_every_reference_reachable(self):
        text = (SKILL / 'SKILL.md').read_text(encoding='utf-8')
        # 400 words of intent table plus the shared SKILL.md template (headings, scope, three mistakes).
        self.assertLessEqual(len(text.split()), 470)
        direct = set(re.findall(r'\(references/([a-z0-9-]+\.md)\)', text))
        reachable = set(direct)
        for name in direct:
            reachable |= set(re.findall(r'\]\(([a-z0-9-]+\.md)(?:#[^)]*)?\)', (SKILL / 'references' / name).read_text(encoding='utf-8')))
        self.assertEqual({path.name for path in (SKILL / 'references').glob('*.md')} - reachable, set())

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
