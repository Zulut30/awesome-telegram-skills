"""Build docs/README.md, the documentation map, from docs/navigation.json and check the structure.

    python scripts/build_docs_map.py          # write docs/README.md
    python scripts/build_docs_map.py --check  # fail when docs/README.md or the structure is out of date

Every user page under docs/ (outside docs/internal) is listed exactly once in one of four sections with a goal;
internal plans, reviews and research stay in docs/internal and are never listed; at most max_sidebar_pages
entries are marked nav for the site sidebar; every listed path exists.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'docs/navigation.json'
OUTPUT = ROOT / 'docs/README.md'
SECTIONS = ('learn', 'how-to', 'reference', 'explanation')


def user_documents(root: Path) -> set[str]:
    docs = root / 'docs'
    return {path.relative_to(root).as_posix() for path in docs.rglob('*.md')
            if not path.relative_to(docs).as_posix().startswith('internal/') and path != root / 'docs/README.md'}


def problems(manifest: dict, root: Path) -> list[str]:
    found: list[str] = []
    if [section['id'] for section in manifest['sections']] != list(SECTIONS):
        found.append(f'sections must be {", ".join(SECTIONS)} in this order')
    entries = [entry for section in manifest['sections'] for entry in section['pages']]
    paths = [entry['path'] for entry in entries]
    for path in sorted({path for path in paths if paths.count(path) > 1}):
        found.append(f'{path}: listed more than once')
    for entry in entries:
        if entry['path'] != 'docs/README.md' and not (root / entry['path']).exists():  # README.md is the output
            found.append(f"{entry['path']}: does not exist")
        if entry['path'].startswith('docs/internal/'):
            found.append(f"{entry['path']}: internal material must not be listed")
        goal = entry.get('goal', '')
        if not entry.get('title') or len(goal) < 20 or not goal.endswith('.'):
            found.append(f"{entry['path']}: needs a title and a one-sentence goal")
    for path in sorted(user_documents(root) - set(paths)):
        found.append(f'{path}: user page without a section and goal (or move it to docs/internal)')
    sidebar = sum(1 for entry in entries if entry.get('nav'))
    if sidebar > manifest['max_sidebar_pages']:
        found.append(f"{sidebar} sidebar pages, at most {manifest['max_sidebar_pages']}")
    return found


def render(manifest: dict) -> str:
    lines = ['# Карта документации', '',
             'Каждая страница отвечает на один вопрос. Разделы: **Обучение** — пройти путь от нуля до результата, '
             '**Как сделать** — решить конкретную задачу, **Справочник** — найти точные факты, **Объяснения** — понять, '
             'почему устроено так. Пункты со звездочкой есть в меню сайта.', '']
    for section in manifest['sections']:
        lines += [f"## {section['title']}", '', '| Страница | Цель |', '| --- | --- |']
        for entry in section['pages']:
            if entry['path'] == 'docs/README.md':
                continue
            link = posixpath.relpath(entry['path'], 'docs')
            star = ' ★' if entry.get('nav') else ''
            lines.append(f"| [{entry['title']}]({link}){star} | {entry['goal']} |")
        lines.append('')
    internal = posixpath.relpath(manifest['internal_index'], 'docs')
    lines += ['## Внутренние материалы', '',
              f'Планы, реестры выполнения, исследования и обзоры прошлых версий собраны в [docs/internal]({internal}). '
              'Они не нужны для работы с проектом и не входят в меню и поиск сайта.', '',
              'Карта собирается из `docs/navigation.json` командой `python scripts/build_docs_map.py`.', '']
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='fail instead of writing when something is out of date')
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    found = problems(manifest, ROOT)
    text = render(manifest)
    current = OUTPUT.read_text(encoding='utf-8') if OUTPUT.exists() else None
    if args.check and current != text:
        found.append('docs/README.md is out of date: run python scripts/build_docs_map.py')
    if found:
        sys.stderr.write('\n'.join(found) + '\n')
        return 1
    if not args.check and current != text:
        OUTPUT.write_text(text, encoding='utf-8')
    entries = [entry for section in manifest['sections'] for entry in section['pages']]
    print(json.dumps({'passed': True, 'pages': len(entries), 'sidebar': sum(1 for entry in entries if entry.get('nav')),
                      'mode': 'check' if args.check else 'write'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
