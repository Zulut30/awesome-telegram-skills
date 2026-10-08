"""scripts/build_native_signatures.py: official parameter names and optionality, a complete type table, no drift."""
import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/build_native_signatures.py'
spec = importlib.util.spec_from_file_location('build_native_signatures', SCRIPT)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class NativeSignatureTests(unittest.TestCase):
    def setUp(self):
        self.index = json.loads(generator.INDEX.read_text(encoding='utf-8'))
        self.table = json.loads(generator.TYPES.read_text(encoding='utf-8'))

    def test_official_signature_parsing(self):
        cases = {
            'ready()': [],
            'start(params[, callback])': [('params', False), ('callback', True)],
            'updateBiometricToken(token, [callback])': [('token', False), ('callback', True)],
            'setEmojiStatus(custom_emoji_id[, params, callback])': [('custom_emoji_id', False), ('params', True), ('callback', True)],
            'getItem(key, callback)': [('key', False), ('callback', False)],
        }
        for signature, expected in cases.items():
            self.assertEqual(generator.official_parameters(signature), expected, signature)
        with self.assertRaises(ValueError):
            generator.official_parameters('broken(a[, b)')

    def test_generated_module_is_current_and_covers_every_method(self):
        done = subprocess.run([sys.executable, str(SCRIPT), '--check'], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        module = generator.OUTPUT.read_text(encoding='utf-8')
        self.assertEqual(module.count("\n  '"), len(self.index['methods']), 'one signature per official method')
        self.assertIn("'showPopup': (params: PopupParams, callback?: (buttonId: string) => void) => void;", module)
        self.assertIn("'isVersionAtLeast': (version: string) => boolean;", module)

    def test_table_drift_is_refused(self):
        renamed = copy.deepcopy(self.table)
        renamed['methods']['showPopup']['parameters'] = {'options': 'PopupParams', 'callback': '() => void'}
        with self.assertRaisesRegex(ValueError, 'showPopup: parameters'):
            generator.render(self.index, renamed)
        missing = copy.deepcopy(self.table)
        del missing['methods']['ready']
        with self.assertRaisesRegex(ValueError, "missing \\['ready'\\]"):
            generator.render(self.index, missing)


if __name__ == '__main__':
    unittest.main()
