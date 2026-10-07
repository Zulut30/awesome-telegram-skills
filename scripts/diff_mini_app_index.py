"""Compare two Mini Apps indexes by content and describe the change for an issue.

Compared: method paths with their min_version, event names with their min_version and
property names. The page hash and check date change without an API change and are ignored.
Exit code 0 either way; "changed" in the JSON summary (and in GITHUB_OUTPUT) tells the caller.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def content(index: dict) -> dict:
    return {'methods': {item['path']: item['min_version'] for item in index['methods']},
            'events': {item['name']: item['min_version'] for item in index['events']},
            'properties': sorted({f'{item["owner"]}.{item["name"]}' for item in index['properties']})}


def diff(old: dict, new: dict) -> dict:
    before, after = content(old), content(new)
    result = {}
    for kind in ('methods', 'events'):
        result['added_' + kind] = {name: after[kind][name] for name in sorted(set(after[kind]) - set(before[kind]))}
        result['removed_' + kind] = sorted(set(before[kind]) - set(after[kind]))
        result['changed_' + kind] = {name: {'old': before[kind][name], 'new': after[kind][name]}
                                     for name in sorted(set(before[kind]) & set(after[kind]))
                                     if before[kind][name] != after[kind][name]}
    result['added_properties'] = sorted(set(after['properties']) - set(before['properties']))
    result['removed_properties'] = sorted(set(before['properties']) - set(after['properties']))
    result['changed'] = before != after
    digest = json.dumps(result, sort_keys=True, ensure_ascii=False)
    result['digest'] = hashlib.sha256(digest.encode('utf-8')).hexdigest()[:12]
    result['counts'] = {'methods': len(after['methods']), 'events': len(after['events'])}
    return result


def title(result: dict) -> str:
    return f'Mini Apps: изменился индекс методов и событий ({result["digest"]})'


def gate(version: str | None) -> str:
    return f'с версии {version}' if version else 'версия в документации не указана'


def markdown(result: dict, source: str) -> str:
    lines = [f'Еженедельная сверка [{source}]({source}) нашла изменения в индексе Mini Apps.', '',
             f'Сейчас методов: {result["counts"]["methods"]}, событий: {result["counts"]["events"]}.', '']
    for kind, label in (('methods', 'методы'), ('events', 'события')):
        if result['added_' + kind]:
            lines += [f'### Новые {label}', '', *(f'- `{name}` — {gate(version)}' for name, version in result['added_' + kind].items()), '']
        if result['removed_' + kind]:
            lines += [f'### Удаленные {label}', '', *(f'- `{name}`' for name in result['removed_' + kind]), '']
        if result['changed_' + kind]:
            lines += [f'### Изменилась минимальная версия: {label}', '',
                      *(f'- `{name}`: {change["old"]} → {change["new"]}' for name, change in result['changed_' + kind].items()), '']
    if result['added_properties'] or result['removed_properties']:
        lines += ['### Свойства', '', *(f'- добавлено `{name}`' for name in result['added_properties']),
                  *(f'- удалено `{name}`' for name in result['removed_properties']), '']
    lines += ['Что сделать: прочитать раздел документации, задать минимальную версию нового модуля в '
              '`scripts/mini_app_index.py`, пересобрать каталог (`scripts/build_telegram_catalog.py --mini-app-html <сохраненная страница>`), '
              'сверить скиллы Mini App и добавить запись в журнал `docs/sources.md`.']
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('old', type=Path, help='committed index (catalog/mini-app-index.json)')
    parser.add_argument('new', type=Path, help='index built from the current page by scripts/mini_app_index.py')
    parser.add_argument('--markdown', type=Path, help='write the issue body here when something changed')
    parser.add_argument('--github-output', type=Path, help='append changed=, title=, digest= for GitHub Actions')
    args = parser.parse_args()
    old, new = (json.loads(path.read_text(encoding='utf-8')) for path in (args.old, args.new))
    result = diff(old, new)
    if args.markdown and result['changed']:
        args.markdown.write_text(markdown(result, new.get('source', 'https://core.telegram.org/bots/webapps')), encoding='utf-8')
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as output:
            output.write(f'changed={str(result["changed"]).lower()}\ntitle={title(result)}\ndigest={result["digest"]}\n')
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
