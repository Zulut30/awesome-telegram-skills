"""scripts/run_python_tests.py shards modules, skips integration tests in --unit and refuses child processes there."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'scripts/run_python_tests.py'
SPAWNING = '''import subprocess, sys, unittest
from _support import integration


class Spawn(unittest.TestCase):
    {marker}def test_child_process(self):
        subprocess.run([sys.executable, '-c', 'pass'], check=True)
'''
PLAIN = '''import unittest


class Plain(unittest.TestCase):
    def test_in_process(self):
        self.assertEqual(sum(range(4)), 6)
'''


class PythonTestRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='runner-')
        self.addCleanup(temporary.cleanup)
        self.tests = Path(temporary.name)
        shutil.copy(ROOT / 'packages/python/tests/_support.py', self.tests / '_support.py')
        (self.tests / 'test_plain.py').write_text(PLAIN, encoding='utf-8')

    def run_runner(self, *arguments):
        result = subprocess.run([sys.executable, str(RUNNER), '--tests', str(self.tests), '--json', *arguments],
                                capture_output=True, text=True, timeout=120)
        return result.returncode, json.loads(result.stdout.splitlines()[-1]), result.stderr

    def test_unit_scope_skips_marked_and_refuses_unmarked_child_processes(self):
        (self.tests / 'test_spawn.py').write_text(SPAWNING.format(marker=''), encoding='utf-8')
        code, report, log = self.run_runner('--unit', '--jobs', '2')
        self.assertEqual((code, report['passed'], report['tests']), (1, False, 2))
        self.assertIn('Unit scope started child processes at: test_spawn.py:', log)
        (self.tests / 'test_spawn.py').write_text(SPAWNING.format(marker='@integration\n    '), encoding='utf-8')
        code, report, _ = self.run_runner('--unit', '--jobs', '2')
        self.assertEqual((code, report['passed'], report['tests'], report['skipped']), (0, True, 2, 1))
        self.assertEqual((report['scope'], report['jobs'], report['modules']), ('unit', 2, 2))
        code, report, _ = self.run_runner('--jobs', '1')
        self.assertEqual((code, report['scope'], report['tests'], report['skipped'], report['jobs']), (0, 'all', 2, 0, 1))

    def test_failures_budget_and_empty_directory_fail(self):
        (self.tests / 'test_broken.py').write_text(PLAIN.replace('6)', '7)'), encoding='utf-8')
        code, report, log = self.run_runner('--unit')
        self.assertEqual((code, report['passed']), (1, False))
        self.assertIn('AssertionError: 6 != 7', log)
        (self.tests / 'test_broken.py').unlink()
        code, report, log = self.run_runner('--unit', '--budget', '0')
        self.assertEqual((code, report['passed'], report['budget']), (1, False, 0))
        self.assertIn('exceeds the budget', log)
        empty = self.tests / 'empty'
        empty.mkdir()
        result = subprocess.run([sys.executable, str(RUNNER), '--tests', str(empty)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('No test_*.py modules', result.stderr)


if __name__ == '__main__':
    unittest.main()
