"""Create a NEW starter, preserving all existing paths. No install/process/network."""
from __future__ import annotations
from dataclasses import dataclass
from email.parser import Parser
from importlib.resources import files
import json
from pathlib import Path
import re
import tarfile
import tomllib
import zipfile


@dataclass(frozen=True, slots=True)
class StarterPlan:
    target: Path
    template: str
    library_version: str
    files: tuple[str, ...]
    created: bool


def _linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())


def library_source(path: str | Path) -> tuple[Path, str]:
    source = Path(path).expanduser().resolve(strict=True)
    if source.is_dir():
        if (source / 'packages/python/pyproject.toml').is_file(): source = source / 'packages/python'
        project = tomllib.loads((source / 'pyproject.toml').read_text(encoding='utf-8'))['project']
        name, version = project['name'], project['version']
    elif source.suffix == '.whl':
        with zipfile.ZipFile(source) as archive:
            members = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
            if len(members) != 1 or archive.getinfo(members[0]).file_size > 65536: raise ValueError('Invalid local wheel metadata')
            metadata = Parser().parsestr(archive.read(members[0]).decode('utf-8'))
            name, version = metadata['Name'], metadata['Version']
    else: raise ValueError('Provide a local library source directory or wheel')
    if name != 'awesome-telegram-patterns' or not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Local source is not an awesome-telegram-patterns release')
    if tuple(map(int, version.split('.'))) < (0, 4, 0): raise ValueError('Starter requires library >=0.4.0')
    return source, version


def typescript_source(path: str | Path) -> tuple[Path, str]:
    source = Path(path).expanduser().resolve(strict=True)
    with tarfile.open(source, 'r:gz') as archive:
        member = archive.getmember('package/package.json')
        if not member.isfile() or member.size > 65536: raise ValueError('Invalid TypeScript tarball metadata')
        stream = archive.extractfile(member)
        if stream is None: raise ValueError('Missing TypeScript tarball metadata')
        with stream: metadata = json.load(stream)
    if metadata.get('name') != '@awesome-telegram/patterns' or not re.fullmatch(r'\d+\.\d+\.\d+', metadata.get('version', '')):
        raise ValueError('Provide an @awesome-telegram/patterns tarball')
    return source, metadata['version']


def create_starter(target: str | Path, *, library: str | Path, template: str = 'bot',
                   typescript: str | Path | None = None, dry_run: bool = False) -> StarterPlan:
    if template not in {'bot', 'bot-mini-app'} or type(dry_run) is not bool: raise ValueError('Use a supported starter template')
    requested = Path(target).expanduser().absolute()
    if requested.exists() or _linked(requested): raise FileExistsError('Target already exists; no files replaced')
    if not requested.parent.is_dir() or _linked(requested.parent): raise ValueError('Use an existing ordinary parent directory')
    source, version = library_source(library)
    ts_source = None
    if template == 'bot-mini-app':
        if typescript is None: raise ValueError('Mini App starter requires a local --typescript tarball')
        ts_source, ts_version = typescript_source(typescript)
        if ts_version != version: raise ValueError('Use matching Python and TypeScript release versions')
    elif typescript is not None: raise ValueError('--typescript is only used by bot-mini-app')
    name = re.sub(r'[^a-z0-9]+', '-', requested.name.lower()).strip('-') or 'telegram-starter'
    if len(name) > 64: raise ValueError('Use a shorter project directory name')
    root = files('telegram_patterns').joinpath('resources/starter')
    output = {}
    for filename in ('app.py', 'offline.py', 'README.md', '.env.example', '.gitignore', 'pyproject.toml'):
        content = root.joinpath(filename + '.txt').read_text(encoding='utf-8')
        output[filename] = content.replace('__PROJECT_NAME__', name).replace('__LIBRARY_DEPENDENCY__', json.dumps('awesome-telegram-patterns[aiogram] @ ' + source.as_uri()))
    config = {'schema_version': 1, 'template': template, 'library_version': version, 'library_uri': source.as_uri(),
              'typescript_uri': ts_source.as_uri() if ts_source else None}
    output['.telegram-patterns.json'] = json.dumps(config, ensure_ascii=False, indent=2) + '\n'
    if ts_source:
        for filename in ('index.html', 'tsconfig.json', 'src/main.ts'):
            output['mini-app/' + filename] = root.joinpath('mini-app/' + filename + '.txt').read_text(encoding='utf-8')
        output['mini-app/package.json'] = json.dumps({'name': name + '-mini-app', 'private': True, 'type': 'module',
            'scripts': {'build': 'tsc -p tsconfig.json', 'typecheck': 'tsc -p tsconfig.json --noEmit'},
            'dependencies': {'@awesome-telegram/patterns': ts_source.as_uri()}, 'devDependencies': {'typescript': '7.0.2'}}, indent=2) + '\n'
    planned = StarterPlan(requested, template, version, tuple(sorted(output)), not dry_run)
    if dry_run: return planned
    requested.mkdir()  # Atomic reservation; an existing directory is NEVER adopted.
    for relative, content in output.items():
        path = requested / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        # Refuse links introduced concurrently; never overwrite an existing file.
        if any(_linked(parent) for parent in (path, *path.parents) if parent.is_relative_to(requested)):
            raise ValueError('Output path contains a link; starter interrupted')
        with path.open('x', encoding='utf-8', newline='\n') as stream: stream.write(content)
    return planned
