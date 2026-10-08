"""Closed, dependency-aware component registry for the bundled new-project CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .errors import ValidationFailure


@dataclass(frozen=True, slots=True)
class StarterComponent:
    id: str
    intent: str
    language: str
    templates: tuple[str, ...]
    requires: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    callback_prefixes: tuple[str, ...] = ()
    min_library_version: str = '0.4.0'


BOT = ('bot', 'bot-mini-app')
MINI = ('bot-mini-app',)
_COMPONENTS = (
    StarterComponent('bot-settings', 'Конфигурация token без dotenv', 'python', BOT),
    StarterComponent('command-replies', 'Команды /start и /help', 'python', BOT, commands=('start', 'help')),
    StarterComponent('action-menu', 'Начальное меню', 'python', BOT),
    StarterComponent(
        'callback-router', 'ACK и публичный ответ кнопки', 'python', BOT, ('action-menu',), callback_prefixes=('act:',)
    ),
    StarterComponent('bot-polling', 'Явный live polling и закрытие сессии', 'python', BOT, ('bot-settings',)),
    StarterComponent('bot-test-transport', 'Offline Dispatcher без сети', 'python', BOT),
    StarterComponent('mini-app-bridge', 'Тема и lifecycle Mini App', 'typescript', MINI),
    StarterComponent('responsive-shell', 'Адаптивная локальная форма', 'typescript', MINI, ('mini-app-bridge',)),
    StarterComponent(
        'native-keyboards',
        '/keyboard: строки 2/3 и цветные кнопки',
        'python',
        BOT,
        ('callback-router',),
        ('starter_keyboard.py',),
        ('keyboard',),
        ('starter-keyboard:',),
    ),
    StarterComponent(
        'paginated-menu',
        '/catalog: страницы публичного каталога',
        'python',
        BOT,
        ('callback-router',),
        ('starter_catalog.py',),
        ('catalog',),
        ('starter-page:', 'starter-item:'),
    ),
    StarterComponent(
        'text-form',
        '/apply: форма с явным подтверждением',
        'python',
        BOT,
        ('command-replies',),
        ('starter_form.py',),
        ('apply', 'back', 'cancel'),
        ('form:starter:',),
        '0.8.0',
    ),
    StarterComponent(
        'update-events', 'Метаданные фаз без содержимого Update', 'python', BOT, (), ('starter_observer.py',)
    ),
    StarterComponent(
        'mini-app-native-api',
        'Haptic capability и полезный fallback',
        'typescript',
        MINI,
        ('mini-app-bridge', 'responsive-shell'),
        ('mini-app/src/starter-native.ts',),
    ),
    StarterComponent(
        'selection-draft',
        'Черновик только публичного ID, без имени/token',
        'typescript',
        MINI,
        ('responsive-shell',),
        ('mini-app/src/starter-draft.ts',),
    ),
    StarterComponent(
        'api-client',
        'Client factory и локальный transport fixture',
        'typescript',
        MINI,
        ('responsive-shell',),
        ('mini-app/src/starter-client.ts',),
        min_library_version='0.9.0',
    ),
)
_BY_ID = {item.id: item for item in _COMPONENTS}
_BASE = ('bot-settings', 'command-replies', 'action-menu', 'callback-router', 'bot-polling', 'bot-test-transport')
CONFLICT_DETAILS = {
    'selection-type': 'Передайте список component IDs; одиночная строка или нестроковые элементы не подходят.',
    'unknown-component': 'Компонент не входит в набор starter. Посмотрите init --list-components; остальные API '
    'подключаются вручную.',
    'component-template': 'Frontend-компонент требует --template bot-mini-app и локальный --typescript tarball.',
    'template': 'Выберите шаблон bot или bot-mini-app.',
    'artifact-version': 'Python wheel и TypeScript tarball должны относиться к одной версии.',
    'missing-typescript': 'Шаблон bot-mini-app требует --typescript с локальным tarball.',
    'unexpected-typescript': '--typescript применим только к bot-mini-app.',
    'missing-input': 'Нужны новый target и --library; для просмотра набора используйте init --list-components.',
    'listing-input': 'Просмотр набора не принимает target, --library, --typescript, --component или --dry-run.',
    'entrypoint-conflict': 'Выбранные blueprint конфликтуют по файлу, команде или callback prefix. Требуется '
    'исправить registry перед созданием проекта.',
    'component-version': 'Предоставленная библиотека старее API выбранного компонента. Сверьте min_library_version '
    'в init --list-components и получите согласованные артефакты.',
}


class StarterConflict(ValidationFailure):
    """Known preflight conflict; messages contain only owned explanations."""

    def __init__(self, reason: str) -> None:
        if reason not in CONFLICT_DETAILS:
            raise ValidationFailure('Unknown starter conflict reason')
        self.reason = reason
        super().__init__(CONFLICT_DETAILS[reason])


def starter_components(template: str | None = None) -> tuple[StarterComponent, ...]:
    """List selectable groups without imports, filesystem reads or code execution."""
    if template is not None and template not in BOT:
        raise StarterConflict('template')
    return tuple(item for item in _COMPONENTS if template is None or template in item.templates)


def resolve_components(template: str, requested: Sequence[str] | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    starter_components(template)
    if requested is not None and (
        isinstance(requested, (str, bytes))
        or not isinstance(requested, Sequence)
        or len(requested) > len(_COMPONENTS) * 4
        or any(not isinstance(item, str) for item in requested)
    ):
        raise StarterConflict('selection-type')
    explicit = set(requested or ())
    if not explicit.issubset(_BY_ID):
        raise StarterConflict('unknown-component')
    selected = set(_BASE)
    if template == 'bot-mini-app':
        selected.update(('mini-app-bridge', 'responsive-shell'))

    def add(key: str) -> None:
        component = _BY_ID[key]
        if template not in component.templates:
            raise StarterConflict('component-template')
        selected.add(key)
        for dependency in component.requires:
            if dependency not in selected:
                add(dependency)

    for key in explicit:
        add(key)
    names: set[str] = set()
    files: set[str] = {
        'app.py',
        'offline.py',
        'readme.md',
        'pyproject.toml',
        '.gitignore',
        '.env.example',
        '.telegram-patterns.json',
        'offline_components.py',
        'mini_app_server.py',
        'mini-app/index.html',
        'mini-app/package.json',
        'mini-app/tsconfig.json',
        'mini-app/vite.config.ts',
        'mini-app/src/main.ts',
    }
    prefixes: list[str] = []
    for component in _COMPONENTS:
        if component.id not in selected:
            continue
        for command in component.commands:
            if command.casefold() in names:
                raise StarterConflict('entrypoint-conflict')
            names.add(command.casefold())
        for filename in component.files:
            if (
                not filename
                or ':' in filename
                or '\\' in filename
                or '\0' in filename
                or any(part in {'', '.', '..'} for part in filename.split('/'))
            ):
                raise StarterConflict('entrypoint-conflict')
            canonical = filename.casefold()
            if any(
                canonical == other or canonical.startswith(other + '/') or other.startswith(canonical + '/')
                for other in files
            ):
                raise StarterConflict('entrypoint-conflict')
            files.add(canonical)
        for prefix in component.callback_prefixes:
            if any(prefix.startswith(previous) or previous.startswith(prefix) for previous in prefixes):
                raise StarterConflict('entrypoint-conflict')
            prefixes.append(prefix)
    return (
        tuple(item.id for item in _COMPONENTS if item.id in explicit),
        tuple(item.id for item in _COMPONENTS if item.id in selected),
    )
