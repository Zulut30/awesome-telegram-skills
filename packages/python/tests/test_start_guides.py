"""Code on the role start pages runs as written and prints the documented result."""

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _support import integration

ROOT = Path(__file__).resolve().parents[3]


class StartGuideTests(unittest.TestCase):
    @integration
    def test_existing_aiogram_bot_snippet_prints_the_documented_output(self):
        page = (ROOT / 'docs/start/existing-aiogram-bot.md').read_text(encoding='utf-8')
        code = re.search(r'<!-- start:existing-bot -->\n```python\n(.*?)\n```', page, re.S).group(1)
        expected = re.search(r'Ожидаемый вывод: `([^`]+)`', page).group(1)
        with tempfile.TemporaryDirectory() as folder:
            done = subprocess.run(
                [sys.executable, '-c', code], cwd=folder, capture_output=True, text=True, encoding='utf-8', timeout=60
            )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), expected)


if __name__ == '__main__':
    unittest.main()
