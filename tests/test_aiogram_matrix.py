"""The aiogram CI matrix, the doctor's tested versions and the extra's lower bound describe one range."""
import ast
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def constant(name):
    tree = ast.parse((ROOT / 'packages/python/src/telegram_patterns/diagnostics.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == name)
    return ast.literal_eval(node.value)


class AiogramMatrixTests(unittest.TestCase):
    def test_matrix_doctor_and_extra_agree(self):
        workflow = (ROOT / '.github/workflows/repository-checks.yml').read_text(encoding='utf-8')
        matrix = re.search(r"aiogram: \[([^\]]+)\]", workflow).group(1)
        tested = tuple(value.strip().strip("'\"") for value in matrix.split(','))
        self.assertEqual(tested, constant('AIOGRAM_TESTED'))
        minors = [tuple(map(int, version.split('.')[:2])) for version in tested]
        self.assertEqual(minors, sorted(set(minors)), 'one release per minor, oldest first')
        self.assertEqual(len(minors), 3, 'the three latest minors')
        self.assertEqual(minors[0], constant('AIOGRAM_MINIMUM'))
        self.assertEqual(minors[-1], constant('AIOGRAM_FULL_API'))
        project = tomllib.loads((ROOT / 'packages/python/pyproject.toml').read_text(encoding='utf-8'))['project']
        extra = project['optional-dependencies']['aiogram']
        self.assertEqual(extra, [f'aiogram>={minors[0][0]}.{minors[0][1]},<4'])
        self.assertIn(f"`>={minors[0][0]}.{minors[0][1]},<4`", (ROOT / 'docs/versioning.md').read_text(encoding='utf-8'))
        self.assertNotIn('<2027', ''.join(project['optional-dependencies']['calendar']))


if __name__ == '__main__':
    unittest.main()
