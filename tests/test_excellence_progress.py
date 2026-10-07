"""Реестр выполнения плана из 100 пунктов согласован с самим планом."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'docs/internal/excellence-plan-100.md'
PROGRESS = ROOT / 'docs/internal/excellence-progress.json'


class ExcellenceProgressTests(unittest.TestCase):
    def test_registry_matches_plan_and_statuses_are_justified(self):
        plan = PLAN.read_text(encoding='utf-8').split('## Порядок выполнения')[0]
        titles = {int(n): t.rstrip('.') for n, t in re.findall(r'^(\d+)\. \*\*(.+?)\*\*', plan, re.M)}
        self.assertEqual(sorted(titles), list(range(1, 101)))
        progress = json.loads(PROGRESS.read_text(encoding='utf-8'))
        self.assertEqual([item['id'] for item in progress['items']], list(range(1, 101)))
        for item in progress['items']:
            with self.subTest(item=item['id']):
                self.assertEqual(item['title'], titles[item['id']])
                self.assertIn(item['status'], {'pending', 'partial', 'done'})
                if item['status'] != 'pending':
                    self.assertTrue(item['commit_subject'].startswith(f"excellence({item['id']:03d}): "))
                    self.assertTrue(item['evidence'])
                if item['status'] == 'partial':
                    self.assertTrue(item['remaining'])
                if item['status'] == 'done':
                    self.assertIsNone(item['remaining'])


if __name__ == '__main__':
    unittest.main()
