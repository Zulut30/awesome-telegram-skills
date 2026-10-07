"""Проверка имен в реестрах работает без сети на подставленных ответах."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_registry_names', ROOT / 'scripts/check_registry_names.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class RegistryNameTests(unittest.TestCase):
    def test_free_and_taken_names_are_reported_without_claiming_ownership(self):
        calls = []
        def free(url):
            calls.append(url); return 404, None
        report = module.check(free)
        self.assertEqual((report['pypi']['taken'], report['npm']['taken'], report['npm']['scope_exists']), (False, False, False))
        self.assertFalse(report['ownership_proven'])
        self.assertEqual(calls, ['https://pypi.org/pypi/awesome-telegram-patterns/json',
                                 'https://registry.npmjs.org/@awesome-telegram%2Fpatterns',
                                 'https://registry.npmjs.org/-/org/awesome-telegram/package'])
        def taken(url):
            if 'pypi' in url: return 200, {'info': {'author': 'someone', 'maintainer': None}}
            if '/-/org/' in url: return 200, {}
            return 200, {'maintainers': [{'name': 'other'}]}
        report = module.check(taken)
        self.assertEqual((report['pypi']['maintainers'], report['npm']['maintainers'], report['npm']['scope_exists']),
                         (['someone'], ['other'], True))


if __name__ == '__main__':
    unittest.main()
