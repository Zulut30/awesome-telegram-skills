"""Compare two Mini Apps indexes by content and describe the change for an issue.

Compared: method paths with their min_version and signature, event names with their min_version and
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
            'signatures': {item['path']: item['signature'] for item in index['methods']},
            'callback_errors': {item['path']: item['callback_error'] for item in index['methods'] if item.get('callback_error')},
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
    result['changed_signatures'] = {name: {'old': before['signatures'][name], 'new': after['signatures'][name]}
                                    for name in sorted(set(before['signatures']) & set(after['signatures']))
                                    if before['signatures'][name] != after['signatures'][name]}
    result['changed_callback_errors'] = {name: {'old': before['callback_errors'].get(name), 'new': after['callback_errors'].get(name)}
                                         for name in sorted(set(before['callback_errors']) | set(after['callback_errors']))
                                         if before['callback_errors'].get(name) != after['callback_errors'].get(name)}
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
    if result['changed_signatures']:
        lines += ['### Изменились сигнатуры', '',
                  *(f'- `{name}`: `{change["old"]}` → `{change["new"]}`' for name, change in result['changed_signatures'].items()), '']
    if result['changed_callback_errors']:
        lines += ['### Изменились поля ошибки callback', '',
                  *(f'- `{name}`: `{json.dumps(change["old"], ensure_ascii=False)}` → `{json.dumps(change["new"], ensure_ascii=False)}`'
                    for name, change in result['changed_callback_errors'].items()), '']
    lines += [('Что сделать: прочитать раздел документации и сверить SDK. Добавить новый модуль в '
              '`scripts/mini_app_index.py` с опубликованной минимальной версией либо явным `None`, если её нет; '
              'unknown version запрещает вызов через универсальный фасад. Пересобрать каталог '
              '(`scripts/build_telegram_catalog.py --mini-app-html <сохраненная страница>`), '
              'сверить параметры и overloads в `catalog/mini-app-types.json`, выполнить `scripts/build_native_signatures.py`, '
              'сверить скиллы Mini App и добавить запись в журнал `docs/sources.md`.')]
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
        args.markdown.write_text(markdown(result, new.get('source', 'https://core.telegram.org/bots/webapps')), encoding='utf-8', newline='\n')
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8', newline='\n') as output:
            output.write(f'changed={str(result["changed"]).lower()}\ntitle={title(result)}\ndigest={result["digest"]}\n')
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
