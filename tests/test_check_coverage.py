"""scripts/check_coverage.py: statement minimum for the package, full lines and branches for the guarded modules."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/check_coverage.py'
spec = importlib.util.spec_from_file_location('check_coverage', SCRIPT)
check_coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_coverage)


def summary(missing_lines=0, missing_branches=0, partial=0):
    return {'summary': {'missing_lines': missing_lines, 'missing_branches': missing_branches,
                        'num_partial_branches': partial, 'num_branches': 10}}


def report(statements=95.0, **overrides):
    files = {f'/src/{module}': summary() for module in check_coverage.FULL_BRANCHES}
    files.update(overrides)
    return {'meta': {'branch_coverage': True}, 'files': files,
            'totals': {'percent_statements_covered': statements, 'percent_branches_covered': 80.0}}


class CoverageGateTests(unittest.TestCase):
    def test_minimum_and_full_branch_modules(self):
        self.assertTrue(check_coverage.check(report())['passed'])
        self.assertFalse(check_coverage.check(report(89.99))['passed'])
        partial = check_coverage.check(report(**{'/src/telegram_patterns/slots.py': summary(partial=1)}))
        self.assertFalse(partial['passed'])
        self.assertEqual(partial['full_branch_modules']['telegram_patterns/slots.py']['partial_branches'], 1)
        windows = report()
        windows['files'] = {path.replace('/', '\\'): value for path, value in windows['files'].items()}
        self.assertTrue(check_coverage.check(windows)['passed'])
        missing = report()
        del missing['files']['/src/telegram_patterns/_aiogram/media.py']
        result = check_coverage.check(missing)
        self.assertEqual(result['full_branch_modules']['telegram_patterns/_aiogram/media.py'],
                         {'passed': False, 'reason': 'not measured'})

    def test_command_line_exit_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'coverage.json'
            for data, code in ((report(), 0), (report(50.0), 1)):
                path.write_text(json.dumps(data), encoding='utf-8')
                done = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
                self.assertEqual(done.returncode, code, done.stderr)
            data = report()
            data['meta']['branch_coverage'] = False
            path.write_text(json.dumps(data), encoding='utf-8')
            done = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 2)
            self.assertIn('branch coverage', done.stderr)


if __name__ == '__main__':
    unittest.main()
