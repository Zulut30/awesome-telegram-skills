"""Every skill has three judged tasks; the with/without report matches them and the README table."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / 'evaluations/skill-value.json'
REPORT = ROOT / 'evaluations/reports/skill-value-latest.json'


def evaluator():
    spec = importlib.util.spec_from_file_location('eval_skill_value', ROOT / 'scripts/eval_skill_value.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def result(task_id: str, skill: str, without: list[bool], with_: list[bool]) -> dict:
    return {'id': task_id, 'skill': skill, 'criteria': [f'c{number}' for number in range(len(without))],
            'without': {'turns': 1, 'verdicts': [{'met': met, 'why': ''} for met in without], 'answer': 'a'},
            'with': {'turns': 3, 'verdicts': [{'met': met, 'why': ''} for met in with_], 'answer': 'b'}}


class SkillValueCasesTests(unittest.TestCase):
    def test_every_skill_has_three_tasks_with_criteria(self):
        tasks = json.loads(CASES.read_text(encoding='utf-8'))['tasks']
        skills = {path.parent.name for path in (ROOT / '.agents/skills').glob('*/SKILL.md')}
        counts = Counter(task['skill'] for task in tasks)
        self.assertEqual(set(counts), skills)
        self.assertEqual([name for name, count in counts.items() if count < 3], [])
        self.assertEqual(len({task['id'] for task in tasks}), len(tasks))
        for task in tasks:
            with self.subTest(task=task['id']):
                self.assertTrue(task['task'].strip())
                self.assertGreaterEqual(len(task['criteria']), 3)
                self.assertEqual(len(set(task['criteria'])), len(task['criteria']))


class SkillValueReportTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = evaluator()
        self.report = json.loads(REPORT.read_text(encoding='utf-8'))
        self.tasks = {task['id']: task for task in json.loads(CASES.read_text(encoding='utf-8'))['tasks']}

    def test_runs_cover_current_tasks_and_totals_follow_verdicts(self):
        self.assertGreaterEqual(len(self.report['runs']), 2, 'two solver models')
        for run in self.report['runs']:
            with self.subTest(solver=run['solver']):
                self.assertEqual([item['id'] for item in run['results']], list(self.tasks),
                                 'tasks changed: rerun scripts/eval_skill_value.py for them')
                for item in run['results']:
                    self.assertEqual(item['criteria'], self.tasks[item['id']]['criteria'], item['id'])
                    for condition in ('without', 'with'):
                        self.assertNotIn('answer', item[condition])
                        self.assertEqual(len(item[condition]['verdicts']), len(item['criteria']), item['id'])
                summary = self.evaluator.summarize(run['results'])
                self.assertEqual(run['skills'], summary['skills'])
                self.assertEqual(run['totals'], summary['totals'])
                self.assertEqual(set(run['skills_sha256']), set(run['skills']))
                self.assertGreater(run['totals']['with'], run['totals']['without'])

    def test_readme_shows_the_report_table(self):
        readme = (ROOT / 'evaluations/README.md').read_text(encoding='utf-8')
        self.assertIn(self.evaluator.table(self.report), readme)


class SkillValueMergeTests(unittest.TestCase):
    def test_partial_run_replaces_only_its_tasks(self):
        module = evaluator()
        with tempfile.TemporaryDirectory() as folder:
            cases = Path(folder) / 'cases.json'
            cases.write_text(json.dumps({'tasks': [{'id': 'a-1'}, {'id': 'b-1'}]}), encoding='utf-8')
            module.ROOT = Path(folder).resolve()
            first = {'solver': 'haiku', 'judge': 'sonnet', 'cli': ['1'], 'skills_sha256': {'a': 'x', 'b': 'y'},
                     'results': [result('a-1', 'a', [False] * 4, [True] * 4), result('b-1', 'b', [False] * 3, [False] * 3)]}
            report = module.merge(None, {**first, **module.summarize(first['results'])}, cases_file=cases)
            self.assertEqual(report['runs'][0]['totals']['passed_with'], 1)
            again = {'solver': 'haiku', 'judge': 'sonnet', 'cli': ['2'], 'skills_sha256': {'b': 'z'},
                     'results': [result('b-1', 'b', [False] * 3, [True, True, True])]}
            report = module.merge(report, {**again, **module.summarize(again['results'])}, cases_file=cases)
            run = report['runs'][0]
            self.assertEqual([item['id'] for item in run['results']], ['a-1', 'b-1'])
            self.assertEqual(run['skills_sha256'], {'a': 'x', 'b': 'z'})
            self.assertEqual(run['cli'], ['1', '2'])
            self.assertEqual((run['totals']['with'], run['totals']['passed_with']), (7, 2))
            self.assertNotIn('answer', run['results'][0]['with'])
            with self.assertRaises(ValueError):
                module.merge(report, {**again, 'judge': 'opus', **module.summarize(again['results'])}, cases_file=cases)

    def test_one_solver_key_keeps_one_answering_model(self):
        # An alias such as haiku moves to a new model with a CLI update; its results must not mix in one column.
        module = evaluator()
        with tempfile.TemporaryDirectory() as folder:
            cases = Path(folder) / 'cases.json'
            cases.write_text(json.dumps({'tasks': [{'id': 'a-1'}, {'id': 'b-1'}]}), encoding='utf-8')
            module.ROOT = Path(folder).resolve()

            def run(task_id: str, skill: str, model: str | None) -> dict:
                item = result(task_id, skill, [False] * 3, [True] * 3)
                if model:
                    for condition in ('without', 'with'):
                        item[condition].update({'served_model': model, 'judge_model': 'claude-sonnet-5-5'})
                results = [item]
                return {'solver': 'haiku', 'judge': 'sonnet', 'cli': ['1'], 'skills_sha256': {skill: 'x'},
                        'served_models': module.served_models(results), **module.summarize(results), 'results': results}

            report = module.merge(None, run('a-1', 'a', None), cases_file=cases)
            self.assertEqual(report['runs'][0]['served_models'], {'solver': [], 'judge': []}, 'nothing recorded, nothing claimed')
            report = module.merge(report, run('b-1', 'b', 'claude-haiku-5-5'), cases_file=cases)
            self.assertEqual(report['runs'][0]['served_models'], {'solver': ['claude-haiku-5-5'], 'judge': ['claude-sonnet-5-5']})
            report = module.merge(report, run('a-1', 'a', 'claude-haiku-5-5'), cases_file=cases)
            with self.assertRaisesRegex(ValueError, 'answered as'):
                module.merge(report, run('a-1', 'a', 'claude-haiku-4-5'), cases_file=cases)

    def test_pass_needs_three_quarters_of_criteria(self):
        module = evaluator()
        self.assertEqual([module.needed(size) for size in (3, 4, 5)], [3, 3, 4])


if __name__ == '__main__':
    unittest.main()
