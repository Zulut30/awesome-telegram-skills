"""Private, bounded local checks behind the documented cli.doctor API."""
from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tomllib

from .settings import BotSettings

_MAX_MANIFEST_BYTES = 256 * 1024
_VERSION = re.compile(r'\d+\.\d+\.\d+')
_SYSTEM_ENV = {'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC'}
_SDK_PROBE = ("from telegram_patterns import aiogram as a; "
              "import sys; ready=all(callable(getattr(a,n,None)) for n in "
              "('command_router','action_menu','run_bot')); "
              "print('ready' if ready else 'unavailable'); sys.exit(0 if ready else 1)")
_LIMITS = ('Only local manifests, installed package metadata, isolated Python adapter imports and fixed node --version; '
           'no Telegram token validity/webhook/polling, deployment, project-code execution, '
           'backend auth, dependency installation or real-client check. Suggested commands are not executed.')


def _command(argv: list[str], *, cwd: str = 'project', placeholders: bool = False) -> dict:
    if argv[0] == 'npm' and os.name == 'nt':
        argv = ['npm.cmd', *argv[1:]]
    return {'argv': argv, 'cwd': cwd, 'requires_substitution': placeholders}


def _rerun() -> dict:
    return _command(['python', '-m', 'telegram_patterns', 'doctor', '.'])


def _repair_install() -> list[dict]:
    bootstrap = [_command(['python', '-m', 'ensurepip'])] if importlib.util.find_spec('pip') is None else []
    return [*bootstrap, _command(['python', '-m', 'pip', 'check']),
            _command(['python', '-m', 'pip', 'install', '<PROVIDED_WHEEL>[aiogram]'], placeholders=True)]


def _linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())


def _tool_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key.upper() in _SYSTEM_ENV}


def _sdk_probe() -> bool:
    """Fixed isolated import check, never importing SDK dependencies from target."""
    try:
        result = subprocess.run([sys.executable, '-I', '-B', '-c', _SDK_PROBE], cwd=sys.prefix,
                                capture_output=True, text=True, timeout=30,
                                env=_tool_environment(), shell=False)
        return result.returncode == 0 and result.stdout.strip() == 'ready'
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return False


def _read_manifest(path: Path) -> tuple[str | None, str]:
    """Never follow a known link; bound reads even if a file grows after stat."""
    try:
        if any(_linked(parent) for parent in (path, *path.parents)):
            return None, 'linked-manifest'
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            return None, 'manifest-not-file'
        if info.st_size > _MAX_MANIFEST_BYTES:
            return None, 'manifest-too-large'
        with path.open('rb') as stream:
            content = stream.read(_MAX_MANIFEST_BYTES + 1)
        if len(content) > _MAX_MANIFEST_BYTES:
            return None, 'manifest-too-large'
        return content.decode('utf-8'), 'readable'
    except FileNotFoundError:
        return None, 'missing-manifest'
    except UnicodeError:
        return None, 'manifest-encoding'
    except OSError:
        return None, 'manifest-unreadable'


def diagnose(target: str | Path, *, require_token: bool) -> dict:
    checks: list[dict] = []

    def check(name: str, status: str, reason: str, detail: str, *,
              fix: str = '', commands: list[dict] | None = None) -> None:
        checks.append({'name': name, 'status': status, 'detail': detail, 'reason': reason,
                       'remediation': {'summary': fix, 'commands': commands or []}})

    def finish() -> dict:
        return {'passed': not any(item['status'] == 'fail' for item in checks),
                'network': False, 'checks': checks, 'limits': _LIMITS,
                'schema_version': 1, 'tool_probes_attempted':
                    (['python -I -B adapter imports'] if sdk_probed else []) + (['node --version'] if node_executed else []),
                'suggestions_executed': False}

    node_executed = False
    sdk_probed = False
    try:
        supplied = Path(target).expanduser().absolute()
        if any(_linked(parent) for parent in (supplied, *supplied.parents)):
            check('project', 'fail', 'linked-project', 'Каталог проекта проходит через symbolic link или junction.',
                  fix='Укажите настоящий каталог проекта, чтобы диагностика не читала другое дерево.',
                  commands=[_command(['python', '-m', 'telegram_patterns', 'doctor', '<PROJECT_DIRECTORY>'], placeholders=True)])
            return finish()
        root = supplied.resolve(strict=True)
        if not root.is_dir():
            check('project', 'fail', 'project-not-directory', 'Doctor ожидает каталог проекта.',
                  fix='Укажите каталог, содержащий конфигурацию приложения.', commands=[_rerun()])
            return finish()
    except (OSError, ValueError, RuntimeError, TypeError):
        check('project', 'fail', 'project-unavailable', 'Каталог не найден или недоступен.',
              fix='Проверьте путь и права чтения; существующие файлы создавать или удалять не нужно.',
              commands=[_command(['python', '-m', 'telegram_patterns', 'doctor', '<PROJECT_DIRECTORY>'], placeholders=True)])
        return finish()

    check('python', 'pass' if sys.version_info >= (3, 11) else 'fail',
          'python-supported' if sys.version_info >= (3, 11) else 'python-too-old',
          '.'.join(map(str, sys.version_info[:3])),
          fix='' if sys.version_info >= (3, 11) else 'Выберите Python >=3.11 и отдельное окружение приложения.',
          commands=[] if sys.version_info >= (3, 11) else [_command(['python', '--version'])])
    try:
        library = importlib.metadata.version('awesome-telegram-patterns')
        if isinstance(library, str) and _VERSION.fullmatch(library):
            check('library', 'pass', 'library-installed', library)
        else:
            check('library', 'fail', 'library-version-invalid', 'Не удалось определить версию локальной библиотеки.',
                  fix='Установите согласованный предоставленный wheel в окружение приложения.', commands=_repair_install())
    except importlib.metadata.PackageNotFoundError:
        check('library', 'fail', 'library-not-installed', 'Метаданные установленной библиотеки отсутствуют.',
              fix='Запустите doctor из окружения, куда установлен предоставленный wheel.', commands=_repair_install())

    try:
        sdk = importlib.metadata.version('aiogram')
    except importlib.metadata.PackageNotFoundError:
        check('aiogram', 'fail', 'sdk-missing', 'Aiogram не установлен в текущем Python окружении.',
              fix='Для нашего aiogram starter установите предоставленный wheel с extra. Core recipes/init работают без SDK; другой стек сохраняйте.',
              commands=_repair_install())
    else:
        match = _VERSION.fullmatch(sdk) if isinstance(sdk, str) else None
        supported = bool(match and tuple(map(int, sdk.split('.')[:2])) >= (3, 31) and sdk.split('.')[0] == '3')
        check('aiogram', 'pass' if supported else 'fail', 'sdk-supported' if supported else 'sdk-incompatible',
              sdk if match else 'Версия SDK не распознана.',
              fix='' if supported else 'Нужен aiogram >=3.31,<4. Проверьте ограничения приложения перед изменением SDK.',
              commands=[] if supported else _repair_install())
        if supported:
            if sdk != '3.31.0':
                check('sdk-tested-version', 'warn', 'sdk-not-tested', 'Эта поставка проверена на aiogram 3.31.0.',
                      fix='Проверьте выбранную версию своими тестами; смена SDK не выполняется автоматически.',
                      commands=[_command(['python', '-m', 'pip', 'check'])])
            try:
                spec = importlib.util.find_spec('aiogram')
                expected = importlib.metadata.distribution('aiogram').locate_file('aiogram/__init__.py')
                verified_origin = bool(spec and spec.origin and Path(spec.origin).resolve(strict=True) == Path(str(expected)).resolve(strict=True))
            except (OSError, ValueError, importlib.metadata.PackageNotFoundError):
                verified_origin = False
            if not verified_origin:
                check('python-exports', 'fail', 'adapter-origin-unverified', 'Aiogram import не совпадает с установленным SDK.',
                      fix='Проверьте имена aiogram.py/aiogram и sys.path: локальный файл может подменять SDK. Запустите установленный пакет из правильного окружения; файлы не изменяются автоматически.',
                      commands=[_rerun()])
            else:
                sdk_probed = True
                exports = _sdk_probe()
                check('python-exports', 'pass' if exports else 'fail', 'adapter-ready' if exports else 'adapter-import-failed',
                      'Публичные adapters доступны в изолированном установленном окружении.' if exports else 'Не удалось загрузить публичные adapters из установленного окружения.',
                      fix='' if exports else 'Проверьте зависимости и установленную библиотеку в том же interpreter. User-site/source-only imports не входят в изолированную проверку.',
                      commands=[] if exports else _repair_install())

    text, reason = _read_manifest(root / 'pyproject.toml')
    if text is None:
        optional = reason == 'missing-manifest'
        check('pyproject', 'warn' if optional else 'fail', reason,
              'Нет pyproject.toml; проект может использовать другой формат.' if optional else 'Pyproject недоступен как UTF-8 файл до 256 KiB.',
              fix='Проверьте зависимости в принятом формате проекта; миграция не обязательна.' if optional else
                  'Проверьте права, UTF-8 и размер файла; укажите обычный файл внутри настоящего проекта.',
              commands=[_rerun()])
    else:
        try:
            tomllib.loads(text)
            check('pyproject', 'pass', 'toml-valid', 'TOML прочитан; код проекта не выполнялся.')
        except (ValueError, RecursionError):
            check('pyproject', 'fail', 'toml-invalid', 'Синтаксис pyproject.toml поврежден.',
                  fix='Исправьте TOML в редакторе, сохранив зависимости приложения; содержимое файла в отчет не включается.', commands=[_rerun()])

    try:
        BotSettings.from_env()
        check('token-format', 'pass', 'token-format-valid', 'BOT_TOKEN присутствует в окружении; проверен только формат.')
    except ValueError:
        present = bool(os.environ.get('BOT_TOKEN'))
        check('token-format', 'fail' if require_token else 'warn', 'token-format-invalid' if present else 'token-missing',
              'BOT_TOKEN имеет неверный формат.' if present else 'BOT_TOKEN отсутствует в окружении; .env не читается.',
              fix='Для offline запуска token не нужен. Для live задайте BOT_TOKEN через свой механизм секретов; doctor не подтверждает действительность token.',
              commands=[_command(['python', '-m', 'telegram_patterns', 'doctor', '.', '--require-token'])])

    mini_dir = root / 'mini-app'
    # A present but damaged/inaccessible mini-app must not silently disappear.
    try:
        mini_dir.stat()
        mini_present = True
    except FileNotFoundError:
        mini_present = _linked(mini_dir)
    except OSError:
        mini_present = True
    if mini_present:
        text, reason = _read_manifest(mini_dir / 'package.json')
        if text is None:
            check('mini-app-manifest', 'fail', reason, 'Mini App package.json недоступен как UTF-8 файл до 256 KiB.',
                  fix='Проверьте обычный mini-app/package.json, права, UTF-8 и размер. Другой frontend layout проверяйте инструментами проекта.', commands=[_rerun()])
        else:
            try:
                data = json.loads(text)
            except (ValueError, RecursionError):
                check('mini-app-manifest', 'fail', 'json-invalid', 'Синтаксис Mini App package.json поврежден.',
                      fix='Исправьте JSON без изменения выбранного frontend стека.', commands=[_rerun()])
            else:
                dependencies = data.get('dependencies') if isinstance(data, dict) else None
                dependency = dependencies.get('@awesome-telegram/patterns') if isinstance(dependencies, dict) else None
                valid = isinstance(dependency, str) and bool(dependency.strip())
                check('mini-app-manifest', 'pass' if valid else 'fail', 'mini-app-dependency-declared' if valid else 'mini-app-dependency-missing',
                      'Зависимость библиотеки объявлена; установка и совместимость frontend не подтверждены.' if valid else
                      'Нет непустой строковой зависимости @awesome-telegram/patterns в dependencies.',
                      fix='' if valid else 'Укажите предоставленный tarball согласованной версии в package.json; сохраняйте свой frontend.',
                      commands=[] if valid else [_command(['npm', 'install', '<PROVIDED_TARBALL>'], cwd='mini-app', placeholders=True)])
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        check('npm', 'pass' if npm else 'fail', 'npm-on-path' if npm else 'npm-missing',
              'Npm найден в PATH; пакеты не устанавливались.' if npm else 'Npm отсутствует в PATH.',
              fix='' if npm else 'Установите поддерживаемую Node LTS с npm и откройте новый terminal.',
              commands=[] if npm else [_command(['npm', '--version'], cwd='mini-app')])
        node = shutil.which('node')
        if not node:
            check('node', 'fail', 'node-missing', 'Node отсутствует в PATH.',
                  fix='Выберите поддерживаемую Node LTS, технический минимум пакета >=20. Эта поставка проверяется на Node 24.',
                  commands=[_command(['node', '--version'], cwd='mini-app')])
        else:
            # Fixed trusted-tool probe receives no token or arbitrary inherited secrets/options.
            environment = _tool_environment()
            try:
                node_executed = True
                result = subprocess.run([node, '--version'], cwd=root, capture_output=True, text=True,
                                        timeout=10, env=environment, shell=False)
                match = re.fullmatch(r'v(\d+)\.\d+\.\d+', result.stdout.strip())
                node_ok = bool(result.returncode == 0 and match and int(match.group(1)) >= 20)
                reason = 'node-supported' if node_ok else 'node-too-old' if result.returncode == 0 and match else 'node-probe-failed'
                check('node', 'pass' if node_ok else 'fail', reason,
                      match.group(0) if match and result.returncode == 0 else 'Не удалось прочитать версию Node.',
                      fix='' if node_ok else 'Проверьте установленный Node и PATH; используйте поддерживаемую LTS >=20.',
                      commands=[] if node_ok else [_command(['node', '--version'], cwd='mini-app')])
                if node_ok and match and int(match.group(1)) != 24:
                    check('node-tested-version', 'warn', 'node-not-tested', 'Эта поставка проверена на Node 24; минимальная версия не является рекомендацией production.',
                          fix='Выберите поддерживаемую LTS и проверьте свой frontend build; версии клиентов проверяются отдельно.',
                          commands=[_command(['npm', 'run', 'build'], cwd='mini-app')])
            except (OSError, subprocess.TimeoutExpired, UnicodeError):
                check('node', 'fail', 'node-probe-failed', 'Локальная команда node --version завершилась ошибкой или timeout.',
                      fix='Проверьте установленный Node и PATH; вывод процесса в отчет не включается.',
                      commands=[_command(['node', '--version'], cwd='mini-app')])
    return finish()
