"""The skill selection report covers at least 200 requests, names the models that answered, meets 95% in the
gate mode and matches today's descriptions; the evaluator's helpers pick the answering model and the skill name."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import re
import unittest

try:
    import yaml  # noqa: F401  (descriptions are read from YAML frontmatter)
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'evaluations/reports/skill-selection-latest.json'
spec = importlib.util.spec_from_file_location('eval_skill_selection', ROOT / 'scripts/eval_skill_selection.py')
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)
MODEL_ID = re.compile(r'claude-[a-z]+-\d+-\d+')


@unittest.skipIf(yaml is None, 'PyYAML is not installed')
class SkillSelectionReportTests(unittest.TestCase):
    def test_report_is_current_and_meets_threshold(self):
        report = json.loads(REPORT.read_text(encoding='utf-8'))
        self.assertEqual(report['descriptions_sha256'], evaluator.digest(evaluator.descriptions(None)),
                         'descriptions changed: rerun scripts/eval_skill_selection.py and refresh the report')
        cases = json.loads((ROOT / report['cases']).read_text(encoding='utf-8'))['cases']
        self.assertGreaterEqual(len(cases), 200)
        self.assertTrue(any(case.get('not') for case in cases), 'negative requests are part of the set')
        self.assertEqual((report['threshold'], report['gate_mode']), (evaluator.THRESHOLD, evaluator.GATE_MODE))
        gated = [run for run in report['runs'] if run['mode'] == report['gate_mode']]
        self.assertGreaterEqual(len({run['served_model'] for run in gated}), 2, 'the gate needs at least two models')
        for run in report['runs']:
            with self.subTest(model=run['served_model'], mode=run['mode']):
                # An alias such as "haiku" moves to a new model with a CLI update: the report names the exact model.
                self.assertRegex(run['served_model'], MODEL_ID)
                self.assertEqual(run['served_models'], [run['served_model']], 'one run, one answering model')
                self.assertEqual(run['cases'], len(cases))
                self.assertEqual(sum(kind['cases'] for kind in run['by_kind'].values()), len(cases))
                self.assertEqual(run['cases'] - run['correct'], len(run['misses']))
                if run['mode'] == report['gate_mode']:
                    self.assertGreaterEqual(run['accuracy'], report['threshold'])


class EvaluatorHelperTests(unittest.TestCase):
    def test_answering_model_skips_the_cli_helper_model(self):
        # The CLI bills a small helper model for its own side request next to the requested one.
        usage = {'claude-haiku-5-5': {'inputTokens': 6519}, 'claude-haiku-4-5': {'inputTokens': 10, 'cacheCreationInputTokens': 8691}}
        self.assertEqual(evaluator.answering_model(usage, 'claude-haiku-4-5'), 'claude-haiku-4-5')
        self.assertEqual(evaluator.answering_model(usage, 'haiku'), 'claude-haiku-4-5')
        self.assertEqual(evaluator.answering_model({'claude-haiku-5-5': {'inputTokens': 15211}}, 'haiku'), 'claude-haiku-5-5')
        sonnet = {'claude-haiku-5-5': {'inputTokens': 6519}, 'claude-sonnet-5-5': {'cacheReadInputTokens': 7915}}
        self.assertEqual(evaluator.answering_model(sonnet, 'sonnet'), 'claude-sonnet-5-5')
        self.assertIsNone(evaluator.answering_model({}, 'haiku'))

    def test_choose_reads_the_first_name_or_the_last_line(self):
        self.assertEqual(evaluator.choose('**telegram-cryptopay**', 'instant'), 'telegram-cryptopay')
        reasoned = 'Запрос про Crypto Pay, а не про выбор маршрута в telegram-payments.\n\n**telegram-cryptopay**'
        self.assertEqual(evaluator.choose(reasoned, 'reasoned'), 'telegram-cryptopay')
        self.assertEqual(evaluator.choose(reasoned, 'instant'), 'telegram-payments')
        # A reasoned answer without a name on its last line does not follow the format and counts as no choice.
        self.assertIsNone(evaluator.choose('Подойдет telegram-cryptopay.\nВот и все.', 'reasoned'))
        self.assertIsNone(evaluator.choose('', 'reasoned'))

    def test_merge_replaces_one_model_and_mode_and_drops_stale_runs(self):
        def run(model, mode, sha='a', correct=1):
            results = [{'query': 'q1', 'expected': ['telegram-x'], 'chosen': 'telegram-x' if correct else 'telegram-y',
                        'correct': bool(correct), 'kind': 'positive'},
                       {'query': 'q2', 'expected': ['telegram-z'], 'chosen': 'telegram-z', 'correct': True, 'kind': 'negative'}]
            return {'descriptions_sha256': sha, 'model': model, 'mode': mode, 'served_model': model, 'served_models': [model],
                    'cli': '2.1.294 (Claude Code)', 'cases': 2, 'correct': 1 + correct, 'accuracy': (1 + correct) / 2,
                    'results': results}
        cases = ROOT / 'evaluations/skill-selection.json'
        today = dt.date(2026, 10, 8)
        legacy = {'descriptions_sha256': 'a', 'runs': [{'model': 'haiku', 'cases': 2, 'correct': 2, 'accuracy': 1.0}]}
        report = evaluator.merge(legacy, run('claude-haiku-5-5', 'instant', correct=0), cases_file=cases, today=today)
        self.assertEqual([(item['model'], item['mode']) for item in report['runs']], [('claude-haiku-5-5', 'instant')],
                         'a run without a recorded model is dropped')
        self.assertEqual(report['runs'][0]['misses'], [{'query': 'q1', 'expected': ['telegram-x'], 'chosen': 'telegram-y'}])
        self.assertEqual(report['runs'][0]['by_kind'], {'positive': {'cases': 1, 'correct': 0}, 'negative': {'cases': 1, 'correct': 1}})
        report = evaluator.merge(report, run('claude-haiku-5-5', 'reasoned'), cases_file=cases, today=today)
        report = evaluator.merge(report, run('claude-haiku-5-5', 'instant'), cases_file=cases, today=today)
        self.assertEqual([(item['mode'], item['correct']) for item in report['runs']], [('reasoned', 2), ('instant', 2)])
        self.assertEqual((report['cases'], report['date'], report['gate_mode']), ('evaluations/skill-selection.json', '2026-10-08', 'reasoned'))
        report = evaluator.merge(report, run('claude-sonnet-5-5', 'reasoned', sha='b'), cases_file=cases, today=today)
        self.assertEqual([item['model'] for item in report['runs']], ['claude-sonnet-5-5'], 'runs on other descriptions are dropped')


if __name__ == '__main__':
    unittest.main()
