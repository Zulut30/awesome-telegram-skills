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
            'call(name[, input][, callback])': [('name', False), ('input', True), ('callback', True)],
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
        # The official SDK emits null when the popup closes without a selected button.
        self.assertIn("'showPopup': (params: PopupParams, callback?: (buttonId: string | null) => void) => void;", module)
        self.assertIn("'isVersionAtLeast': (version: string) => boolean;", module)
        self.assertIn("'Serverless.call': (...args: [name: string, callback?: NativeServerlessCallback | undefined] | [name: string, input?: Readonly<Record<string, unknown>> | undefined, callback?: NativeServerlessCallback | undefined]) => void;", module)

    def test_reviewed_callback_shift_overloads_cannot_drop_required_names_or_invent_parameters(self):
        for label, branches in (
            ('not-a-list', {'name': 'callback'}),
            ('single-branch', [['name', 'input', 'callback']]),
            ('not-a-list-branch', ['name', ['name', 'input', 'callback']]),
            ('not-a-name', [['name', None], ['name', 'input', 'callback']]),
            ('required-name-omitted', [['callback'], ['name', 'input', 'callback']]),
            ('invented-parameter', [['name', 'secret'], ['name', 'input', 'callback']]),
            ('reordered', [['name', 'callback', 'input'], ['name', 'input', 'callback']]),
            ('repeated-name', [['name', 'name'], ['name', 'input', 'callback']]),
            ('missing-full-branch', [['name'], ['name', 'callback']]),
            ('duplicate-branch', [['name', 'input', 'callback'], ['name', 'input', 'callback']]),
        ):
            with self.subTest(case=label):
                table = copy.deepcopy(self.table)
                table['methods']['Serverless.call']['overloads'] = branches
                with self.assertRaisesRegex(ValueError, 'Serverless.call: overload'):
                    generator.render(self.index, table)

    def test_serverless_partial_review_does_not_redate_all_existing_types(self):
        module = generator.render(self.index, self.table)
        self.assertIn('(checked 2026-10-07)', module)
        self.assertIn('Partial review 2026-11-05: Serverless.call', module)
        self.assertEqual(self.table['checked_date'], '2026-10-07')
        self.assertIsNone(next(item for item in self.index['methods'] if item['path'] == 'Serverless.call')['min_version'])

    def test_callback_error_fields_must_match_the_reviewed_official_shape(self):
        for label, transform in (
            ('status-string', lambda value: value.replace('status: number', 'status: string')),
            ('parameters-required', lambda value: value.replace('parameters?:', 'parameters:')),
            ('field-omitted', lambda value: value.replace('readonly status: number; ', '')),
            ('field-invented', lambda value: value.replace(' }', '; readonly secret: string }')),
        ):
            with self.subTest(case=label):
                table = copy.deepcopy(self.table)
                table['declarations']['NativeServerlessError'] = transform(table['declarations']['NativeServerlessError'])
                with self.assertRaisesRegex(ValueError, 'callback error declaration differs'):
                    generator.render(self.index, table)

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
