"""Fail when a public Python or TypeScript symbol was removed or changed without a CHANGELOG note.

The public API is compared between a base ref and the working tree. Python symbols come
from catalog/api-reference-index.json and are described by inspect (function and
constructor signatures, public methods, Literal values); TypeScript symbols are the
exports of packages/typescript/dist/index.d.ts with their declaration text. Every
removed or changed symbol must be named in backticks in the newest CHANGELOG section.

    python scripts/check_api_compatibility.py --base auto

`auto` uses the pull request base branch on GitHub Actions, otherwise the latest
vX.Y.Z tag reachable from HEAD, otherwise HEAD^. Requires aiogram (Python adapters)
and npm (to build the base TypeScript declarations).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NPM = 'npm.cmd' if os.name == 'nt' else 'npm'

# Runs inside a separate interpreter with the tree's sources first on sys.path.
_PYTHON_SNAPSHOT = r'''
import dataclasses, hashlib, importlib, inspect, json, sys, typing
sys.path.insert(0, sys.argv[1])
index = json.load(open(sys.argv[2], encoding='utf-8'))
def signature(obj):
    try: return str(inspect.signature(obj))
    except (TypeError, ValueError): return None
def describe(obj):
    if inspect.isclass(obj):
        members = {}
        for name, member in sorted(vars(obj).items()):
            if name.startswith('_'): continue
            target = member.__func__ if isinstance(member, (classmethod, staticmethod)) else member
            members[name] = signature(target) if callable(target) else type(member).__name__
        fields = [(f.name, str(f.type), f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING)
                  for f in dataclasses.fields(obj)] if dataclasses.is_dataclass(obj) else None
        bases = [b.__qualname__ for b in obj.__mro__[1:] if b is not object]
        return {'kind': 'class', 'init': signature(obj), 'bases': bases, 'members': members, 'fields': fields}
    if callable(obj) and not typing.get_origin(obj):
        return {'kind': 'function', 'signature': signature(obj)}
    if typing.get_origin(obj) is typing.Literal:
        return {'kind': 'literal', 'values': sorted(map(repr, typing.get_args(obj)))}
    text = repr(obj)
    return {'kind': type(obj).__name__, 'value_sha256': hashlib.sha256(text.encode()).hexdigest()}
result = {}
for symbol in index['symbols']:
    module = symbol['module']
    if module.startswith('@'): continue
    try: obj = getattr(importlib.import_module(module), symbol['name'])
    except (ImportError, AttributeError): continue
    result[f"{module}.{symbol['name']}"] = describe(obj)
print(json.dumps(result, sort_keys=True))
'''


def _git(*arguments: str) -> str:
    return subprocess.run(['git', *arguments], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def resolve_base(base: str) -> str:
    if base != 'auto':
        return _git('rev-parse', f'{base}^{{commit}}')
    target = os.environ.get('GITHUB_BASE_REF')
    if target:
        return _git('merge-base', 'HEAD', f'origin/{target}')
    try:
        return _git('rev-parse', _git('describe', '--tags', '--abbrev=0', '--match', 'v[0-9]*.[0-9]*.[0-9]*', 'HEAD^') + '^{commit}')
    except subprocess.CalledProcessError:
        return _git('rev-parse', 'HEAD^')


def _statements(text: str) -> dict[str, str]:
    """Top-level `export` declarations of a .d.ts file, keyed by exported name."""
    found: dict[str, str] = {}
    for match in re.finditer(r'^export (?:declare )?(?:abstract )?(class|interface|function|const|type|enum) (\w+)', text, re.M):
        start, depth, index = match.start(), 0, match.end()
        braced = match.group(1) in {'class', 'interface', 'enum'}
        while index < len(text):
            char = text[index]
            if char in '{([<':
                depth += 1
            elif char in '})]>':
                depth -= 1
                if braced and char == '}' and depth == 0:
                    index += 1
                    break
            elif char == ';' and depth == 0 and not braced:
                index += 1
                break
            index += 1
        statement = ' '.join(text[start:index].split())
        name = match.group(2)
        found[name] = found[name] + ' ' + statement if name in found else statement  # function overloads
    return found


def typescript_snapshot(package: Path) -> dict[str, str]:
    dist = package / 'dist'
    declarations: dict[str, str] = {}
    for file in sorted(dist.glob('*.d.ts')):
        declarations.update(_statements(file.read_text(encoding='utf-8')))
    index = (dist / 'index.d.ts').read_text(encoding='utf-8')
    exported = [name.strip().split(' as ')[-1] for group in re.findall(r'export (?:type )?\{([^}]*)\}', index)
                for name in group.split(',') if name.strip()]
    return {f'@awesome-telegram/patterns.{name}': declarations.get(name, '<re-export>') for name in exported}


def python_snapshot(tree: Path) -> dict[str, object]:
    done = subprocess.run([sys.executable, '-c', _PYTHON_SNAPSHOT, str(tree / 'packages/python/src'),
                           str(tree / 'catalog/api-reference-index.json')],
                          cwd=tree, check=True, capture_output=True, text=True)
    return json.loads(done.stdout)


def snapshot(tree: Path, *, build: bool) -> dict[str, object]:
    if build:
        subprocess.run([NPM, 'ci', '--no-audit', '--no-fund'], cwd=tree, check=True, stdout=subprocess.DEVNULL)
        subprocess.run([NPM, 'run', 'build', '-w', '@awesome-telegram/patterns'], cwd=tree, check=True, stdout=subprocess.DEVNULL)
    return {**python_snapshot(tree), **typescript_snapshot(tree / 'packages/typescript')}


def newest_changelog_section(text: str) -> str:
    sections = re.split(r'^## ', text, flags=re.M)
    return sections[1] if len(sections) > 1 else ''


def compare(base: dict[str, object], head: dict[str, object], changelog: str) -> dict[str, object]:
    removed = sorted(set(base) - set(head))
    changed = sorted(name for name in set(base) & set(head) if base[name] != head[name])
    added = sorted(set(head) - set(base))
    mentioned = set(re.findall(r'`([^`]+)`', newest_changelog_section(changelog)))
    tokens = {part for item in mentioned for part in re.split(r'[^\w]+', item) if part}
    unmentioned = [name for name in removed + changed if name.rsplit('.', 1)[-1] not in tokens]
    return {'passed': not unmentioned, 'removed': removed, 'changed': changed, 'added': added, 'unmentioned': unmentioned}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default='auto', help='Git ref to compare with, or auto')
    parser.add_argument('--no-build', action='store_true', help='Use the existing packages/typescript/dist of the working tree')
    args = parser.parse_args()
    commit = resolve_base(args.base)
    with tempfile.TemporaryDirectory(prefix='api-base-') as temporary:
        tree = Path(temporary)
        archive = subprocess.run(['git', 'archive', '--format=tar', commit], cwd=ROOT, check=True, capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
            handle.extractall(tree, filter='data')
        base = snapshot(tree, build=True)
    if not args.no_build:
        subprocess.run([NPM, 'run', 'build', '-w', '@awesome-telegram/patterns'], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    head = snapshot(ROOT, build=False)
    report = compare(base, head, (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8'))
    report['base'] = commit
    report['symbols'] = {'base': len(base), 'head': len(head),
                         'head_sha256': hashlib.sha256(json.dumps(head, sort_keys=True).encode()).hexdigest()}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report['unmentioned']:
        print('Removed or changed public symbols must be named in backticks in the newest CHANGELOG section: '
              + ', '.join(report['unmentioned']), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
