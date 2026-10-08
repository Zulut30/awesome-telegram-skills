"""Build docs/showcase.md from catalog/showcase.json and check every entry.

    python scripts/build_showcase.py               # write docs/showcase.md
    python scripts/build_showcase.py --check       # fail when the page or an entry is invalid (CI)
    python scripts/build_showcase.py --check-links # also open every project link (maintainers, needs network)

A project enters the catalog from the "Проект для витрины" issue form after a maintainer opened its link and saw it
work. Entries name real skills from .agents/skills and real component ids from components.json; the page never
counts the repository's own examples as showcase projects.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'catalog/showcase.json'
PAGE = ROOT / 'docs/showcase.md'
FORM = 'https://github.com/Zulut30/awesome-telegram-skills/issues/new?template=showcase.yml'
KINDS = {'bot': 'Бот', 'mini-app': 'Mini App', 'bot+mini-app': 'Бот и Mini App'}
FIELDS = ('name', 'kind', 'url', 'source', 'description', 'skills', 'components', 'issue', 'added', 'checked_at')
LINK = re.compile(r'https://(t\.me/[A-Za-z][A-Za-z0-9_]{3,31}[A-Za-z0-9](/[A-Za-z0-9_]+)?(\?startapp=[\w-]{1,64})?|[\w.-]+\.[a-z]{2,}(/[^\s|]*)?)')
PRIVATE = re.compile(r'\d{6,}:[A-Za-z0-9_-]{30,}|[\w.+-]+@[\w-]+\.[\w.]+|\+\d[\d ()-]{8,}')


def problems(catalog: dict, root: Path, today: dt.date) -> list[str]:
    skills = {path.parent.name for path in (root / '.agents/skills').glob('*/SKILL.md')}
    components = {item['id'] for item in json.loads((root / 'components.json').read_text(encoding='utf-8'))['components']}
    found, seen = [], set()
    for number, project in enumerate(catalog['projects'], start=1):
        name = project.get('name') or f'#{number}'
        if tuple(project) != FIELDS:
            found.append(f'{name}: fields must be {", ".join(FIELDS)}')
            continue
        if name.lower() in seen:
            found.append(f'{name}: listed more than once')
        seen.add(name.lower())
        if project['kind'] not in KINDS:
            found.append(f'{name}: kind must be one of {", ".join(KINDS)}')
        if not LINK.fullmatch(project['url']):
            found.append(f'{name}: url must be https://t.me/<bot> or another https link')
        if project['source'] is not None and not project['source'].startswith('https://'):
            found.append(f'{name}: source must be an https link or null')
        if not 20 <= len(project['description']) <= 200 or PRIVATE.search(project['description']):
            found.append(f'{name}: description must be 20-200 characters without tokens, e-mail or phone numbers')
        if not project['skills'] and not project['components']:
            found.append(f'{name}: name at least one skill or component the project uses')
        for skill in project['skills']:
            if skill not in skills:
                found.append(f'{name}: unknown skill {skill}')
        for component in project['components']:
            if component not in components:
                found.append(f'{name}: unknown component {component}')
        if not isinstance(project['issue'], int) or project['issue'] < 1:
            found.append(f'{name}: issue must be the number of the showcase issue')
        for field in ('added', 'checked_at'):
            try:
                if dt.date.fromisoformat(project[field]) > today:
                    found.append(f'{name}: {field} is in the future')
            except (TypeError, ValueError):
                found.append(f'{name}: {field} must be an ISO date')
    return found


def render(catalog: dict) -> str:
    projects = catalog['projects']
    lines = ['# Витрина проектов', '',
             'Боты и Mini Apps, которые используют скиллы или библиотеку этого репозитория. Каждый проект добавлен '
             'по заявке автора; мейнтейнер открыл ссылку и убедился, что проект работает, — дата в колонке «Проверено». '
             'Проекты принадлежат своим авторам: репозиторий не отвечает за их данные и платежи.', '',
             f'Принято проектов: **{len(projects)}**. Цель — не меньше {catalog["target"]} работающих проектов.', '']
    if projects:
        lines += ['| Проект | Тип | Что делает | Скиллы и компоненты | Проверено |', '| --- | --- | --- | --- | --- |']
        for project in sorted(projects, key=lambda item: item['name'].lower()):
            source = f" · [код]({project['source']})" if project['source'] else ''
            used = ', '.join([f'`{skill}`' for skill in project['skills']] + [f'`{component}`' for component in project['components']])
            lines.append(f"| [{project['name']}]({project['url']}){source} | {KINDS[project['kind']]} | {project['description']} | "
                         f"{used} | {project['checked_at']} |")
    else:
        lines.append('Пока ни один внешний проект не прошел проверку. Ваш может стать первым.')
    lines += ['', '## Добавить свой проект', '',
              f'1. Откройте [форму «Проект для витрины»]({FORM}) и заполните название, ссылку на бота или Mini App, '
              'какие скиллы и компоненты используются и короткое описание.',
              '2. Мейнтейнер откроет ссылку в Telegram. Проект должен работать для любого пользователя без приглашения; '
              'тестовое окружение Telegram не подходит.',
              '3. После проверки проект попадет в `catalog/showcase.json`, страница пересоберется командой '
              '`python scripts/build_showcase.py`. Ссылки периодически проверяются; неработающий проект убирается '
              'с пометкой в issue.', '',
              'Не указывайте в заявке токены, телефоны и личные данные пользователей.', '',
              '## Примеры из репозитория', '',
              'Эти приложения входят в репозиторий и проверяются в CI без сети. Они показывают, как собрать проект, '
              'но не считаются проектами витрины: у них нет публичного бота.', '',
              '- [Сервисный бот](service-bot.md) — запись на услугу и напоминание.',
              '- [Групповой бот](group-bot.md) — темы, права, заявки и модерация.',
              '- [Магазин и Mini App](shop-example.md) — каталог, заказ и оплата Telegram Stars.', '']
    return '\n'.join(lines)


def check_links(catalog: dict) -> list[str]:
    found = []
    for project in catalog['projects']:
        request = urllib.request.Request(project['url'], headers={'User-Agent': 'awesome-telegram-skills showcase check'})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - https links only
                if response.status >= 400:
                    found.append(f"{project['name']}: {project['url']} answered {response.status}")
        except OSError as error:
            found.append(f"{project['name']}: {project['url']} unreachable ({error})")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='fail instead of writing when something is out of date')
    parser.add_argument('--check-links', action='store_true', help='open every project link (network)')
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    found = problems(catalog, ROOT, dt.date.today())
    text = render(catalog)
    if args.check and (not PAGE.exists() or PAGE.read_text(encoding='utf-8') != text):
        found.append('docs/showcase.md is out of date: run python scripts/build_showcase.py')
    if args.check_links:
        found += check_links(catalog)
    if found:
        sys.stderr.write('\n'.join(found) + '\n')
        return 1
    if not args.check and (not PAGE.exists() or PAGE.read_text(encoding='utf-8') != text):
        PAGE.write_text(text, encoding='utf-8')
    print(json.dumps({'passed': True, 'projects': len(catalog['projects']), 'target': catalog['target'],
                      'mode': 'check' if args.check else 'write'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
