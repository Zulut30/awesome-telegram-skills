"""Every confusable pair named in item 37 has negative scenarios, and cases name real skills."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAIRS = [('telegram-bot-api', 'telegram-buttons'), ('telegram-mini-app-ui', 'telegram-mini-app-design-system'),
         ('telegram-mini-app-ui', 'telegram-mini-app-ux'), ('telegram-testing', 'telegram-mini-app-device-qa'),
         ('telegram-mini-app-device-qa', 'telegram-mini-app-visual-regression'), ('telegram-payments', 'telegram-subscription-access'),
         ('telegram-payments', 'telegram-yookassa'), ('telegram-project-planner', 'telegram-mini-app-architecture'),
         ('telegram-mini-app-auth', 'telegram-web-login'), ('telegram-debugging', 'telegram-observability')]


class SkillBoundaryTests(unittest.TestCase):
    def test_each_pair_has_negative_scenarios_in_both_directions(self):
        cases = json.loads((ROOT / 'evaluations/skill-boundaries.json').read_text(encoding='utf-8'))['cases']
        skills = {path.parent.name for path in (ROOT / '.agents/skills').glob('*/SKILL.md')}
        for case in cases:
            self.assertTrue(set(case['expected']) <= skills and set(case['not']) <= skills, case)
            self.assertFalse(set(case['expected']) & set(case['not']), case)
        for first, second in PAIRS:
            for good, bad in ((first, second), (second, first)):
                with self.subTest(expected=good, not_=bad):
                    self.assertTrue(any(good in case['expected'] and bad in case['not'] for case in cases))


if __name__ == '__main__':
    unittest.main()
