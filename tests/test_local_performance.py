"""Реальные операции локального измерителя; Chrome acceptance выполняется отдельно."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node is required for the local performance helper')
class LocalPerformanceTests(unittest.TestCase):
    def test_calibration_regression_and_caller_output_refusals(self):
        result = subprocess.run(
            ['node', '--test', str(ROOT / 'tools/local-performance/check.test.mjs')],
            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
