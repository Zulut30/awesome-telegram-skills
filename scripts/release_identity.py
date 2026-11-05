"""Строгая общая identity numeric/RC выпуска; только stdlib, без записи файлов.

Это ограниченный контракт проекта, а не универсальный PEP 440/SemVer parser.
Python manifests используют python_version, npm/catalog/tag — identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import tomllib


MAX_COMPONENT = 2**53 - 1
_NUMBER = r'(0|[1-9][0-9]{0,15})'
_VERSION = re.compile(rf'{_NUMBER}\.{_NUMBER}\.{_NUMBER}(?:(?:rc|-rc\.){_NUMBER})?')
_DISTRIBUTION = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?')
_NPM_PART = r'[a-z0-9][a-z0-9._-]*'
_NPM_NAME = re.compile(rf'(?:@{_NPM_PART}/)?{_NPM_PART}')


class ReleaseIdentityError(ValueError):
    """Неоднозначная/неподдержанная версия, имя артефакта или manifest."""


@dataclass(frozen=True)
class ReleaseIdentity:
    """Immutable identity; прямое создание проверяется так же строго, как parsing."""

    major: int
    minor: int
    patch: int
    rc: int | None = None

    def __post_init__(self) -> None:
        for name in ('major', 'minor', 'patch', 'rc'):
            value = getattr(self, name)
            if name == 'rc' and value is None:
                continue
            if type(value) is not int or not 0 <= value <= MAX_COMPONENT:
                raise ReleaseIdentityError(f'{name} must be an exact integer in 0..{MAX_COMPONENT}')

    @property
    def release(self) -> tuple[int, int, int]:
        """Base tuple для явно заданных report thresholds, без смысла final acceptance."""
        return self.major, self.minor, self.patch

    @property
    def base_version(self) -> str:
        return '.'.join(map(str, self.release))

    @property
    def identity(self) -> str:
        return self.base_version + (f'-rc.{self.rc}' if self.rc is not None else '')

    @property
    def npm_version(self) -> str:
        return self.identity

    @property
    def python_version(self) -> str:
        return self.base_version + (f'rc{self.rc}' if self.rc is not None else '')

    @property
    def tag(self) -> str:
        return 'v' + self.identity

    @property
    def is_prerelease(self) -> bool:
        """Есть RC segment; историческая политика всех GitHub releases 0.x отдельно."""
        return self.rc is not None

    @property
    def precedence_key(self) -> tuple[int, int, int, int, int]:
        """Numeric order: rc.2 < rc.10 < final при одинаковой base version."""
        return (*self.release, int(self.rc is None), self.rc if self.rc is not None else 0)

    def wheel_filename(self, distribution_name: str) -> str:
        """Имя pure Python wheel текущей поставки (py3-none-any), без build tag."""
        if not isinstance(distribution_name, str) or not _DISTRIBUTION.fullmatch(distribution_name):
            raise ReleaseIdentityError('Expected a Python distribution name, without paths or URLs')
        normalized = re.sub(r'[-_.]+', '_', distribution_name).lower()
        return f'{normalized}-{self.python_version}-py3-none-any.whl'

    def npm_tarball_filename(self, package_name: str) -> str:
        """npm pack basename: @scope/name -> scope-name, unscoped name unchanged."""
        if (not isinstance(package_name, str) or len(package_name) > 214
                or not _NPM_NAME.fullmatch(package_name)):
            raise ReleaseIdentityError('Expected a lowercase npm package name or @scope/name, without paths or URLs')
        normalized = package_name.removeprefix('@').replace('/', '-')
        return f'{normalized}-{self.npm_version}.tgz'


def parse_release_version(version: str) -> ReleaseIdentity:
    """Принимает только canonical X.Y.Z, X.Y.ZrcN и X.Y.Z-rc.N; N включает 0."""
    match = _VERSION.fullmatch(version) if isinstance(version, str) else None
    if match is None:
        raise ReleaseIdentityError('Expected canonical X.Y.Z, X.Y.ZrcN or X.Y.Z-rc.N')
    major, minor, patch, rc = match.groups()
    return ReleaseIdentity(int(major), int(minor), int(patch), int(rc) if rc is not None else None)


def parse_release_tag(tag: str) -> ReleaseIdentity:
    """Git tag только v + canonical identity/npm form; Python-form tag запрещен."""
    if not isinstance(tag, str) or not tag.startswith('v'):
        raise ReleaseIdentityError('Expected v followed by canonical release identity')
    release = parse_release_version(tag[1:])
    if tag != release.tag:
        raise ReleaseIdentityError('Tag must use canonical identity, including -rc.N when present')
    return release


def _unique_json_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseIdentityError('Duplicate JSON field in npm manifest')
        result[key] = value
    return result


def read_release_identity(pyproject_path: str | Path, package_json_path: str | Path) -> ReleaseIdentity:
    """Read-only сверка двух manifests; никаких implicit fixes/strip/normalization.

    Читаются ровно переданные файлы; нет поиска manifests в cwd/git/env или network.
    Ошибки чтения/декодирования/формата оборачиваются в ReleaseIdentityError.
    """
    pyproject = Path(pyproject_path)
    package_json = Path(package_json_path)
    try:
        python_data = tomllib.loads(pyproject.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ReleaseIdentityError(f'Cannot read Python manifest: {pyproject}') from error
    try:
        npm_data = json.loads(package_json.read_text(encoding='utf-8'), object_pairs_hook=_unique_json_fields)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseIdentityError(f'Cannot read npm manifest: {package_json}') from error
    project = python_data.get('project')
    if not isinstance(project, dict) or not isinstance(npm_data, dict):
        raise ReleaseIdentityError('Expected [project].version and package.json object.version')
    python_version = project.get('version')
    npm_version = npm_data.get('version')
    python_release = parse_release_version(python_version)
    npm_release = parse_release_version(npm_version)
    if python_version != python_release.python_version:
        raise ReleaseIdentityError('Python manifest must use canonical Python version')
    if npm_version != npm_release.npm_version:
        raise ReleaseIdentityError('npm manifest must use canonical npm version')
    if python_release != npm_release:
        raise ReleaseIdentityError('Python and npm manifests have different release identities')
    return python_release
