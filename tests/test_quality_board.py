"""Quality board numbers come from repository data and CI runs, never from hand-written values."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_quality_board', ROOT / 'scripts/build_quality_board.py')
board = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = board
spec.loader.exec_module(board)


class QualityBoardTests(unittest.TestCase):
    def test_repository_numbers_match_their_sources(self):
        numbers = board.collect(ROOT)
        selection = json.loads((ROOT / 'evaluations/reports/skill-selection-latest.json').read_text(encoding='utf-8'))
        self.assertEqual([run['accuracy'] for run in numbers['skill_selection']['runs']], [run['accuracy'] for run in selection['runs']])
        index = json.loads((ROOT / '.agents/skills/telegram-bot-api/references/api-index.json').read_text(encoding='utf-8'))
        self.assertEqual(numbers['bot_api']['methods'], len(index['methods']))
        recipes = json.loads((ROOT / 'catalog/recipe-gallery.json').read_text(encoding='utf-8'))['recipes']
        self.assertEqual(numbers['bot_api']['with_recipe'], sum(recipe['id'].startswith('api.') for recipe in recipes))
        self.assertLessEqual(numbers['bot_api']['with_component'], numbers['bot_api']['methods'])
        self.assertEqual(numbers['sources']['skills'], len(list((ROOT / '.agents/skills').glob('*/SKILL.md'))))
        self.assertEqual(numbers['live']['cases'], 0)  # no live acceptance report yet; the board says so
        self.assertIsNone(numbers['ci'])
        self.assertIsNotNone(numbers['acceptance']['date'])

    def test_ci_runs_are_summarized_from_completed_runs_only(self):
        runs = [{'status': 'completed', 'conclusion': 'success', 'created_at': '2026-10-07T10:00:00Z'},
                {'status': 'in_progress', 'conclusion': None, 'created_at': '2026-10-07T11:00:00Z'},
                {'status': 'completed', 'conclusion': 'failure', 'created_at': '2026-10-06T10:00:00Z'},
                {'status': 'completed', 'conclusion': 'cancelled', 'created_at': '2026-10-05T10:00:00Z'},
                {'status': 'completed', 'conclusion': 'success', 'created_at': '2026-10-04T10:00:00Z'}]
        self.assertEqual(board.summarize_runs(runs), {'runs': 3, 'green': 2, 'share': 0.667,
                                                      'last': {'conclusion': 'success', 'date': '2026-10-07'}})
        self.assertEqual(board.summarize_runs([]), {'runs': 0, 'green': 0, 'share': None, 'last': None})

    def test_site_workflow_builds_the_board_from_ci_and_refreshes_daily(self):
        shared = (ROOT / '.github/workflows/docs-site.yml').read_text(encoding='utf-8')
        self.assertIn('python scripts/build_quality_board.py --ci --repo "$GITHUB_REPOSITORY"', shared)
        self.assertIn('--quality output/quality-board.json', shared)
        pages = (ROOT / '.github/workflows/docs-pages.yml').read_text(encoding='utf-8')
        self.assertIn('schedule:', pages)
        self.assertIn('actions: read', pages)
        checks = (ROOT / '.github/workflows/repository-checks.yml').read_text(encoding='utf-8')
        block = checks.split('\n  docs-site:\n', 1)[1].split('\n  api-compatibility:\n', 1)[0]
        self.assertIn('actions: read', block)


if __name__ == '__main__':
    unittest.main()
