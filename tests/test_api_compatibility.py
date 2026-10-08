"""Логика проверки совместимости публичного API без сборки и сети."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_api_compatibility', ROOT / 'scripts/check_api_compatibility.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class ApiCompatibilityTests(unittest.TestCase):
    def test_declarations_are_extracted_with_bodies_and_overloads(self):
        text = '''export declare class Client {
    constructor(options: Options);
    request<T>(path: string): Promise<T>;
}
export interface Options {
    baseUrl: string;
    nested?: { deep: number };
}
export type Code = 'a' | 'b';
export declare function parse(value: string): number;
export declare function parse(value: number): number;
export declare const LIMIT: readonly ["x", "y"];
'''
        found = module._statements(text)
        self.assertEqual(set(found), {'Client', 'Options', 'Code', 'parse', 'LIMIT'})
        self.assertTrue(found['Client'].endswith('}') and 'request<T>' in found['Client'])
        self.assertIn('deep: number', found['Options'])
        self.assertEqual(found['Code'], "export type Code = 'a' | 'b';")
        self.assertEqual(found['parse'].count('export declare function parse'), 2)

    def test_removed_or_changed_symbols_need_a_changelog_mention(self):
        base = {'pkg.Keep': 1, 'pkg.Change': 1, 'pkg.Drop': 1}
        head = {'pkg.Keep': 1, 'pkg.Change': 2, 'pkg.New': 1}
        report = module.compare(base, head, '# Log\n\n## Не выпущено\n\n- Nothing named.\n\n## 0.1.0\n\n- `Change`, `Drop`\n')
        self.assertEqual((report['removed'], report['changed'], report['added']), (['pkg.Drop'], ['pkg.Change'], ['pkg.New']))
        self.assertEqual(report['unmentioned'], ['pkg.Drop', 'pkg.Change'])
        self.assertFalse(report['passed'])
        report = module.compare(base, head, '## Не выпущено\n\n- Removed `pkg.Drop`; `Change(options)` gained a field.\n')
        self.assertTrue(report['passed'])

    def test_newest_section_is_the_first_level_two_heading(self):
        self.assertEqual(module.newest_changelog_section('# T\n\n## A\nx\n## B\ny\n'), 'A\nx\n')
        self.assertEqual(module.newest_changelog_section('# T\n'), '')


if __name__ == '__main__':
    unittest.main()
