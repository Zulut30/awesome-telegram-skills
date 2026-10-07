"""Core modules import without any Telegram SDK; aiogram code lives in telegram_patterns._aiogram."""

import ast
import importlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

PACKAGE = Path(importlib.import_module('telegram_patterns').__file__).parent
SDK_FACADES = {'aiogram', 'testing', 'ptb'}  # public adapter modules that need their extra


def _aliases() -> set[str]:
    return {
        path.stem for path in PACKAGE.glob('*.py') if 'Compatibility path' in path.read_text(encoding='utf-8')[:200]
    }


def _core() -> list[str]:
    skip = SDK_FACADES | _aliases() | {'__main__'}
    return sorted(path.stem for path in PACKAGE.glob('*.py') if path.stem not in skip)


PROBE = """
import importlib, importlib.abc, json, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in {'aiogram', 'telegram', 'cryptography'}:
            raise ModuleNotFoundError(f'blocked {name}', name=name)
        return None
sys.meta_path.insert(0, Block())
imported, refused = [], {}
for module in json.loads(sys.argv[1]):
    importlib.import_module('telegram_patterns.' + module); imported.append(module)
for module in json.loads(sys.argv[2]):
    try:
        importlib.import_module('telegram_patterns.' + module)
    except ModuleNotFoundError as error:
        refused[module] = error.name
print(json.dumps({'imported': imported, 'refused': refused}))
"""


class ModuleLayoutTests(unittest.TestCase):
    def test_every_core_module_imports_without_sdks(self):
        core = _core()
        sdk = ['aiogram', 'testing', 'ptb', '_aiogram.keyboards', '_aiogram.events', 'keyboards']
        result = subprocess.run(
            [sys.executable, '-I', '-c', PROBE, json.dumps(core), json.dumps(sdk)],
            capture_output=True,
            text=True,
            check=True,
            env={'PYTHONPATH': str(PACKAGE.parent)},
            cwd=PACKAGE.parent,
        )
        report = json.loads(result.stdout)
        self.assertEqual(report['imported'], core)
        self.assertEqual(set(report['refused']), set(sdk), 'adapter modules need their extra')
        self.assertIn('calendar_core', core)
        self.assertGreaterEqual(len(core), 20)

    def test_core_files_never_import_an_sdk_at_module_level(self):
        for name in _core():
            tree = ast.parse((PACKAGE / f'{name}.py').read_text(encoding='utf-8'))
            for node in tree.body:
                modules = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or '']
                    if isinstance(node, ast.ImportFrom) and node.level == 0
                    else []
                )
                self.assertFalse([m for m in modules if m.split('.')[0] in {'aiogram', 'telegram'}], name)

    def test_aiogram_code_lives_in_the_subpackage_and_old_paths_alias_it(self):
        moved = {path.stem for path in (PACKAGE / '_aiogram').glob('*.py')} - {'__init__'}
        self.assertEqual(len(moved), 18)
        for alias in _aliases() - {'calendar'}:
            module = importlib.import_module('telegram_patterns.' + alias)
            self.assertTrue(module.__name__.startswith('telegram_patterns._aiogram.'), alias)
            self.assertIn(module.__name__.rsplit('.', 1)[1], moved)
        self.assertIs(
            importlib.import_module('telegram_patterns.calendar'),
            importlib.import_module('telegram_patterns.calendar_core'),
        )
        self.assertFalse(
            {'calendar', 'aiogram'} & {path.stem for path in (PACKAGE / '_aiogram').glob('*.py')},
            'no implementation module is named after the stdlib or the SDK',
        )


if __name__ == '__main__':
    unittest.main()
