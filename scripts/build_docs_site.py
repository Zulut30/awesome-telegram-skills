"""Build a self-contained Pages documentation site from an accepted source tree."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
from tempfile import TemporaryDirectory
import tomllib
from urllib.parse import quote, unquote, urlsplit

import markdown
from markdown.extensions.toc import slugify_unicode
import yaml

REPOSITORY = 'https://github.com/Zulut30/awesome-telegram-skills'
SITE_URL = 'https://zulut30.github.io/awesome-telegram-skills/'
ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', '.venv', 'node_modules', 'output', '__pycache__', 'dist', 'build', '.mypy_cache'}


def text(value: object) -> str:
    return escape(str(value), quote=True)


def relative(target: str, route: str) -> str:
    return posixpath.relpath(target, posixpath.dirname(route) or '.')


def title_and_body(raw: str, fallback: str) -> tuple[str, str]:
    match = re.search(r'^# (.+)$', raw, re.M)
    if not match:
        return fallback, raw
    return match.group(1).strip(), raw[:match.start()] + raw[match.end():].lstrip('\r\n')


def category(name: str) -> str:
    if name.startswith('telegram-mini-app-'):
        return 'Mini Apps'
    if any(word in name for word in ('payments', 'payment-provider', 'cryptopay', 'platega', 'yookassa', 'subscription')):
        return 'Платежи'
    if any(word in name for word in ('profiles', 'user-client', 'web-login', 'localization')):
        return 'Аккаунты и языки'
    if name in {'telegram-project-planner', 'telegram-code-patterns', 'telegram-library-selection', 'telegram-testing', 'telegram-security-review', 'telegram-deploy', 'telegram-debugging', 'telegram-observability', 'telegram-python-backend', 'telegram-admin-panel', 'telegram-media-processing'}:
        return 'Разработка и качество'
    return 'Боты и Bot API'


def source_files(source: Path) -> list[Path]:
    files = []
    for directory, subdirs, names in os.walk(source, followlinks=False):
        subdirs[:] = sorted(name for name in subdirs if name not in EXCLUDED and not name.endswith('.egg-info'))
        files.extend(Path(directory) / name for name in names
                     if name not in EXCLUDED and not name.endswith('.egg-info') and (Path(directory) / name).is_file())
    return sorted(files)


def route_for(name: str) -> str | None:
    path = PurePosixPath(name)
    if name == 'docs/for-agents.md':
        return 'for-agents/index.html'
    if name == 'README.en.md':
        return 'en/index.html'
    if name == 'packages/python/README.md':
        return 'library/python/index.html'
    if name == 'packages/typescript/README.md':
        return 'library/typescript/index.html'
    if name.startswith('.agents/skills/') and path.suffix == '.md':
        parts = path.parts
        tail = PurePosixPath(*parts[3:]).with_suffix('').as_posix()
        return f'skills/{parts[2]}/index.html' if tail == 'SKILL' else f'skills/{parts[2]}/{tail}/index.html'
    if name.startswith('docs/') and path.suffix == '.md':
        return path.with_suffix('').as_posix() + '/index.html'
    if name.startswith('recipes/') and path.suffix == '.md':
        return 'cookbook/' + PurePosixPath(*path.parts[1:]).with_suffix('').as_posix() + '/index.html'
    if name in {'AGENTS.md', 'CONTRIBUTING.md', 'CHANGELOG.md'}:
        return 'docs/' + {'AGENTS.md': 'repository-instructions', 'CONTRIBUTING.md': 'contributing', 'CHANGELOG.md': 'changelog'}[name] + '/index.html'
    if name == 'assets/readme/README.md':
        return 'docs/visual-assets/index.html'
    return None


@dataclass
class Skill:
    name: str
    title: str
    description: str
    prompt: str
    body: str
    group: str
    source: str


class DocumentHTML(HTMLParser):
    """Sanitize raw Markdown HTML and resolve repository-local resources."""
    allowed = {'p', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'pre', 'code', 'strong', 'em', 'del', 's', 'blockquote', 'hr', 'br', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'div', 'span', 'img', 'details', 'summary', 'kbd', 'sup', 'sub', 'abbr', 'dl', 'dt', 'dd'}
    void = {'br', 'hr', 'img'}
    blocked = {'script', 'style', 'iframe', 'object', 'embed'}

    def __init__(self, source: Path, origin: str, route: str, mapping: dict[str, str]):
        super().__init__(convert_charrefs=True)
        self.source, self.origin, self.route, self.mapping = source, origin, route, mapping
        self.parts: list[str] = []
        self.blocked_depth = 0

    def resolve(self, target: str) -> str | None:
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            return target if parsed.scheme in {'https', 'http', 'mailto'} else None
        if not parsed.path:
            return target
        name = posixpath.normpath(posixpath.join(posixpath.dirname(self.origin), unquote(parsed.path)))
        if name.startswith('../') or name.startswith('/'):
            return None
        destination = self.source / name
        if destination.is_dir():
            return f'{REPOSITORY}/tree/main/{quote(name)}'
        if not destination.is_file():
            raise ValueError(f'{self.origin}: unavailable document link {target}')
        href = relative(self.mapping.get(name, 'sources/' + name), self.route)
        return href + ('?' + parsed.query if parsed.query else '') + ('#' + parsed.fragment if parsed.fragment else '')

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.blocked:
            self.blocked_depth += 1
            return
        if self.blocked_depth or tag not in self.allowed:
            return
        clean = []
        for key, value in attrs:
            if value is None:
                if key == 'open' and tag == 'details':
                    clean.append('open')
                continue
            if key in {'href', 'src'}:
                resolved = self.resolve(value)
                if resolved is not None:
                    clean.append(f'{key}="{text(resolved)}"')
            elif key in {'id', 'class', 'title', 'alt', 'width', 'height', 'colspan', 'rowspan', 'start', 'aria-label'}:
                clean.append(f'{key}="{text(value)}"')
        self.parts.append('<' + tag + (' ' + ' '.join(clean) if clean else '') + '>')

    def handle_endtag(self, tag: str) -> None:
        if tag in self.blocked:
            self.blocked_depth = max(0, self.blocked_depth - 1)
        elif not self.blocked_depth and tag in self.allowed and tag not in self.void:
            self.parts.append(f'</{tag}>')

    def handle_data(self, value: str) -> None:
        if not self.blocked_depth:
            self.parts.append(escape(value))


class Builder:
    def __init__(self, source: Path, output: Path, site_url: str, revision: str):
        self.source, self.output = source, output
        self.site_url, self.revision = site_url.rstrip('/') + '/', revision
        self.files = source_files(source)
        self.mapping = {file.relative_to(source).as_posix(): route_for(file.relative_to(source).as_posix())
                        for file in self.files if route_for(file.relative_to(source).as_posix())}
        self.components = json.loads((source / 'components.json').read_text(encoding='utf-8'))
        self.api = json.loads((source / 'catalog/api-reference-index.json').read_text(encoding='utf-8'))
        self.api_groups = json.loads((source / 'catalog/api-reference.json').read_text(encoding='utf-8'))
        self.recipes = json.loads((source / 'catalog/recipe-gallery.json').read_text(encoding='utf-8'))
        self.version = self.components['library_version']
        versions = [self.api['library_version'], self.api_groups['library_version'], self.recipes['library_version'],
                    tomllib.loads((source / 'packages/python/pyproject.toml').read_text(encoding='utf-8'))['project']['version'],
                    json.loads((source / 'packages/typescript/package.json').read_text(encoding='utf-8'))['version']]
        if any(version != self.version for version in versions):
            raise ValueError('Documentation source versions disagree')
        accepted = [json.loads(file.read_text(encoding='utf-8')) for file in (source / 'docs/v1-checks').glob('[0-9][0-9][0-9].json')]
        if not any(item.get('version') == self.version and item.get('passed') is True for item in accepted):
            raise ValueError('Publish documentation only for an accepted version; use a clean source snapshot')
        self.skills: list[Skill] = []
        for entry in sorted((source / '.agents/skills').glob('*/SKILL.md')):
            raw = entry.read_text(encoding='utf-8')
            match = re.match(r'\A---\n(.*?)\n---\n', raw, re.S)
            if not match:
                raise ValueError(f'Invalid skill frontmatter: {entry}')
            meta = yaml.safe_load(match.group(1))
            interface = yaml.safe_load((entry.parent / 'agents/openai.yaml').read_text(encoding='utf-8'))['interface']
            if meta['name'] != entry.parent.name:
                raise ValueError('Skill name and folder disagree')
            self.skills.append(Skill(meta['name'], interface['display_name'], meta['description'], interface['default_prompt'], raw[match.end():], category(meta['name']), entry.relative_to(source).as_posix()))
        self.search: list[dict[str, str]] = []
        self.pages: dict[str, str] = {}

    def link(self, name: str, route: str) -> str:
        return relative(self.mapping.get(name, 'sources/' + name), route)

    def sidebar(self, route: str) -> str:
        sections = [
            ('Начало', [('index.html', 'Обзор'), ('docs/capability-map/index.html', 'Что умеет бот'), ('docs/quickstart/index.html', 'Первый запуск'), ('for-agents/index.html', 'Для ИИ-агента')]),
            ('Библиотека', [('library/index.html', f"Группы компонентов · {len(self.components['components'])}"), ('library/python/index.html', 'Python / aiogram'), ('library/typescript/index.html', 'TypeScript / Mini Apps'), ('api/index.html', 'Справочник API'), ('docs/public-api/index.html', 'Контракты API'), ('docs/extension-model/index.html', 'Адаптеры проекта')]),
            ('Боты', [('docs/keyboard-layouts/index.html', 'Клавиатуры и кнопки'), ('docs/message-navigation/index.html', 'Экраны и возврат'), ('docs/selection-controls/index.html', 'Выбор и подтверждение'), ('docs/dialog-fields/index.html', 'Формы и поля'), ('docs/dialog-restart/index.html', 'Состояние после рестарта'), ('docs/calendar-slots/index.html', 'Календарь и время'), ('docs/media/index.html', 'Медиа'), ('docs/profiles/index.html', 'Профили'), ('docs/inline-search/index.html', 'Inline-поиск'), ('docs/polls/index.html', 'Опросы'), ('docs/platform-operations/index.html', 'Специальные операции')]),
            ('Практика', [('recipes/index.html', 'Галерея рецептов'), ('docs/service-bot/index.html', 'Сервисный бот'), ('docs/group-bot/index.html', 'Групповой бот'), ('docs/shop-example/index.html', 'Магазин и Mini App'), ('docs/doctor/index.html', 'Диагностика'), ('docs/error-model/index.html', 'Ошибки и восстановление')]),
            ('Качество и развитие', [('docs/support-matrix/index.html', 'Матрица поддержки'), ('docs/telegram-api-boundaries/index.html', 'Границы Telegram API'), ('docs/versioning/index.html', 'Версии и совместимость'), ('docs/library-roadmap-100/index.html', 'План 1.0'), ('docs/evaluation/index.html', 'Сценарии проверки'), ('docs/contributing/index.html', 'Участие в проекте')]),
            ('Все скиллы', [('skills/index.html', f'Каталог · {len(self.skills)}')] + [(f'skills/{skill.name}/index.html', skill.name.removeprefix('telegram-')) for skill in self.skills]),
        ]
        html = []
        for label, links in sections:
            html.append(f'<section class="nav-group"><p class="nav-label">{text(label)}</p>')
            for path, title in links:
                selected = ' aria-current="page"' if route == path else ''
                html.append(f'<a href="{text(relative(path, route))}"{selected}>{text(title)}</a>')
            html.append('</section>')
        return ''.join(html)

    def render(self, route: str, title: str, content: str, *, section: str = 'Документация', toc: str = '', origin: str = '', summary: str = '', search_text: str = '') -> None:
        if route in self.pages:
            raise ValueError(f'Duplicate documentation route: {route}')
        base = relative('index.html', route).removesuffix('index.html') or './'
        assets = lambda name: text(relative('assets/' + name, route))
        def nav(target: str, label: str) -> str:
            current = ' aria-current="page"' if route.startswith(target.split('/')[0] + '/') else ''
            return f'<a href="{text(relative(target, route))}"{current}>{label}</a>'
        source_link = f'{REPOSITORY}/blob/{self.revision if re.fullmatch("[a-f0-9]{40}", self.revision) else "main"}/{quote(origin)}' if origin else REPOSITORY
        description = summary or f'{title}. Документация Awesome Telegram Skills {self.version}.'
        plane = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m3 10 18-7-6 18-4-7-8-4Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="m11 14 10-11" stroke="currentColor" stroke-width="1.7"/></svg>'
        search_icon = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" stroke-width="1.8"/><path d="m15.5 15.5 5 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>'
        tools = f'<div class="page-tools"><span class="badge">{text(self.version)}</span><span>experimental · локальная поставка</span><a href="{text(source_link)}">Исходник ↗</a></div>'
        table_of_contents = f'<aside class="toc" aria-label="На этой странице"><p class="toc-title">На этой странице</p>{toc}</aside>' if toc else ''
        html = f'''<!doctype html><html lang="{'en' if route.startswith(('en/', 'docs/en/')) else 'ru'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{text(title)} — Awesome Telegram Skills</title><meta name="description" content="{text(description[:230])}"><link rel="canonical" href="{text(self.site_url + route.removesuffix('index.html'))}"><meta property="og:title" content="{text(title)} — Awesome Telegram Skills"><meta property="og:description" content="{text(description[:230])}"><meta property="og:image" content="{text(self.site_url + 'assets/cover.png')}"><meta name="theme-color" content="#087eb4"><script src="{assets('theme.js')}"></script><link rel="stylesheet" href="{assets('site.css')}"><script src="{assets('site.js')}" defer></script></head><body data-base="{text(base)}" data-menu="closed"><a class="skip-link" href="#content">К содержимому</a><header class="topbar"><div class="topbar-inner"><a class="brand" href="{text(relative('index.html', route))}"><span class="brand-icon">{plane}</span><span>Awesome Telegram<small>SKILLS &amp; PATTERNS</small></span></a><nav class="topnav" aria-label="Основные разделы">{nav('library/index.html','Библиотека')}{nav('skills/index.html','Скиллы')}{nav('api/index.html','API')}{nav('for-agents/index.html','Для ИИ')}</nav><div class="top-actions"><button type="button" class="search-trigger" data-open-search aria-label="Поиск по документации">{search_icon}<span>Поиск</span><kbd>Ctrl K</kbd></button><button type="button" class="icon-button" data-theme-toggle aria-label="Включить темную тему">◐</button><button type="button" class="menu-button" data-menu-toggle aria-controls="site-navigation" aria-expanded="false" aria-label="Открыть меню">☰</button></div></div></header><button type="button" class="backdrop" data-close-menu aria-label="Закрыть меню"></button><div class="layout"><nav id="site-navigation" class="sidebar" aria-label="Навигация документации"><div class="sidebar-version"><span class="version-dot"></span>Версия {text(self.version)} · experimental</div>{self.sidebar(route)}</nav><main class="main-wrap" id="content" tabindex="-1"><p class="breadcrumbs"><a href="{text(relative('index.html', route))}">Документация</a> / {text(section)}</p><div class="reading-layout"><article class="article">{tools}{content}</article>{table_of_contents}</div><footer class="page-footer"><span>Скиллы и пакеты самостоятельны. SDK/mock/browser ≠ live-приемка.</span><a href="{REPOSITORY}">GitHub ↗</a></footer></main></div><dialog class="search-dialog" id="search-dialog" aria-labelledby="search-title"><div class="search-head"><label><span id="search-title" class="visually-hidden">Поиск по документации</span><input id="doc-search" type="search" autocomplete="off" maxlength="200" placeholder="Задача, скилл или API…" aria-label="Запрос поиска"></label><button type="button" class="icon-button" data-close-search aria-label="Закрыть поиск">×</button></div><p class="search-status" id="search-status" role="status" aria-live="polite"></p><div class="search-results" id="search-results"></div></dialog></body></html>'''
        target = self.output / route
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(html.encode('utf-8'))
        self.pages[route] = title
        self.search.append({'path': route, 'title': title, 'summary': description[:190], 'text': re.sub(r'<[^>]+>', ' ', search_text or content)[:14000]})

    def markdown_page(self, name: str, skill: Skill | None = None) -> None:
        raw = (self.source / name).read_text(encoding='utf-8')
        if skill:
            raw = skill.body
        title, body = title_and_body(raw, PurePosixPath(name).stem)
        md = markdown.Markdown(extensions=['tables', 'fenced_code', 'toc', 'sane_lists'], extension_configs={'toc': {'slugify': slugify_unicode, 'toc_depth': '2-3'}})
        rendered = md.convert(body)
        parser = DocumentHTML(self.source, name, self.mapping[name], self.mapping)
        parser.feed(rendered)
        content = f'<h1>{text(skill.title if skill else title)}</h1>'
        if skill:
            content += f'<p class="lead">{text(skill.description)}</p><h2>Как вызвать</h2><pre><code>{text(skill.prompt)}</code></pre><h2>Инструкции навыка</h2>'
        content += ''.join(parser.parts)
        if skill:
            resources = [file for file in self.files if file.is_relative_to(self.source / '.agents/skills' / skill.name / 'references') and file.suffix == '.md']
            content += '<h2>References этого навыка</h2><p>Открывайте только материал по вашей задаче; каталог переносится целиком.</p><ul class="resource-list">'
            for file in resources:
                source_name = file.relative_to(self.source).as_posix()
                resource_title, _ = title_and_body(file.read_text(encoding='utf-8'), file.stem)
                content += f'<li><a href="{text(self.link(source_name, self.mapping[name]))}">{text(resource_title)}</a></li>'
            content += '</ul>'
        self.render(self.mapping[name], skill.title if skill else title, content, section=skill.name if skill else 'Руководства', toc=md.toc, origin=name, summary=skill.description if skill else '', search_text=raw)

    def card(self, route: str, title: str, description: str, target: str, label: str = 'Открыть →', tag: str = '', extra: str = '') -> str:
        return f'<section class="card">{extra}<span class="card-tag">{text(tag)}</span><h3><a href="{text(relative(target, route))}">{text(title)}</a></h3><p>{text(description)}</p><a href="{text(relative(target, route))}">{text(label)}</a></section>'

    def home(self) -> None:
        route = 'index.html'
        content = f'<p class="eyebrow">Практическая документация</p><h1>От идеи до работающего<br>Telegram-проекта.</h1><p class="lead">Скиллы объясняют решение. Компоненты дают код. Примеры показывают интеграцию — от клавиатуры бота до интерфейса Mini App.</p><div class="buttons"><a class="button" href="docs/quickstart/index.html">Первый запуск</a><a class="button secondary" href="for-agents/index.html">Подключить через ИИ</a></div><div class="hero"><img src="assets/cover.png" alt="Awesome Telegram Skills: Python bots. TypeScript Mini Apps." width="2048" height="768"><div class="hero-bottom"><p>Python для ботов и backend. TypeScript для Mini Apps. Сохраняйте SDK, storage и frontend-фреймворк своего проекта.</p></div></div><div class="stats"><div class="stat"><strong>{len(self.skills)}</strong><span>самостоятельный скилл</span></div><div class="stat"><strong>{len(self.components["components"])}</strong><span>группы компонентов</span></div><div class="stat"><strong>{len(self.recipes["recipes"])}</strong><span>рецептов с контекстом</span></div><div class="stat"><strong>{len(self.api["symbols"])}</strong><span>публичных API-символов</span></div></div><div class="callout"><strong>Принятая версия {text(self.version)}, experimental.</strong> Пакеты поставляются локально. Реальные Telegram-клиенты, устройства и платежные провайдеры проверяются отдельно.</div><h2>Выберите свою задачу</h2><div class="cards">'
        for title, summary, target, tag in [('Разработать бота', 'Кнопки, ввод, формы, меню и события через Python/aiogram.', 'library/python/index.html', 'Python'), ('Собрать Mini App', 'Темы, safe areas, bridge, API и scoped черновики.', 'library/typescript/index.html', 'TypeScript'), ('Выбрать скилл', 'Когда использовать, как вызвать, какой результат получить.', 'skills/index.html', 'AI skills'), ('Найти готовый рецепт', 'Ряды 2/3, цвета, контекст, код и команды offline-проверки.', 'recipes/index.html', 'Cookbook'), ('Проверить API', 'Полный import, runtime/type, пример и ограничения.', 'api/index.html', 'Reference'), ('Передать библиотеку агенту', 'Установка, выбор компонента, интеграция и приемка результата.', 'for-agents/index.html', 'Для ИИ')]:
            content += self.card(route, title, summary, target, tag=tag)
        content += '</div><h2>Глубже в библиотеку</h2><p>Полные контракты, ошибки, расширение, матрица поддержки и план 1.0 находятся в меню. Исторические результаты отмечены своей версией; каталог API не объявляет все Telegram-сценарии готовыми к production.</p>'
        self.render(route, 'Документация Telegram Skills и библиотеки', content, section='Обзор')

    def skill_index(self) -> None:
        route = 'skills/index.html'
        groups = sorted({skill.group for skill in self.skills})
        filters = '<form class="filter-bar" data-filter onsubmit="return false"><label>Найти скилл<input type="search" aria-label="Найти скилл" placeholder="Кнопки, профиль, Mini App…"></label><label>Область<select aria-label="Область навыка"><option value="">Все области</option>' + ''.join(f'<option>{text(group)}</option>' for group in groups) + '</select></label></form><p class="filter-result" data-filter-status role="status" aria-live="polite"></p>'
        content = f'<h1>Скилл под вашу задачу.</h1><p class="lead">{len(self.skills)} самостоятельный навык: назначение, вызов, порядок работы и локальные references. Выбирайте узкий навык; полный набор не нужен для одного изменения.</p>' + filters + '<div class="cards">'
        for skill in self.skills:
            content += f'<section class="card" data-search-card="{text(skill.name + " " + skill.title + " " + skill.description)}" data-category="{text(skill.group)}"><span class="card-tag">{text(skill.group)}</span><h2 class="skill-heading"><a href="{text(relative("skills/" + skill.name + "/index.html", route))}">{text(skill.name)}</a></h2><p>{text(skill.description)}</p><div class="card-footer"><span>{text(skill.title)}</span><a href="{text(relative("skills/" + skill.name + "/index.html", route))}">Подробнее →</a></div></section>'
        content += '<p class="nothing" data-filter-empty hidden>Ничего не найдено. Попробуйте другую задачу или область.</p></div>'
        self.render(route, 'Каталог всех скиллов', content, section='Скиллы')

    def library(self) -> None:
        route = 'library/index.html'
        content = '<h1>Компоненты вместо повторяющегося кода.</h1><p class="lead">Два независимых локальных пакета. Выберите компонент по задаче, подтвердите публичный API и добавьте бизнес-правила проекта.</p><div class="buttons"><a class="button" href="python/index.html">Python-пакет</a><a class="button secondary" href="typescript/index.html">TypeScript-пакет</a></div><h2>Каталог компонентов</h2><div class="cards">'
        for item in self.components['components']:
            target = f'library/components/{item["id"]}/index.html'
            names = {name.strip().rsplit('.', 1)[-1] for name in item['import'].split(',')}
            symbols = [symbol for symbol in self.api['symbols'] if symbol['name'] in names and (symbol['module'].startswith('telegram_patterns') if item['language'] == 'python' else not symbol['module'].startswith('telegram_patterns'))]
            group_ids = {symbol['recipe'].removeprefix('ref.') for symbol in symbols}
            group_titles = [group['title'] for group in self.api_groups['groups'] if group['id'] in group_ids]
            intent = item.get('intent') or '; '.join(group_titles) or item['id']
            boundaries = item.get('boundaries', item.get('contracts', []))
            content += self.card(route, item['id'], intent, target, tag=item['language'], extra=f'<span class="badge">{text(item["maturity"])}</span> ')
            imports = '\n'.join(dict.fromkeys(symbol['import'] for symbol in symbols)) or item['import']
            examples = list(dict.fromkeys(([item['example']] if item.get('example') else []) + [symbol['example'] for symbol in symbols]))
            example_links = ''.join(f'<li><a href="{text(self.link(name, target))}">{text(name)}</a></li>' for name in examples)
            page = f'<h1>{text(item["id"])}</h1><p class="lead">{text(intent)}</p><h2>Публичная точка входа</h2><pre><code>{text(imports)}</code></pre><p>Импорты взяты из <a href="{relative("api/index.html", target)}">публичного индекса API</a>; для TypeScript различайте runtime и type exports.</p><h2>Пример и исходник</h2><ul>{example_links}<li><a href="{text(self.link(item["source"], target))}">{text(item["source"])}</a></li></ul><h2>Контракт и ограничения</h2><ul>' + ''.join(f'<li>{text(boundary)}</li>' for boundary in boundaries) + '</ul><p>Статус: <strong>' + text(item['maturity']) + '</strong>. ' + text(item.get('maturity_scope', '')) + '</p><p><a href="' + relative('docs/public-api/index.html', target) + '">Параметры, результаты, ошибки и владение ресурсами →</a></p>'
            self.render(target, item['id'], page, section='Компоненты', origin='components.json', summary=intent)
        content += '</div>'
        self.render(route, 'Каталог библиотеки', content, section='Библиотека')

    def api_index(self) -> None:
        route = 'api/index.html'
        modules = sorted({item['module'] for item in self.api['symbols']})
        content = f'<h1>Публичный API.</h1><p class="lead">{len(self.api["symbols"])} Python/TypeScript-символов: точный import, назначение, runtime/type и проверяемый пример. API-контракты и примеры читаются отдельно от Telegram method snapshot.</p><div class="buttons"><a class="button secondary" href="{relative("docs/api-reference-core/index.html", route)}">Python core</a><a class="button secondary" href="{relative("docs/api-reference-bot/index.html", route)}">Bot / aiogram</a><a class="button secondary" href="{relative("docs/api-reference-typescript/index.html", route)}">TypeScript</a></div><form class="filter-bar" data-filter onsubmit="return false"><label>Имя или задача<input type="search" aria-label="Найти API" placeholder="action_menu, SQLiteOnce, TelegramBridge…"></label><label>Модуль<select aria-label="Модуль API"><option value="">Все модули</option>' + ''.join(f'<option>{text(module)}</option>' for module in modules) + '</select></label></form><p class="filter-result" data-filter-status role="status" aria-live="polite"></p><div class="cards">'
        for item in self.api['symbols']:
            anchor = re.sub(r'[^a-z0-9-]', '-', (item['module'] + '-' + item['name']).lower()).strip('-')
            content += f'<section class="card api-card" id="{text(anchor)}" data-search-card="{text(item["name"] + " " + item["module"] + " " + item["intent"])}" data-category="{text(item["module"])}"><span class="card-tag">{text(item["kind"])} · {text(item["module"])}</span><h2>{text(item["name"])}</h2><p>{text(item["intent"])}</p><pre><code>{text(item["import"])}</code></pre><p class="limits">{text(item["limits"])}</p><a href="{text(self.link(item["example"], route))}">Полный пример →</a></section>'
            self.search.append({'title': item['name'] + ' · ' + item['module'], 'path': route + '#' + anchor, 'summary': item['intent'], 'text': item['intent'] + ' ' + item['import']})
        content += '<p class="nothing" data-filter-empty hidden>Такой API не найден. Сверьте установленную версию и каталог.</p></div>'
        self.render(route, 'Справочник публичного API', content, section='API', origin='catalog/api-reference-index.json')

    def build(self) -> dict:
        self.output.mkdir(parents=True, exist_ok=False)
        for file in self.files:
            name = file.relative_to(self.source)
            if file.is_symlink() or not file.resolve().is_relative_to(self.source):
                raise ValueError('Source symlinks are not published')
            target = self.output / 'sources' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, target)
        shutil.copytree(self.source / 'site/assets', self.output / 'assets')
        shutil.copyfile(self.source / 'assets/readme/cover.png', self.output / 'assets/cover.png')
        skill_by_source = {skill.source: skill for skill in self.skills}
        for name in self.mapping:
            self.markdown_page(name, skill_by_source.get(name))
        self.home()
        self.skill_index()
        self.library()
        self.api_index()
        shutil.copytree(self.source / 'gallery', self.output / 'recipes')
        gallery = self.output / 'recipes/index.html'
        gallery.write_bytes(gallery.read_bytes().replace(b'data-repository-base="../"', b'data-repository-base="files/"'))
        shutil.copyfile(self.source / 'catalog/recipe-gallery.json', self.output / 'recipes/recipes.json')
        for name in {name for item in self.recipes['recipes'] for name in (*item['source_files'], *item['check_files'])}:
            source = (self.source / name).resolve()
            if not source.is_relative_to(self.source) or not source.is_file():
                raise ValueError('Gallery source file is outside the source snapshot')
            target = self.output / 'recipes/files' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        self.pages['recipes/index.html'] = 'Галерея рецептов'
        self.search.append({'title': 'Галерея рецептов', 'path': 'recipes/index.html', 'summary': 'Ряды 2/3, цвета, формы, native API и offline fixtures', 'text': ' '.join(item['title'] + ' ' + item['summary'] for item in self.recipes['recipes'])})
        (self.output / 'search-index.json').write_bytes(json.dumps(self.search, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        (self.output / 'components.json').write_bytes((self.source / 'components.json').read_bytes())
        (self.output / 'api-reference-index.json').write_bytes((self.source / 'catalog/api-reference-index.json').read_bytes())
        (self.output / '.nojekyll').write_bytes(b'')
        overview = f'# Awesome Telegram Skills\n\n> Самостоятельные AI skills и локальные Python/TypeScript-компоненты для Telegram. Принятая experimental версия {self.version}.\n\nНе считайте сайт установленным пакетом; не загружайте все материалы ради узкой задачи.\n\n## Начать\n\n- [Инструкция для ИИ-агента]({self.site_url}for-agents/): вход, установка, выбор API, требования рецепта и проверка\n- [Каталог скиллов]({self.site_url}skills/): назначение всех {len(self.skills)} навыков\n- [Компоненты]({self.site_url}library/): {len(self.components["components"])} групп\n- [API]({self.site_url}api/): точные импорты и виды exports\n- [Галерея]({self.site_url}recipes/): {len(self.recipes["recipes"])} рецептов\n- [Машинный каталог компонентов]({self.site_url}components.json)\n- [Машинный индекс API]({self.site_url}api-reference-index.json)\n\n## Скиллы\n' + ''.join(f'- [{skill.name}]({self.site_url}skills/{skill.name}/): {skill.description}\n' for skill in self.skills) + f'\n## Полный текст (по необходимости)\n\n- [llms-full.txt]({self.site_url}llms-full.txt): инструкции и guides; не обязателен для одной задачи\n'
        (self.output / 'llms.txt').write_bytes(overview.encode('utf-8'))
        full = overview + '\n\n' + '\n\n'.join(f'---\nSource: {name}\nURL: {self.site_url + route.removesuffix("index.html")}\n\n{(self.source / name).read_text(encoding="utf-8")}' for name, route in self.mapping.items())
        (self.output / 'llms-full.txt').write_bytes(full.encode('utf-8'))
        urls = ''.join(f'<url><loc>{text(self.site_url + route.removesuffix("index.html"))}</loc></url>' for route in sorted(self.pages))
        (self.output / 'sitemap.xml').write_bytes(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'.encode('utf-8'))
        (self.output / 'robots.txt').write_bytes(f'User-agent: *\nAllow: /\nSitemap: {self.site_url}sitemap.xml\n'.encode('utf-8'))
        manifest = {'version': self.version, 'revision': self.revision, 'skills': len(self.skills), 'component_groups': len(self.components['components']), 'api_symbols': len(self.api['symbols']), 'recipes': len(self.recipes['recipes']), 'pages': self.pages, 'files': {file.relative_to(self.output).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest() for file in sorted(self.output.rglob('*')) if file.is_file()}}
        (self.output / 'site-manifest.json').write_bytes(json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--site-url', default=SITE_URL)
    parser.add_argument('--revision', default='preview')
    parser.add_argument('--check', action='store_true', help='Compare a fresh deterministic build without changing existing output')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output == source or source.is_relative_to(output):
        raise ValueError('Output must not contain the source tree')
    if args.check:
        if not output.is_dir():
            raise ValueError('Check requires an existing site')
        before = {file.relative_to(output).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest() for file in output.rglob('*') if file.is_file()}
        with TemporaryDirectory(prefix='telegram-docs-check-') as temporary:
            fresh = Path(temporary) / 'site'
            manifest = Builder(source, fresh, args.site_url, args.revision).build()
            expected = {file.relative_to(fresh).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest() for file in fresh.rglob('*') if file.is_file()}
        if before != expected:
            raise ValueError('Site differs from its source; existing output preserved')
    else:
        if output.exists():
            raise ValueError('Output already exists; choose a new directory or --check. Existing files preserved.')
        manifest = Builder(source, output, args.site_url, args.revision).build()
    print(json.dumps({'passed': True, 'version': manifest['version'], 'skills': manifest['skills'], 'component_groups': manifest['component_groups'], 'api_symbols': manifest['api_symbols'], 'recipes': manifest['recipes'], 'pages': len(manifest['pages']), 'check': args.check, 'output': str(output)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
