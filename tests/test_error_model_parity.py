"""Python core и TypeScript используют одинаковую модель ошибок (docs/error-model.md)."""
import ast
import importlib.util
import re
import sys
import typing
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def python_errors():
    spec = importlib.util.spec_from_file_location('parity_errors', ROOT / 'packages/python/src/telegram_patterns/errors.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def russian_texts() -> dict[str, str]:
    tree = ast.parse((ROOT / 'packages/python/src/telegram_patterns/texts.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.AnnAssign) and getattr(n.target, 'id', '') == '_RU')
    return ast.literal_eval(node.value)


def ts_union(source: str, name: str) -> set[str]:
    match = re.search(rf'export type {name} = ([^;]+);', source)
    return set(re.findall(r"'([^']+)'", match.group(1)))


class ErrorModelParityTests(unittest.TestCase):
    def test_codes_categories_recovery_and_messages_match(self):
        source = (ROOT / 'packages/typescript/src/errors.ts').read_text(encoding='utf-8')
        errors = python_errors()
        for name in ('ErrorCode', 'ErrorCategory', 'ErrorOutcome', 'RecoveryAction', 'OperationKind'):
            with self.subTest(type=name):
                self.assertEqual(set(typing.get_args(getattr(errors, name))), ts_union(source, name))
        block = source.split('const descriptions', 1)[1].split('};', 1)[0]
        ts = {code: (category, recovery, message) for code, category, recovery, message in
              re.findall(r"'?([\w-]+)'?: \['([\w-]+)', '([\w-]+)', '([^']+)'\]", block)}
        self.assertEqual({code: value[:2] for code, value in ts.items()}, errors._DESCRIPTORS)
        # Python takes the public message from the Russian text catalog (telegram_patterns.texts, key error.<code>).
        russian = russian_texts()
        self.assertEqual({code: value[2] for code, value in ts.items()}, {code: russian['error.' + code] for code in ts})
        self.assertEqual(set(ts), set(typing.get_args(errors.ErrorCode)))
        self.assertIn(f"'{russian['error.unknown-outcome-write']}'", source)  # unknown write outcome


if __name__ == '__main__':
    unittest.main()
