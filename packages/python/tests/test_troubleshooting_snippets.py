"""Runnable checks on the troubleshooting page print exactly the documented output."""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / 'docs/troubleshooting.md'


class TroubleshootingSnippetTests(unittest.TestCase):
    def test_runnable_snippets_print_documented_output(self):
        text = PAGE.read_text(encoding='utf-8')
        blocks = re.findall(r'<!-- troubleshooting:run -->\n```python\n(.*?)\n```', text, re.S)
        self.assertGreaterEqual(len(blocks), 10)
        for code in blocks:
            expected = [line.split('# → ', 1)[1].strip() for line in code.splitlines() if '# → ' in line]
            with self.subTest(code=code.splitlines()[0]), tempfile.TemporaryDirectory() as folder:
                done = subprocess.run(
                    [sys.executable, '-c', code],
                    cwd=folder,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    timeout=60,
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertTrue(expected, 'each runnable check documents its output')
                self.assertEqual([line.strip() for line in done.stdout.splitlines()], expected)

    def test_read_only_tool_refuses_unsafe_methods_without_network(self):
        text = PAGE.read_text(encoding='utf-8')
        code = re.search(r'<!-- troubleshooting:tg.py -->\n```python\n(.*?)\n```', text, re.S).group(1)
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'tg.py'
            script.write_text(code, encoding='utf-8')
            environment = {key: value for key, value in os.environ.items() if key != 'BOT_TOKEN'}
            for argv in (['getUpdates'], ['deleteWebhook'], ['sendMessage?chat_id=1&text=x'], []):
                done = subprocess.run(
                    [sys.executable, '-I', str(script), *argv],
                    cwd=folder,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    timeout=30,
                    env=environment,
                )
                self.assertNotEqual(done.returncode, 0, argv)
                self.assertIn('Использование', done.stderr)
            done = subprocess.run(
                [sys.executable, '-I', str(script), 'getMe'],
                cwd=folder,
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=30,
                env=environment,
            )
            self.assertNotEqual(done.returncode, 0)
            self.assertIn('BOT_TOKEN', done.stderr)


if __name__ == '__main__':
    unittest.main()
