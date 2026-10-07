"""Every telegram_patterns import in the skills' Python examples exists in this package version."""

import ast
import importlib
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class ReferenceImportTests(unittest.TestCase):
    def test_imported_names_exist(self):
        checked = set()
        for path in sorted((ROOT / '.agents/skills').rglob('*.md')):
            for block in re.findall(r'```python\n(.*?)```', path.read_text(encoding='utf-8'), re.S):
                for node in ast.walk(ast.parse(block)):
                    if (
                        isinstance(node, ast.ImportFrom)
                        and node.module
                        and node.module.split('.')[0] == 'telegram_patterns'
                    ):
                        module = importlib.import_module(node.module)
                        for alias in node.names:
                            with self.subTest(
                                file=path.relative_to(ROOT).as_posix(), name=f'{node.module}.{alias.name}'
                            ):
                                self.assertTrue(
                                    hasattr(module, alias.name)
                                    or importlib.util.find_spec(f'{node.module}.{alias.name}') is not None
                                )
                            checked.add((node.module, alias.name))
        self.assertGreaterEqual(len(checked), 150)


if __name__ == '__main__':
    unittest.main()
