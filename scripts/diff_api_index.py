"""Compare two Bot API indexes by content and describe the change for an issue.

The HTML SHA-256 changes with every page rebuild even when the API is the same, so only the
version, the method and type names and their field names are compared. Exit code 0 either way;
"changed" in the JSON summary (and in GITHUB_OUTPUT with --github-output) tells the caller.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def content(index: dict) -> dict:
    """The part of an index that describes the API itself."""
    entries = {}
    for kind in ('methods', 'types'):
        for item in index[kind]:
            entries[item['name']] = {'kind': item['kind'], 'fields': sorted(item['fields'])}  # table order is not API
    return {'version': index.get('bot_api_version'), 'entries': entries}


def diff(old: dict, new: dict) -> dict:
    before, after = content(old), content(new)
    names_before, names_after = set(before['entries']), set(after['entries'])

    def named(names: set[str], side: dict, kind: str) -> list[str]:
        return sorted(name for name in names if side['entries'][name]['kind'] == kind)

    fields = {}
    for name in sorted(names_before & names_after):
        old_fields, new_fields = before['entries'][name]['fields'], after['entries'][name]['fields']
        added = [field for field in new_fields if field not in old_fields]
        removed = [field for field in old_fields if field not in new_fields]
        if added or removed:
            fields[name] = {'added': added, 'removed': removed}
    result = {
        'version': {'old': before['version'], 'new': after['version']},
        'added_methods': named(names_after - names_before, after, 'method'),
        'added_types': named(names_after - names_before, after, 'type'),
        'removed_methods': named(names_before - names_after, before, 'method'),
        'removed_types': named(names_before - names_after, before, 'type'),
        'changed_fields': fields,
        'counts': {'methods': len(new['methods']), 'types': len(new['types'])},
    }
    result['changed'] = before != after
    digest = json.dumps({key: value for key, value in result.items() if key != 'counts'}, sort_keys=True, ensure_ascii=False)
    result['digest'] = hashlib.sha256(digest.encode('utf-8')).hexdigest()[:12]
    return result


def title(result: dict) -> str:
    version = result['version']['new'] or 'без номера'
    return f'Bot API {version}: изменился индекс методов и типов ({result["digest"]})'


def markdown(result: dict, source: str) -> str:
    version = result['version']
    lines = [f'Еженедельная сверка [{source}]({source}) нашла изменения в индексе Bot API.', '',
             f'- Версия: {version["old"]} → {version["new"]}',
             f'- Сейчас методов: {result["counts"]["methods"]}, типов: {result["counts"]["types"]}', '']
    for key, label in (('added_methods', 'Новые методы'), ('added_types', 'Новые типы'),
                       ('removed_methods', 'Удаленные методы'), ('removed_types', 'Удаленные типы')):
        if result[key]:
            lines += [f'### {label}', '', *(f'- [`{name}`]({source}#{name.lower()})' for name in result[key]), '']
    if result['changed_fields']:
        lines += ['### Изменились поля', '']
        for name, change in result['changed_fields'].items():
            parts = []
            if change['added']:
                parts.append('добавлены ' + ', '.join(f'`{field}`' for field in change['added']))
            if change['removed']:
                parts.append('удалены ' + ', '.join(f'`{field}`' for field in change['removed']))
            lines.append(f'- [`{name}`]({source}#{name.lower()}): ' + '; '.join(parts))
        lines.append('')
    lines += ['Что сделать: обновить `.agents/skills/telegram-bot-api/references/api-index.json` '
              '(`python .agents/skills/telegram-bot-api/scripts/update_api_index.py`), проверить поддержку в aiogram, '
              'пересобрать каталоги и сверить затронутые скиллы, затем добавить запись в журнал `docs/sources.md`.']
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('old', type=Path, help='committed index')
    parser.add_argument('new', type=Path, help='freshly built index')
    parser.add_argument('--markdown', type=Path, help='write the issue body here when something changed')
    parser.add_argument('--github-output', type=Path, help='append changed=, title= for GitHub Actions')
    args = parser.parse_args()
    old, new = (json.loads(path.read_text(encoding='utf-8')) for path in (args.old, args.new))
    result = diff(old, new)
    if args.markdown and result['changed']:
        args.markdown.write_text(markdown(result, new.get('source', 'https://core.telegram.org/bots/api')), encoding='utf-8')
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as output:
            output.write(f'changed={str(result["changed"]).lower()}\ntitle={title(result)}\ndigest={result["digest"]}\n')
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
