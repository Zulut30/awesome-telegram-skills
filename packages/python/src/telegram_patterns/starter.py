"""Create a NEW starter, preserving all existing paths. No install/process/network."""
from __future__ import annotations
from .errors import ValidationFailure, InvalidCompletion
from dataclasses import dataclass
from email.parser import Parser
from importlib.resources import files
import json
import os
from pathlib import Path
from typing import Sequence
import re
import tarfile
import tomllib
import zipfile
from .starter_components import StarterConflict, resolve_components, starter_components


@dataclass(frozen=True, slots=True)
class StarterPlan:
    target: Path
    template: str
    library_version: str
    files: tuple[str, ...]
    created: bool
    components: tuple[str, ...] = ()
    requested_components: tuple[str, ...] = ()


def _linked(path: Path) -> bool:
    """A symlink or junction outside the OS layout; known links are refused.

    Root-owned aliases directly under the filesystem root are trusted: on macOS
    /var, /tmp and /etc point to /private/..., so every temporary path crosses one.
    """
    if not (path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())):
        return False
    try:
        system_alias = (os.name != 'nt' and path.is_absolute() and path.parent == Path(path.anchor)
                        and path.lstat().st_uid == 0)
    except OSError:
        system_alias = False
    return not system_alias


def library_source(path: str | Path) -> tuple[Path, str]:
    source = Path(path).expanduser().resolve(strict=True)
    if source.is_dir():
        if (source / 'packages/python/pyproject.toml').is_file(): source = source / 'packages/python'
        project = tomllib.loads((source / 'pyproject.toml').read_text(encoding='utf-8'))['project']
        name, version = project['name'], project['version']
    elif source.suffix == '.whl':
        with zipfile.ZipFile(source) as archive:
            members = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
            if len(members) != 1 or archive.getinfo(members[0]).file_size > 65536: raise ValidationFailure('Invalid local wheel metadata')
            metadata = Parser().parsestr(archive.read(members[0]).decode('utf-8'))
            name, version = metadata['Name'], metadata['Version']
    else: raise ValidationFailure('Provide a local library source directory or wheel')
    if name != 'awesome-telegram-patterns' or not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValidationFailure('Local source is not an awesome-telegram-patterns release')
    if tuple(map(int, version.split('.'))) < (0, 4, 0): raise ValidationFailure('Starter requires library >=0.4.0')
    return source, version


def typescript_source(path: str | Path) -> tuple[Path, str]:
    source = Path(path).expanduser().resolve(strict=True)
    with tarfile.open(source, 'r:gz') as archive:
        member = archive.getmember('package/package.json')
        if not member.isfile() or member.size > 65536: raise ValidationFailure('Invalid TypeScript tarball metadata')
        stream = archive.extractfile(member)
        if stream is None: raise ValidationFailure('Missing TypeScript tarball metadata')
        with stream: metadata = json.load(stream)
    if metadata.get('name') != '@awesome-telegram/patterns' or not re.fullmatch(r'\d+\.\d+\.\d+', metadata.get('version', '')):
        raise ValidationFailure('Provide an @awesome-telegram/patterns tarball')
    return source, metadata['version']


def create_starter(target: str | Path, *, library: str | Path, template: str = 'bot',
                   typescript: str | Path | None = None, dry_run: bool = False,
                   components: Sequence[str] | None = None) -> StarterPlan:
    explicit, selected = resolve_components(template, components)
    if type(dry_run) is not bool: raise ValidationFailure('Use a bool dry_run flag')
    requested = Path(target).expanduser().absolute()
    if requested.exists() or _linked(requested): raise FileExistsError('Target already exists; no files replaced')
    if not requested.parent.is_dir() or any(_linked(parent) for parent in requested.parents):
        raise ValidationFailure('Use an existing ordinary parent directory without linked ancestors')
    source, version = library_source(library)
    for component in starter_components(template):
        if component.id in selected and tuple(map(int, version.split('.'))) < tuple(map(int, component.min_library_version.split('.'))):
            raise StarterConflict('component-version')
    ts_source = None
    if template == 'bot-mini-app':
        if typescript is None: raise StarterConflict('missing-typescript')
        ts_source, ts_version = typescript_source(typescript)
        if ts_version != version: raise StarterConflict('artifact-version')
    elif typescript is not None: raise StarterConflict('unexpected-typescript')
    name = re.sub(r'[^a-z0-9]+', '-', requested.name.lower()).strip('-') or 'telegram-starter'
    if len(name) > 64: raise ValidationFailure('Use a shorter project directory name')
    root = files('telegram_patterns').joinpath('resources/starter')
    output = {}
    for filename in ('app.py', 'offline.py', 'README.md', '.env.example', '.gitignore', 'pyproject.toml'):
        content = root.joinpath(filename + '.txt').read_text(encoding='utf-8')
        output[filename] = content.replace('__PROJECT_NAME__', name).replace('__LIBRARY_DEPENDENCY__', json.dumps('awesome-telegram-patterns[aiogram] @ ' + source.as_uri()))
    imports, setup, dispatcher = [], [], 'Dispatcher()'
    ts_imports, ts_mounts = [], []
    feature_files = []
    for component in starter_components(template):
        if component.id not in selected or not component.files: continue
        for filename in component.files:
            content = root.joinpath('components/' + filename + '.txt').read_text(encoding='utf-8')
            output[filename] = content
            feature_files.append(filename)
            if filename.endswith('.py'):
                module = Path(filename).stem
                imports.append(f'from {module} import configure as configure_{module}')
                setup.append(f'    component_commands += configure_{module}(dispatcher)')
                if component.id == 'text-form':
                    imports.append('from aiogram.fsm.storage.memory import SimpleEventIsolation')
                    dispatcher = 'Dispatcher(events_isolation=SimpleEventIsolation())'
            else:
                module = Path(filename).stem
                alias = module.replace('-', '_')
                ts_imports.append(f"import {{mount as {alias}}} from './{module}.js';")
                ts_mounts.append(f'{alias}(shell.content, window.Telegram?.WebApp)')
    output['app.py'] = output['app.py'].replace('__COMPONENT_IMPORTS__', '\n'.join(imports))
    output['app.py'] = output['app.py'].replace('__DISPATCHER__', dispatcher)
    output['app.py'] = output['app.py'].replace('__COMPONENT_SETUP__', '\n'.join(setup))
    output['pyproject.toml'] = output['pyproject.toml'].replace('__PROJECT_MODULES__',
        json.dumps(['app', *[Path(name).stem for name in feature_files if name.endswith('.py')]]))
    output['README.md'] += '\nПодключенные группы: ' + ', '.join(selected) + '.\n'
    if feature_files:
        output['README.md'] += ('\nВыбранные модули подключены к app.py/frontend; Python-проверка: '
                               '`python offline_components.py`. Форма использует transient MemoryStorage; '
                               'наблюдение не durable audit. Каталог и клавиатуры публичные, без private effect. '
                               'API client frontend использует fixture transport; backend auth/session не созданы. '
                               'Черновик хранит только публичный ID под demo scope; реальные учетные записи требуют server-derived scope.\n')
        output['offline_components.py'] = root.joinpath('components/offline_components.py.txt').read_text(encoding='utf-8')
    config = {'schema_version': 1, 'template': template, 'library_version': version, 'library_uri': source.as_uri(),
              'typescript_uri': ts_source.as_uri() if ts_source else None,
              'requested_components': explicit, 'components': selected, 'component_files': feature_files}
    output['.telegram-patterns.json'] = json.dumps(config, ensure_ascii=False, indent=2) + '\n'
    if ts_source:
        for filename in ('index.html', 'tsconfig.json', 'src/main.ts'):
            output['mini-app/' + filename] = root.joinpath('mini-app/' + filename + '.txt').read_text(encoding='utf-8')
        output['mini-app/src/main.ts'] = output['mini-app/src/main.ts'].replace('__COMPONENT_IMPORTS__', '\n'.join(ts_imports))
        output['mini-app/src/main.ts'] = output['mini-app/src/main.ts'].replace('__COMPONENT_MOUNTS__', ','.join(ts_mounts))
        output['mini-app/package.json'] = json.dumps({'name': name + '-mini-app', 'private': True, 'type': 'module',
            'scripts': {'build': 'tsc -p tsconfig.json', 'typecheck': 'tsc -p tsconfig.json --noEmit'},
            # npm file specs are filesystem paths, not percent-encoded file URLs.
            # Keep literal spaces/Unicode/% in the provided local tarball path.
            'dependencies': {'@awesome-telegram/patterns': 'file:' + ts_source.as_posix()}, 'devDependencies': {'typescript': '7.0.2'}}, indent=2) + '\n'
    planned = StarterPlan(requested, template, version, tuple(sorted(output)), not dry_run, selected, explicit)
    if dry_run: return planned
    requested.mkdir()  # Atomic reservation; an existing directory is NEVER adopted.
    for relative, content in output.items():
        path = requested / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        # Refuse links introduced concurrently; never overwrite an existing file.
        if any(_linked(parent) for parent in (path, *path.parents) if parent.is_relative_to(requested)):
            raise InvalidCompletion('Output path contains a link; starter interrupted')
        with path.open('x', encoding='utf-8', newline='\n') as stream: stream.write(content)
    return planned
