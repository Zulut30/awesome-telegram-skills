"""Every tracked text file is stored with LF; .gitattributes keeps it that way on every OS."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(shutil.which('git') is None or not (ROOT / '.git').exists(), 'needs a git checkout')
class LineEndingTests(unittest.TestCase):
    def test_no_tracked_file_is_stored_with_crlf(self):
        listing = subprocess.run(['git', 'ls-files', '--eol'], cwd=ROOT, capture_output=True, text=True,
                                 encoding='utf-8', check=True).stdout.splitlines()
        self.assertGreater(len(listing), 500)
        stored_crlf = [line.split('\t', 1)[1] for line in listing if line.split()[0] in {'i/crlf', 'i/mixed'}]
        self.assertEqual(stored_crlf, [])

    def test_gitattributes_normalizes_to_lf(self):
        rules = (ROOT / '.gitattributes').read_text(encoding='utf-8').splitlines()
        self.assertIn('* text=auto eol=lf', rules)
        self.assertIn('*.png binary', rules)


if __name__ == '__main__':
    unittest.main()
