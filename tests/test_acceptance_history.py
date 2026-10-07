"""Acceptance history: a small summary in the tree, full reports behind permalinks or release assets."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_acceptance_history', ROOT / 'scripts/build_acceptance_history.py')
history = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = history
spec.loader.exec_module(history)
SUMMARY = json.loads((ROOT / 'docs/acceptance-history.json').read_text(encoding='utf-8'))


class AcceptanceHistoryTests(unittest.TestCase):
    def test_summary_is_valid_current_and_small(self):
        self.assertEqual(history.problems(SUMMARY), [])
        self.assertEqual((ROOT / 'docs/acceptance-history.md').read_text(encoding='utf-8'), history.render(SUMMARY))
        self.assertFalse((ROOT / 'docs/v1-checks').exists())
        self.assertLess((ROOT / 'docs/acceptance-history.json').stat().st_size, 80_000)
        # The documentation site publishes only versions with an accepted report.
        self.assertTrue(any(entry['version'] == '0.24.0' and entry['passed'] is True for entry in SUMMARY['reports']))

    def test_no_document_links_the_removed_report_directory(self):
        done = subprocess.run(['git', 'grep', '-n', '-E', r'\]\((\.\./)*(docs/)?v1-checks/'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(done.stdout, '')

    def test_add_summarizes_a_report_without_copying_it_and_rules_reject_bad_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / 'distribution-report.json'
            report.write_text(json.dumps({'version': '0.25.0', 'passed': True, 'checked_date': '2026-10-08', 'distribution_stages': 80,
                                          'python_tests': {'run': 600, 'passed': 600, 'skipped': 0}, 'typescript_tests': 40}), encoding='utf-8')
            url = 'https://github.com/Zulut30/awesome-telegram-skills/releases/download/v0.25.0/distribution-report.json'
            entry = history.summarize('0.25.0-distribution.json', report.read_bytes(), url)
        self.assertEqual({key: entry[key] for key in ('version', 'passed', 'stages', 'python_tests', 'typescript_tests')},
                         {'version': '0.25.0', 'passed': True, 'stages': 80, 'python_tests': 600, 'typescript_tests': 40})
        self.assertEqual(history.problems({'reports': [entry]}), [])
        bad = dict(entry, url='https://example.com/report.json', sha256='x')
        found = history.problems({'reports': [entry, entry, bad]})
        self.assertIn('0.25.0-distribution.json: listed more than once', found)
        self.assertIn('0.25.0-distribution.json: url must be a commit permalink or a release asset', found)
        self.assertIn('0.25.0-distribution.json: sha256 must be 64 hex characters', found)


if __name__ == '__main__':
    unittest.main()
