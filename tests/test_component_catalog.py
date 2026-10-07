"""components.json against the code: every catalog import exists, every public export is catalogued, versions agree."""

import ast
import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'components.json').read_text(encoding='utf-8'))
PY = ROOT / 'packages/python/src/telegram_patterns'
TS = ROOT / 'packages/typescript/src'
TS_ROOT = '@awesome-telegram/patterns'


def python_exports() -> dict[str, set[str]]:
    """`__all__` of every public Python module, read without importing the SDKs."""
    result = {}
    for module, path in (('telegram_patterns', PY / '__init__.py'), ('telegram_patterns.aiogram', PY / 'aiogram.py'),
                         ('telegram_patterns.testing', PY / 'testing.py'), ('telegram_patterns.ptb', PY / 'ptb.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        names = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == '__all__' for t in node.targets))
        result[module] = set(names)
    # cli has no __all__: its public API is what the generated reference lists (doctor); main is the console entry.
    index = json.loads((ROOT / 'catalog/api-reference-index.json').read_text(encoding='utf-8'))
    result['telegram_patterns.cli'] = {item['name'] for item in index['symbols'] if item['module'] == 'telegram_patterns.cli'}
    return result


def typescript_exports() -> dict[str, set[str]]:
    """Value and type exports of the package root and of each framework subpath."""
    def names(text: str) -> set[str]:
        found = set()
        for group in re.findall(r'export\s+(?:type\s+)?\{([^}]*)\}', text):
            found |= {part.strip().split(' as ')[-1].strip() for part in group.split(',') if part.strip()}
        found |= set(re.findall(r'^export\s+(?:async\s+)?(?:function|class|interface|type|const)\s+(\w+)', text, re.M))
        return found
    result = {TS_ROOT: names((TS / 'index.ts').read_text(encoding='utf-8'))}
    for framework in ('react', 'vue', 'svelte'):
        result[f'{TS_ROOT}/{framework}'] = names((TS / f'frameworks/{framework}.ts').read_text(encoding='utf-8'))
    return result


def catalogued(component: dict) -> set[tuple[str, str]]:
    """(module, name) pairs of a component's `import` text; CLI command segments are skipped."""
    pairs = set()
    for segment in component['import'].split(';'):
        segment = segment.strip()
        if not segment or segment.startswith('telegram-patterns '):
            continue
        if component['language'] == 'typescript':
            module, _, rest = segment.rpartition(':') if segment.startswith('@') else (TS_ROOT, '', segment)
            pairs |= {(module.strip(), name.strip()) for name in rest.split(',') if name.strip()}
            continue
        module = None
        for item in (part.strip() for part in segment.split(',')):
            if not item:
                continue
            if item.startswith('telegram_patterns.'):
                module, _, name = item.rpartition('.')
            else:
                name = item
            pairs.add((module, name))
    return pairs


class ComponentCatalogTests(unittest.TestCase):
    def test_every_catalog_import_is_a_real_export(self):
        exports = {**python_exports(), **typescript_exports()}
        for component in CATALOG['components']:
            for module, name in sorted(catalogued(component)):
                with self.subTest(component=component['id'], symbol=f'{module}.{name}'):
                    self.assertIn(module, exports, 'unknown module')
                    self.assertIn(name, exports[module], 'not exported')

    def test_every_public_export_is_catalogued(self):
        mentioned = set().union(*(catalogued(component) for component in CATALOG['components']))
        for module, names in {**python_exports(), **typescript_exports()}.items():
            missing = sorted(name for name in names if (module, name) not in mentioned)
            with self.subTest(module=module):
                self.assertEqual(missing, [], f'add to a component import in components.json: {missing}')

    def test_versions_agree_in_every_manifest(self):
        version = CATALOG['library_version']
        pyproject = tomllib.loads((ROOT / 'packages/python/pyproject.toml').read_text(encoding='utf-8'))['project']['version']
        init = re.search(r"^__version__ = '([^']+)'", (PY / '__init__.py').read_text(encoding='utf-8'), re.M).group(1)
        typescript = json.loads((ROOT / 'packages/typescript/package.json').read_text(encoding='utf-8'))
        recipes = json.loads((PY / 'resources/recipes.json').read_text(encoding='utf-8'))['library_version']
        index = json.loads((ROOT / 'catalog/api-reference-index.json').read_text(encoding='utf-8'))['library_version']
        lock = json.loads((ROOT / 'package-lock.json').read_text(encoding='utf-8'))['packages']['packages/typescript']['version']
        found = {'pyproject.toml': pyproject, '__version__': init, 'package.json': typescript['version'], 'recipes.json': recipes,
                 'api-reference-index.json': index, 'package-lock.json': lock}
        self.assertEqual(found, dict.fromkeys(found, version))
        minor = '.'.join(version.split('.')[:2])
        upper = f"{version.split('.')[0]}.{int(version.split('.')[1]) + 1}"
        for example in ('mini-app', 'shop/frontend'):
            manifest = json.loads((ROOT / f'examples/{example}/package.json').read_text(encoding='utf-8'))
            with self.subTest(example=example):
                self.assertEqual(manifest['dependencies'][TS_ROOT], version)
        for example in ('service-bot', 'group-bot', 'shop'):
            text = (ROOT / f'examples/{example}/pyproject.toml').read_text(encoding='utf-8')
            with self.subTest(example=example):
                self.assertIn(f'>={minor},<{upper}', text)
        for skill in sorted((ROOT / '.agents/skills').glob('*/SKILL.md')):
            with self.subTest(skill=skill.parent.name):
                self.assertIn(f'version: "{version}"', skill.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
