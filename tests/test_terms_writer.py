"""The shared-reference writer preserves the repository LF contract on Windows too."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import add_terms_lines


class TermsWriterTests(unittest.TestCase):
    def test_real_reference_write_has_lf_and_a_second_check_does_not_rewrite(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'reference.md'
            source.write_bytes('# Fixture\r\n\r\nПроверка версии через CAS.\r\n'.encode('utf8'))
            with patch.object(add_terms_lines, 'ROOT', root), patch.object(add_terms_lines, 'targets', return_value=[source]):
                with patch.object(sys, 'argv', ['add_terms_lines']), redirect_stdout(StringIO()):
                    self.assertEqual(add_terms_lines.main(), 0)
                written = source.read_bytes()
                self.assertNotIn(b'\r\n', written)
                self.assertIn('Термины:'.encode('utf8'), written)
                stamp = source.stat().st_mtime_ns
                with patch.object(sys, 'argv', ['add_terms_lines', '--check']), redirect_stdout(StringIO()):
                    self.assertEqual(add_terms_lines.main(), 0)
                self.assertEqual(source.read_bytes(), written)
                self.assertEqual(source.stat().st_mtime_ns, stamp)

    def test_check_reports_crlf_drift_without_modifying_the_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'reference.md'
            original = '# Fixture\r\n\r\nPlain text.\r\n'.encode('utf8')
            source.write_bytes(original)
            with patch.object(add_terms_lines, 'ROOT', root), patch.object(add_terms_lines, 'targets', return_value=[source]):
                with patch.object(sys, 'argv', ['add_terms_lines', '--check']), redirect_stdout(StringIO()):
                    self.assertEqual(add_terms_lines.main(), 1)
                self.assertEqual(source.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
