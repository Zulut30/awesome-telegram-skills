"""The skill selection report covers at least 200 requests, meets 95% and matches today's descriptions."""
import importlib.util
import json
from pathlib import Path
import unittest

try:
    import yaml  # noqa: F401  (descriptions are read from YAML frontmatter)
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'evaluations/reports/skill-selection-latest.json'


@unittest.skipIf(yaml is None, 'PyYAML is not installed')
class SkillSelectionReportTests(unittest.TestCase):
    def test_report_is_current_and_meets_threshold(self):
        spec = importlib.util.spec_from_file_location('eval_skill_selection', ROOT / 'scripts/eval_skill_selection.py')
        evaluator = importlib.util.module_from_spec(spec); spec.loader.exec_module(evaluator)
        report = json.loads(REPORT.read_text(encoding='utf-8'))
        self.assertEqual(report['descriptions_sha256'], evaluator.digest(evaluator.descriptions(None)),
                         'descriptions changed: rerun scripts/eval_skill_selection.py and refresh the report')
        cases = json.loads((ROOT / report['cases']).read_text(encoding='utf-8'))['cases']
        self.assertGreaterEqual(len(cases), 200)
        self.assertTrue(any(case.get('not') for case in cases), 'negative requests are part of the set')
        self.assertGreaterEqual(len(report['runs']), 2)
        for run in report['runs']:
            with self.subTest(model=run['model']):
                self.assertEqual(run['cases'], len(cases))
                self.assertGreaterEqual(run['accuracy'], 0.95)


if __name__ == '__main__':
    unittest.main()
