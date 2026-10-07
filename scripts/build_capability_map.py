"""Build docs/capability-map.md: every Telegram capability with its skills, components, recipes, checks and gaps.

The curated catalog/capability-map.json names capabilities and matches Bot API and Mini App methods by
regular expressions; the rest is derived from components.json, catalog/recipe-gallery.json and
catalog/telegram-capabilities.json. Every method must belong to exactly one capability and every id must
exist, so a new Telegram method or a removed recipe fails --check instead of hiding a gap.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = 'docs/capability-map.md'
SDK_LABELS = {'aiogram': 'aiogram', 'python-telegram-bot': 'python-telegram-bot', 'python-core': 'без SDK'}
CHECKS = (('sdk', 'SDK-запрос'), ('dispatcher', 'Dispatcher'), ('browser', 'браузер'), ('reference', 'справка'), ('live', 'live'))


def load(root: Path, name: str) -> dict:
    return json.loads((root / name).read_text(encoding='utf-8'))


def build(root: Path = ROOT) -> tuple[str, dict]:
    curated = load(root, 'catalog/capability-map.json')
    telegram = load(root, 'catalog/telegram-capabilities.json')
    components = {item['id']: item for item in load(root, 'components.json')['components']}
    recipes = {item['id']: item for item in load(root, 'catalog/recipe-gallery.json')['recipes']}
    skills = {path.name for path in (root / '.agents/skills').iterdir() if (path / 'SKILL.md').is_file()}
    bot = [method['name'] for method in telegram['bot_api']['methods']]
    mini = [method['path'] for method in telegram['mini_app']['methods']]
    owner: dict[str, str] = {}
    problems: list[str] = []
    rows = []
    for area in curated['areas']:
        for item in area['capabilities']:
            ident = item['id']
            if ident in {row['id'] for row in rows}:
                problems.append(f'{ident}: duplicate capability id')
            for kind, names in (('skill', item['skills']), ('component', item['components']), ('recipe', item['recipes'])):
                known = {'skill': skills, 'component': components, 'recipe': recipes}[kind]
                problems += [f'{ident}: unknown {kind} {name}' for name in names if name not in known]
            methods = [name for name in bot if item.get('bot_api') and re.search(item['bot_api'], name)]
            natives = [path for path in mini if item.get('mini_app') and re.search(item['mini_app'], path)]
            for name in ['Bot API ' + method for method in methods] + ['Mini App ' + path for path in natives]:
                if name in owner:
                    problems.append(f'{name}: in {owner[name]} and {ident}')
                owner[name] = ident
            if (item.get('bot_api') and not methods) or (item.get('mini_app') and not natives):
                problems.append(f'{ident}: a method pattern matches nothing')
            linked = [recipes[name] for name in item['recipes'] if name in recipes]
            levels = {recipe['verification'] for recipe in linked}
            checks = set()
            if any(recipes.get('api.' + name, {}).get('verification') == 'sdk' for name in methods) or 'sdk' in levels:
                checks.add('sdk')
            if 'mock' in levels:
                checks.add('dispatcher')
            if any(components[name]['language'] == 'typescript' for name in item['components'] if name in components):
                checks.add('browser')
            if natives:
                checks.add('reference')
            if 'live' in levels:
                checks.add('live')
            gaps = []
            if not item['components']:
                gaps.append('компонент')
            if not linked:
                gaps.append('сценарий')
            if 'live' not in checks:
                gaps.append('live')
            sdks = [label for key, label in SDK_LABELS.items() if any(recipe['sdk'] == key for recipe in linked)]
            rows.append({'id': ident, 'area': area['title'], 'title': item['title'], 'skills': item['skills'], 'sdks': sdks,
                         'components': item['components'], 'recipes': item['recipes'], 'methods': len(methods),
                         'mini_app_methods': len(natives), 'checks': [key for key, _ in CHECKS if key in checks], 'gaps': gaps})
    problems += [f'Bot API method {name} has no capability' for name in bot if 'Bot API ' + name not in owner]
    problems += [f'Mini App method {name} has no capability' for name in mini if 'Mini App ' + name not in owner]
    if problems:
        raise ValueError('Capability map problems:\n' + '\n'.join(problems))
    summary = {'capabilities': len(rows), 'with_component': sum(bool(row['components']) for row in rows),
               'with_recipe': sum(bool(row['recipes']) for row in rows),
               'dispatcher': sum('dispatcher' in row['checks'] for row in rows),
               'browser': sum('browser' in row['checks'] for row in rows), 'live': sum('live' in row['checks'] for row in rows),
               'bot_api_methods': len(bot), 'mini_app_methods': len(mini)}
    return render(rows, summary, telegram), summary


def render(rows: list[dict], summary: dict, telegram: dict) -> str:
    label = dict(CHECKS)

    def names(values: list[str], prefix: str = '') -> str:
        return ', '.join(f'`{prefix}{value}`' for value in values) or '—'
    lines = ['# Карта возможностей', '',
             '<!-- Generated by scripts/build_capability_map.py from catalog/capability-map.json; edit the catalog, not this page. -->', '',
             'Что умеет бот на этой библиотеке: для каждой возможности Telegram — навык с инструкциями, готовый компонент, '
             'исполняемый сценарий и способ проверки. Пустые клетки и колонка «Пробелы» показывают, чего еще нет.', '',
             f'Возможностей: **{summary["capabilities"]}**. С компонентом — {summary["with_component"]}, со сценарием — '
             f'{summary["with_recipe"]}, проверены на настоящем Dispatcher без сети — {summary["dispatcher"]}, в браузере — '
             f'{summary["browser"]}, live — {summary["live"]}. На карте все {summary["bot_api_methods"]} методов Bot API '
             f'{telegram["bot_api"]["version"]} и {summary["mini_app_methods"]} методов Mini App.', '',
             'SDK — на каких SDK есть исполняемые сценарии. Проверка: **SDK-запрос** — SDK собирает запрос метода без сети; '
             '**Dispatcher** — сценарий проходит на настоящем Dispatcher aiogram или Application python-telegram-bot с заглушкой транспорта; **браузер** — TypeScript-компонент проверен в Chrome; **справка** — фрагмент '
             'Mini App не исполнялся; **live** — проверено на настоящем Telegram. Сценарии запускаются командой '
             '`telegram-patterns run-recipe <id> --offline`.', '']
    area = None
    for row in rows:
        if row['area'] != area:
            area = row['area']
            lines += [f'## {area}', '', '| Возможность | Навыки | Компоненты | Сценарии | SDK | Проверка | Пробелы |',
                      '| --- | --- | --- | --- | --- | --- | --- |']
        lines.append(f'| {row["title"]} | {names(row["skills"])} | {names(row["components"])} | {names(row["recipes"])} | '
                     f'{", ".join(row["sdks"]) or "—"} | '
                     f'{", ".join(label[key] for key in row["checks"]) or "—"} | {", ".join(row["gaps"]) or "—"} |')
        if row is rows[-1] or rows[rows.index(row) + 1]['area'] != area:
            lines.append('')
    lines += ['## Пробелы', '']
    for gap, text in (('компонент', 'Без готового компонента'), ('сценарий', 'Без исполняемого сценария')):
        missing = [row['title'] for row in rows if gap in row['gaps']]
        lines.append(f'- {text} ({len(missing)}): ' + ('; '.join(missing) if missing else 'нет') + '.')
    live = [row['title'] for row in rows if 'live' in row['gaps']]
    lines.append(f'- Без live-проверки: {len(live)} из {len(rows)}. Офлайн-проверки не подтверждают доставку, права и поведение клиентов Telegram.')
    lines += ['', 'Источники данных: [каталог возможностей](../catalog/capability-map.json), [компоненты](../components.json), '
              '[рецепты](../catalog/recipe-gallery.json), [методы Telegram](../catalog/telegram-capabilities.json).', '']
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='fail when docs/capability-map.md differs')
    args = parser.parse_args(argv)
    text, summary = build()
    target = ROOT / OUTPUT
    if args.check:
        if not target.is_file() or target.read_text(encoding='utf-8') != text:
            raise SystemExit(f'{OUTPUT} is out of date; run python scripts/build_capability_map.py')
    else:
        target.write_text(text, encoding='utf-8')
    print(json.dumps({'passed': True, **summary, 'check': args.check}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
