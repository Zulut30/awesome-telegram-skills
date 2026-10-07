"""Private, bounded local checks behind the documented cli.doctor API."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from ._shared import env_flag, read_env_file
from .settings import BotSettings

_MAX_MANIFEST_BYTES = 256 * 1024
_VERSION = re.compile(r'\d+\.\d+\.\d+')
_SYSTEM_ENV = {'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC'}
_SDK_PROBE = (
    "from telegram_patterns import aiogram as a; "
    "import sys; ready=all(callable(getattr(a,n,None)) for n in "
    "('command_router','action_menu','run_bot')); "
    "print('ready' if ready else 'unavailable'); sys.exit(0 if ready else 1)"
)
_LIMITS = (
    'Only local manifests, installed package metadata, isolated Python adapter imports and fixed node --version; '
    'no Telegram token validity/webhook/polling, deployment, project-code execution, '
    'backend auth, dependency installation or real-client check. Suggested commands are not executed.'
)
_WEBHOOK_LIMITS = (
    'Local checks plus one read-only getWebhookInfo request with BOT_TOKEN from the environment or project .env; '
    'no setWebhook/deleteWebhook/getUpdates, endpoint probe, deployment or project-code execution. '
    'Bot API does not report whether secret_token was set; only a local secret is checked. Suggested commands are '
    'not executed.'
)
_API_BASE = 'https://api.telegram.org'
_WEBHOOK_TIMEOUT = 10.0
_MAX_API_BYTES = 64 * 1024
_SECRET = re.compile(r'[A-Za-z0-9_-]{1,256}')
_ENV_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_RECENT_SECONDS = 24 * 3600
_BACKLOG = 100
# Commands read BOT_TOKEN from the environment, so the token never appears in argv or shell history.
_API_CALL = (
    "import os,urllib.request;"
    "print(urllib.request.urlopen('{base}/bot'+os.environ['BOT_TOKEN']+'/{prefix}{method}').read().decode())"
)


def _command(argv: list[str], *, cwd: str = 'project', placeholders: bool = False) -> dict[str, Any]:
    if argv[0] == 'npm' and os.name == 'nt':
        argv = ['npm.cmd', *argv[1:]]
    return {'argv': argv, 'cwd': cwd, 'requires_substitution': placeholders}


def _rerun() -> dict[str, Any]:
    return _command(['python', '-m', 'telegram_patterns', 'doctor', '.'])


def _repair_install() -> list[dict[str, Any]]:
    bootstrap = [_command(['python', '-m', 'ensurepip'])] if importlib.util.find_spec('pip') is None else []
    return [
        *bootstrap,
        _command(['python', '-m', 'pip', 'check']),
        _command(['python', '-m', 'pip', 'install', '<PROVIDED_WHEEL>[aiogram]'], placeholders=True),
    ]


def _linked(path: Path) -> bool:
    """A symlink or junction outside the OS layout; known links are refused.

    Root-owned aliases directly under the filesystem root are trusted: on macOS
    /var, /tmp and /etc point to /private/..., so every temporary path crosses one.
    """
    if not (path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())):
        return False
    try:
        system_alias = (
            os.name != 'nt' and path.is_absolute() and path.parent == Path(path.anchor) and path.lstat().st_uid == 0
        )
    except OSError:
        system_alias = False
    return not system_alias


def _tool_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key.upper() in _SYSTEM_ENV}


def _sdk_probe() -> bool:
    """Fixed isolated import check, never importing SDK dependencies from target."""
    try:
        result = subprocess.run(
            [sys.executable, '-I', '-B', '-c', _SDK_PROBE],
            cwd=sys.prefix,
            capture_output=True,
            text=True,
            timeout=30,
            env=_tool_environment(),
            shell=False,
        )
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


class _WebhookUnavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _fetch_webhook_info(token: str, *, test: bool = False) -> dict[str, Any]:
    """One GET getWebhookInfo; the token exists only in the request URL, never in errors or the report."""
    request = urllib.request.Request(
        f'{_API_BASE}/bot{token}/{"test/" if test else ""}getWebhookInfo', headers={'Accept': 'application/json'}
    )
    try:
        with urllib.request.urlopen(request, timeout=_WEBHOOK_TIMEOUT) as response:
            body = response.read(_MAX_API_BYTES + 1)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        raise _WebhookUnavailable('token-rejected' if status in (401, 404) else 'api-error') from None
    except (urllib.error.URLError, OSError, ValueError):
        raise _WebhookUnavailable('api-unreachable') from None
    try:
        payload = json.loads(body) if len(body) <= _MAX_API_BYTES else None
    except (ValueError, RecursionError):
        payload = None
    if not (isinstance(payload, dict) and payload.get('ok') is True and isinstance(payload.get('result'), dict)):
        raise _WebhookUnavailable('api-error')
    result: dict[str, Any] = payload['result']
    return result


def _api_command(method: str, *, test: bool = False) -> dict[str, Any]:
    return _command(['python', '-c', _API_CALL.format(base=_API_BASE, prefix='test/' if test else '', method=method)])


def _set_webhook_command(secret_env: str, *, test: bool = False) -> dict[str, Any]:
    code = (
        "import "
        "os,urllib.parse,urllib.request;q=urllib.parse.urlencode({'url':'<WEBHOOK_URL>','secret_token':os.environ['"
        + secret_env
        + "']});"
        "print(urllib.request.urlopen('"
        + _API_BASE
        + "/bot'+os.environ['BOT_TOKEN']+'/"
        + ('test/' if test else '')
        + "setWebhook?'+q).read().decode())"
    )
    return _command(['python', '-c', code], placeholders=True)


def _safe_url(url: str) -> str:
    """Scheme, host and port only: a webhook path often carries a secret."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ''
        port = parts.port
    except ValueError:
        return 'URL скрыт: не удалось разобрать'
    if ':' in host:
        host = f'[{host}]'
    hidden = '/…' if parts.path not in ('', '/') or parts.query or parts.fragment else ''
    return f'{parts.scheme}://{host}{f":{port}" if port else ""}{hidden}'


def _age(seconds: float) -> str:
    minutes = max(0, int(seconds // 60))
    if minutes < 60:
        return f'{minutes} мин назад'
    if minutes < 48 * 60:
        return f'{minutes // 60} ч назад'
    return f'{minutes // 1440} дн назад'


def _delivery_error(message: str) -> tuple[str, str]:
    text = message.lower()
    status = re.search(r'wrong response from the webhook: (\d{3})', text)
    if status and status.group(1) in ('401', '403'):
        return 'webhook-auth-rejected', (
            'Сервер отклоняет запросы Telegram: сверьте secret_token из setWebhook с проверкой заголовка '
            'X-Telegram-Bot-Api-Secret-Token, а также правила firewall/WAF.'
        )
    if status and status.group(1) == '404':
        return (
            'webhook-path-not-found',
            'Путь webhook не обслуживается: сверьте URL из setWebhook с маршрутом сервера и reverse proxy.',
        )
    if status and status.group(1).startswith('5'):
        return 'webhook-server-error', (
            'Обработчик падает или proxy не достает до процесса: смотрите логи сервера. '
            'Отвечайте 200 только после обработки или надежного сохранения update.'
        )
    if status:
        return 'webhook-bad-response', 'Webhook должен отвечать 2xx: смотрите логи сервера и ответ обработчика.'
    if 'ssl' in text or 'certificate' in text:
        return 'webhook-tls', (
            'Проверьте полную цепочку сертификата и имя хоста. Самоподписанный сертификат '
            'передается параметром certificate в setWebhook.'
        )
    if any(
        sign in text
        for sign in ('refused', 'timed out', 'timeout', 'resolve', 'no route', 'unreachable', 'name or service')
    ):
        return 'webhook-unreachable', (
            'Telegram не может подключиться: проверьте DNS, открытый порт (443, 80, 88 или 8443), '
            'firewall и что сервер слушает этот адрес.'
        )
    return 'webhook-error', 'Смотрите логи сервера за время ошибки; повторите doctor после исправления.'


def _webhook_checks(
    info: Mapping[str, Any], *, expect: str | None, secret_env: str, secret: str | None, now: float, test: bool = False
) -> list[tuple[Any, ...]]:
    """Pure analysis of a WebhookInfo object; each tuple feeds diagnose().check()."""
    rerun = _command(['python', '-m', 'telegram_patterns', 'doctor', '.', '--webhook'])
    url = info.get('url') if isinstance(info.get('url'), str) else ''
    pending = info.get('pending_update_count')
    pending = pending if isinstance(pending, int) and not isinstance(pending, bool) and pending >= 0 else 0
    found: list[tuple[Any, ...]] = []
    shown = _safe_url(url) if url else ''
    if url:
        extra = [f'IP {info["ip_address"]}'] if isinstance(info.get('ip_address'), str) else []
        if isinstance(info.get('max_connections'), int):
            extra.append(f'max_connections {info["max_connections"]}')
        if info.get('has_custom_certificate') is True:
            extra.append('собственный сертификат')
        detail = f'Webhook установлен: {shown}' + (f' ({", ".join(extra)})' if extra else '') + '.'
        delete = 'удалите webhook через deleteWebhook без drop_pending_updates — очередь updates сохранится.'
        if expect == 'webhook':
            found.append(('webhook', 'pass', 'webhook-set', detail))
        elif expect == 'polling':
            found.append(
                (
                    'webhook',
                    'fail',
                    'webhook-blocks-polling',
                    detail + ' Пока он установлен, getUpdates отвечает 409 Conflict.',
                    'Если updates должен получать этот polling процесс и сервер по этому адресу больше их не '
                    'принимает, ' + delete + ' Иначе запускайте бот в режиме webhook. Doctor ничего не меняет.',
                    [_api_command('deleteWebhook', test=test), rerun],
                )
            )
        else:
            found.append(
                (
                    'webhook',
                    'warn',
                    'webhook-active',
                    detail + ' Polling (run_bot, app.py стартера) получит 409 Conflict.',
                    'Для polling ' + delete + ' Для webhook повторите doctor с --expect webhook.',
                    [
                        _api_command('deleteWebhook', test=test),
                        _command(
                            ['python', '-m', 'telegram_patterns', 'doctor', '.', '--webhook', '--expect', 'webhook']
                        ),
                    ],
                )
            )
    elif expect == 'webhook':
        found.append(
            (
                'webhook',
                'fail',
                'webhook-not-set',
                'Webhook не установлен: Telegram хранит updates для getUpdates.',
                'Вызовите setWebhook с HTTPS адресом сервера (порт 443, 80, 88 или 8443) и secret_token; '
                'другой polling процесс этого бота перед этим остановите.',
                [_set_webhook_command(secret_env, test=test), rerun],
            )
        )
    else:
        found.append(
            (
                'webhook',
                'pass',
                'polling-available',
                'Webhook не установлен: polling через getUpdates доступен одному процессу.',
            )
        )

    if url:
        error_date = info.get('last_error_date')
        recent_error = isinstance(error_date, int) and now - error_date < _RECENT_SECONDS
        if pending >= _BACKLOG or (pending and recent_error):
            found.append(
                (
                    'webhook-pending',
                    'warn',
                    'webhook-backlog',
                    f'{pending} updates ждут доставки на webhook.',
                    'Telegram не успевает доставить updates: устраните ошибку доставки ниже и ускорьте ответ '
                    'обработчика. '
                    'Updates хранятся не дольше 24 часов; не удаляйте очередь ради диагностики.',
                    [rerun],
                )
            )
        else:
            found.append(('webhook-pending', 'pass', 'webhook-queue-ok', f'{pending} updates ждут доставки.'))
    elif pending:
        found.append(
            (
                'webhook-pending',
                'warn',
                'updates-waiting',
                f'{pending} updates ждут getUpdates; Telegram хранит их не дольше 24 часов.',
                'Запустите один polling процесс бота; не удаляйте очередь ради диагностики.',
                [_command(['python', 'app.py'])],
            )
        )
    else:
        found.append(('webhook-pending', 'pass', 'queue-empty', 'Очередь updates пуста.'))

    error_date = info.get('last_error_date')
    if isinstance(error_date, int) and not isinstance(error_date, bool):
        raw_message = info.get('last_error_message')
        message = ' '.join(raw_message.split())[:200] if isinstance(raw_message, str) else ''
        message = message or 'текст ошибки не передан'
        if now - error_date < _RECENT_SECONDS:
            reason, fix = _delivery_error(message)
            found.append(
                (
                    'webhook-error',
                    'warn',
                    reason,
                    f'Последняя ошибка доставки {_age(now - error_date)}: {message}',
                    fix,
                    [rerun],
                )
            )
        else:
            found.append(
                (
                    'webhook-error',
                    'pass',
                    'webhook-error-old',
                    f'Последняя ошибка доставки {_age(now - error_date)}: {message}',
                )
            )
    elif url:
        found.append(('webhook-error', 'pass', 'webhook-no-errors', 'Telegram не сообщает об ошибках доставки.'))
    sync_date = info.get('last_synchronization_error_date')
    if isinstance(sync_date, int) and not isinstance(sync_date, bool) and now - sync_date < _RECENT_SECONDS:
        found.append(
            (
                'webhook-sync',
                'warn',
                'sync-error',
                f'Telegram сообщил об ошибке синхронизации updates {_age(now - sync_date)}.',
                'Обычно это временная проблема на стороне Telegram: повторите doctor позже; если ошибка повторяется, '
                'сверьте, что updates получает только один процесс.',
                [rerun],
            )
        )

    if url or expect == 'webhook':
        generate = _command(['python', '-c', 'import secrets; print(secrets.token_urlsafe(32))'])
        if secret is None or secret == '':
            found.append(
                (
                    'webhook-secret',
                    'warn',
                    'secret-not-found',
                    f'{secret_env} не задан, а getWebhookInfo не сообщает, передан ли secret_token: чужой запрос к '
                    f'webhook не отличить от Telegram.',
                    f'Сгенерируйте секрет, сохраните его в {secret_env}, передайте как secret_token в setWebhook и '
                    f'отклоняйте запросы '
                    'без совпадающего заголовка X-Telegram-Bot-Api-Secret-Token.',
                    [generate, _set_webhook_command(secret_env, test=test)],
                )
            )
        elif not _SECRET.fullmatch(secret):
            found.append(
                (
                    'webhook-secret',
                    'fail',
                    'secret-invalid',
                    f'{secret_env} не подходит для secret_token.',
                    'Нужно 1–256 символов из A-Z, a-z, 0-9, _ и -: сгенерируйте новый секрет.',
                    [generate],
                )
            )
        else:
            found.append(
                (
                    'webhook-secret',
                    'pass',
                    'secret-configured',
                    f'Секрет найден в {secret_env}. Bot API не показывает, передан ли он в setWebhook: '
                    'сервер должен сверять заголовок X-Telegram-Bot-Api-Secret-Token.',
                )
            )
    return found


def _token_value(env_file: Path | None) -> str | None:
    """Raw BOT_TOKEN with BotSettings.from_env precedence; None when the project .env is unreadable."""
    value = os.environ.get('BOT_TOKEN')
    if value is not None or env_file is None:
        return value or ''
    try:
        return read_env_file(env_file).get('BOT_TOKEN', '') if env_file.is_file() else ''
    except (ValueError, OSError):
        return None


def diagnose(
    target: str | Path,
    *,
    require_token: bool,
    webhook: bool = False,
    expect: str | None = None,
    webhook_secret_env: str = 'WEBHOOK_SECRET',
    now: float | None = None,
) -> dict[str, Any]:
    if expect not in (None, 'polling', 'webhook'):
        raise ValueError("expect must be None, 'polling' or 'webhook'")
    if not isinstance(webhook_secret_env, str) or not _ENV_NAME.fullmatch(webhook_secret_env):
        raise ValueError('Invalid webhook secret environment variable name')
    checks: list[dict[str, Any]] = []
    network = False

    def check(
        name: str, status: str, reason: str, detail: str, *, fix: str = '', commands: list[dict[str, Any]] | None = None
    ) -> None:
        checks.append(
            {
                'name': name,
                'status': status,
                'detail': detail,
                'reason': reason,
                'remediation': {'summary': fix, 'commands': commands or []},
            }
        )

    def finish() -> dict[str, Any]:
        return {
            'passed': not any(item['status'] == 'fail' for item in checks),
            'network': network,
            'checks': checks,
            'limits': _WEBHOOK_LIMITS if webhook else _LIMITS,
            'schema_version': 1,
            'tool_probes_attempted': (['python -I -B adapter imports'] if sdk_probed else [])
            + (['node --version'] if node_executed else [])
            + (['getWebhookInfo'] if network else []),
            'suggestions_executed': False,
        }

    node_executed = False
    sdk_probed = False
    try:
        supplied = Path(target).expanduser().absolute()
        if any(_linked(parent) for parent in (supplied, *supplied.parents)):
            check(
                'project',
                'fail',
                'linked-project',
                'Каталог проекта проходит через symbolic link или junction.',
                fix='Укажите настоящий каталог проекта, чтобы диагностика не читала другое дерево.',
                commands=[
                    _command(['python', '-m', 'telegram_patterns', 'doctor', '<PROJECT_DIRECTORY>'], placeholders=True)
                ],
            )
            return finish()
        root = supplied.resolve(strict=True)
        if not root.is_dir():
            check(
                'project',
                'fail',
                'project-not-directory',
                'Doctor ожидает каталог проекта.',
                fix='Укажите каталог, содержащий конфигурацию приложения.',
                commands=[_rerun()],
            )
            return finish()
    except (OSError, ValueError, RuntimeError, TypeError):
        check(
            'project',
            'fail',
            'project-unavailable',
            'Каталог не найден или недоступен.',
            fix='Проверьте путь и права чтения; существующие файлы создавать или удалять не нужно.',
            commands=[
                _command(['python', '-m', 'telegram_patterns', 'doctor', '<PROJECT_DIRECTORY>'], placeholders=True)
            ],
        )
        return finish()

    check(
        'python',
        'pass' if sys.version_info >= (3, 11) else 'fail',
        'python-supported' if sys.version_info >= (3, 11) else 'python-too-old',
        '.'.join(map(str, sys.version_info[:3])),
        fix='' if sys.version_info >= (3, 11) else 'Выберите Python >=3.11 и отдельное окружение приложения.',
        commands=[] if sys.version_info >= (3, 11) else [_command(['python', '--version'])],
    )
    try:
        library = importlib.metadata.version('awesome-telegram-patterns')
        if isinstance(library, str) and _VERSION.fullmatch(library):
            check('library', 'pass', 'library-installed', library)
        else:
            check(
                'library',
                'fail',
                'library-version-invalid',
                'Не удалось определить версию локальной библиотеки.',
                fix='Установите согласованный предоставленный wheel в окружение приложения.',
                commands=_repair_install(),
            )
    except importlib.metadata.PackageNotFoundError:
        check(
            'library',
            'fail',
            'library-not-installed',
            'Метаданные установленной библиотеки отсутствуют.',
            fix='Запустите doctor из окружения, куда установлен предоставленный wheel.',
            commands=_repair_install(),
        )

    try:
        sdk = importlib.metadata.version('aiogram')
    except importlib.metadata.PackageNotFoundError:
        check(
            'aiogram',
            'fail',
            'sdk-missing',
            'Aiogram не установлен в текущем Python окружении.',
            fix='Для нашего aiogram starter установите предоставленный wheel с extra. Core recipes/init работают '
            'без SDK; другой стек сохраняйте.',
            commands=_repair_install(),
        )
    else:
        match = _VERSION.fullmatch(sdk) if isinstance(sdk, str) else None
        supported = bool(match and tuple(map(int, sdk.split('.')[:2])) >= (3, 31) and sdk.split('.')[0] == '3')
        check(
            'aiogram',
            'pass' if supported else 'fail',
            'sdk-supported' if supported else 'sdk-incompatible',
            sdk if match else 'Версия SDK не распознана.',
            fix='' if supported else 'Нужен aiogram >=3.31,<4. Проверьте ограничения приложения перед изменением SDK.',
            commands=[] if supported else _repair_install(),
        )
        if supported:
            if sdk != '3.31.0':
                check(
                    'sdk-tested-version',
                    'warn',
                    'sdk-not-tested',
                    'Эта поставка проверена на aiogram 3.31.0.',
                    fix='Проверьте выбранную версию своими тестами; смена SDK не выполняется автоматически.',
                    commands=[_command(['python', '-m', 'pip', 'check'])],
                )
            try:
                spec = importlib.util.find_spec('aiogram')
                expected = importlib.metadata.distribution('aiogram').locate_file('aiogram/__init__.py')
                verified_origin = bool(
                    spec
                    and spec.origin
                    and Path(spec.origin).resolve(strict=True) == Path(str(expected)).resolve(strict=True)
                )
            except (OSError, ValueError, importlib.metadata.PackageNotFoundError):
                verified_origin = False
            if not verified_origin:
                check(
                    'python-exports',
                    'fail',
                    'adapter-origin-unverified',
                    'Aiogram import не совпадает с установленным SDK.',
                    fix='Проверьте имена aiogram.py/aiogram и sys.path: локальный файл может подменять SDK. '
                    'Запустите установленный пакет из правильного окружения; файлы не изменяются автоматически.',
                    commands=[_rerun()],
                )
            else:
                sdk_probed = True
                exports = _sdk_probe()
                check(
                    'python-exports',
                    'pass' if exports else 'fail',
                    'adapter-ready' if exports else 'adapter-import-failed',
                    'Публичные adapters доступны в изолированном установленном окружении.'
                    if exports
                    else 'Не удалось загрузить публичные adapters из установленного окружения.',
                    fix=''
                    if exports
                    else 'Проверьте зависимости и установленную библиотеку в том же interpreter. '
                    'User-site/source-only imports не входят в изолированную проверку.',
                    commands=[] if exports else _repair_install(),
                )

    text, reason = _read_manifest(root / 'pyproject.toml')
    if text is None:
        optional = reason == 'missing-manifest'
        check(
            'pyproject',
            'warn' if optional else 'fail',
            reason,
            'Нет pyproject.toml; проект может использовать другой формат.'
            if optional
            else 'Pyproject недоступен как UTF-8 файл до 256 KiB.',
            fix='Проверьте зависимости в принятом формате проекта; миграция не обязательна.'
            if optional
            else 'Проверьте права, UTF-8 и размер файла; укажите обычный файл внутри настоящего проекта.',
            commands=[_rerun()],
        )
    else:
        try:
            tomllib.loads(text)
            check('pyproject', 'pass', 'toml-valid', 'TOML прочитан; код проекта не выполнялся.')
        except (ValueError, RecursionError):
            check(
                'pyproject',
                'fail',
                'toml-invalid',
                'Синтаксис pyproject.toml поврежден.',
                fix='Исправьте TOML в редакторе, сохранив зависимости приложения; содержимое файла в отчет не '
                'включается.',
                commands=[_rerun()],
            )

    env_file = root / '.env' if webhook and not _linked(root / '.env') else None
    raw_token = _token_value(env_file)
    token: str | None = None
    token_fix = (
        'Для offline запуска token не нужен. Для live задайте BOT_TOKEN через свой механизм секретов'
        + (' или в .env проекта' if webhook else '')
        + '; doctor не подтверждает действительность token без --webhook.'
    )
    token_retry = [
        _command(['python', '-m', 'telegram_patterns', 'doctor', '.', '--webhook' if webhook else '--require-token'])
    ]
    strict = require_token or webhook
    if raw_token is None:
        check(
            'token-format',
            'fail' if strict else 'warn',
            'env-file-invalid',
            '.env проекта не читается как строки KEY=VALUE до 64 KiB.',
            fix='Исправьте .env по образцу .env.example; значения в отчет не включаются.',
            commands=token_retry,
        )
    elif not raw_token:
        check(
            'token-format',
            'fail' if strict else 'warn',
            'token-missing',
            'BOT_TOKEN нет ни в окружении, ни в .env проекта.'
            if webhook
            else 'BOT_TOKEN отсутствует в окружении; .env не читается.',
            fix=token_fix,
            commands=token_retry,
        )
    elif 'REPLACE_WITH' in raw_token:
        check(
            'token-format',
            'fail' if strict else 'warn',
            'token-placeholder',
            'BOT_TOKEN содержит заглушку из .env.example.',
            fix='Замените заглушку токеном тестового бота от @BotFather.',
            commands=token_retry,
        )
    else:
        try:
            token = BotSettings(token=raw_token).token
        except ValueError:
            check(
                'token-format',
                'fail' if strict else 'warn',
                'token-format-invalid',
                'BOT_TOKEN имеет неверный формат.',
                fix=token_fix,
                commands=token_retry,
            )
        else:
            source = 'окружении' if os.environ.get('BOT_TOKEN') else '.env проекта'
            check(
                'token-format',
                'pass',
                'token-format-valid',
                f'BOT_TOKEN присутствует в {source}; проверен только формат.',
            )

    test_environment = False
    if webhook:
        flag = os.environ.get('TELEGRAM_TEST_ENVIRONMENT')
        if flag is None and env_file is not None:
            try:
                flag = read_env_file(env_file).get('TELEGRAM_TEST_ENVIRONMENT') if env_file.is_file() else None
            except (ValueError, OSError):
                flag = None  # already reported as env-file-invalid
        try:
            test_environment = env_flag(flag or '', 'TELEGRAM_TEST_ENVIRONMENT')
        except ValueError:
            check(
                'telegram-environment',
                'fail',
                'test-environment-invalid',
                'TELEGRAM_TEST_ENVIRONMENT не распознан.',
                fix='Укажите 1/true/yes/on для тестового окружения Telegram или 0/false/no/off (или удалите '
                'переменную) для основного.',
                commands=token_retry,
            )
            token = None
        else:
            check(
                'telegram-environment',
                'pass',
                'test-environment' if test_environment else 'main-environment',
                'Тестовое окружение Telegram: запросы идут на /bot<token>/test/<method>, нужен бот из тестового '
                'аккаунта.'
                if test_environment
                else 'Основное окружение Telegram.',
            )
    if webhook:
        if token is None:
            check(
                'webhook',
                'fail',
                'token-required',
                'Для --webhook нужен BOT_TOKEN в правильном формате.',
                fix='Исправьте проверку token-format и повторите doctor --webhook.',
                commands=token_retry,
            )
        else:
            network = True
            try:
                info = _fetch_webhook_info(token, test=test_environment)
            except _WebhookUnavailable as failure:
                if failure.reason == 'token-rejected':
                    check(
                        'token-valid',
                        'fail',
                        'token-rejected',
                        'Тестовое окружение Telegram отклонило BOT_TOKEN.'
                        if test_environment
                        else 'Telegram отклонил BOT_TOKEN.',
                        fix='Тестовое окружение отдельное: токен основного бота там не действует, создайте бота '
                        'через @BotFather из тестового аккаунта.'
                        if test_environment
                        else 'Проверьте токен или выпустите новый в @BotFather (/token); старый перестанет работать.',
                        commands=token_retry,
                    )
                elif failure.reason == 'api-unreachable':
                    check(
                        'webhook',
                        'fail',
                        'api-unreachable',
                        'Bot API недоступен: сеть, прокси или DNS не пропускают запрос.',
                        fix='Проверьте доступ к api.telegram.org, HTTPS_PROXY и сертификаты прокси; повторите '
                        'doctor --webhook.',
                        commands=token_retry,
                    )
                else:
                    check(
                        'webhook',
                        'fail',
                        'api-error',
                        'Bot API вернул неожиданный ответ на getWebhookInfo.',
                        fix='Повторите позже; если ошибка сохраняется, проверьте адрес Bot API и прокси.',
                        commands=token_retry,
                    )
            else:
                check('token-valid', 'pass', 'token-accepted', 'Telegram принял BOT_TOKEN (getWebhookInfo).')
                secret = os.environ.get(webhook_secret_env)
                if secret is None and env_file is not None:
                    try:
                        secret = read_env_file(env_file).get(webhook_secret_env) if env_file.is_file() else None
                    except (ValueError, OSError):
                        secret = None
                for name, status, reason, detail, *repair in _webhook_checks(
                    info,
                    expect=expect,
                    secret_env=webhook_secret_env,
                    secret=secret,
                    now=time.time() if now is None else now,
                    test=test_environment,
                ):
                    check(
                        name,
                        status,
                        reason,
                        detail,
                        fix=repair[0] if repair else '',
                        commands=repair[1] if repair else None,
                    )

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
            check(
                'mini-app-manifest',
                'fail',
                reason,
                'Mini App package.json недоступен как UTF-8 файл до 256 KiB.',
                fix='Проверьте обычный mini-app/package.json, права, UTF-8 и размер. Другой frontend layout '
                'проверяйте инструментами проекта.',
                commands=[_rerun()],
            )
        else:
            try:
                data = json.loads(text)
            except (ValueError, RecursionError):
                check(
                    'mini-app-manifest',
                    'fail',
                    'json-invalid',
                    'Синтаксис Mini App package.json поврежден.',
                    fix='Исправьте JSON без изменения выбранного frontend стека.',
                    commands=[_rerun()],
                )
            else:
                dependencies = data.get('dependencies') if isinstance(data, dict) else None
                dependency = dependencies.get('@awesome-telegram/patterns') if isinstance(dependencies, dict) else None
                valid = isinstance(dependency, str) and bool(dependency.strip())
                check(
                    'mini-app-manifest',
                    'pass' if valid else 'fail',
                    'mini-app-dependency-declared' if valid else 'mini-app-dependency-missing',
                    'Зависимость библиотеки объявлена; установка и совместимость frontend не подтверждены.'
                    if valid
                    else 'Нет непустой строковой зависимости @awesome-telegram/patterns в dependencies.',
                    fix=''
                    if valid
                    else 'Укажите предоставленный tarball согласованной версии в package.json; сохраняйте свой '
                    'frontend.',
                    commands=[]
                    if valid
                    else [_command(['npm', 'install', '<PROVIDED_TARBALL>'], cwd='mini-app', placeholders=True)],
                )
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        check(
            'npm',
            'pass' if npm else 'fail',
            'npm-on-path' if npm else 'npm-missing',
            'Npm найден в PATH; пакеты не устанавливались.' if npm else 'Npm отсутствует в PATH.',
            fix='' if npm else 'Установите поддерживаемую Node LTS с npm и откройте новый terminal.',
            commands=[] if npm else [_command(['npm', '--version'], cwd='mini-app')],
        )
        node = shutil.which('node')
        if not node:
            check(
                'node',
                'fail',
                'node-missing',
                'Node отсутствует в PATH.',
                fix='Выберите поддерживаемую Node LTS, технический минимум пакета >=20. Эта поставка проверяется на '
                'Node 24.',
                commands=[_command(['node', '--version'], cwd='mini-app')],
            )
        else:
            # Fixed trusted-tool probe receives no token or arbitrary inherited secrets/options.
            environment = _tool_environment()
            try:
                node_executed = True
                result = subprocess.run(
                    [node, '--version'],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env=environment,
                    shell=False,
                )
                match = re.fullmatch(r'v(\d+)\.\d+\.\d+', result.stdout.strip())
                node_ok = bool(result.returncode == 0 and match and int(match.group(1)) >= 20)
                reason = (
                    'node-supported'
                    if node_ok
                    else 'node-too-old'
                    if result.returncode == 0 and match
                    else 'node-probe-failed'
                )
                check(
                    'node',
                    'pass' if node_ok else 'fail',
                    reason,
                    match.group(0) if match and result.returncode == 0 else 'Не удалось прочитать версию Node.',
                    fix='' if node_ok else 'Проверьте установленный Node и PATH; используйте поддерживаемую LTS >=20.',
                    commands=[] if node_ok else [_command(['node', '--version'], cwd='mini-app')],
                )
                if node_ok and match and int(match.group(1)) != 24:
                    check(
                        'node-tested-version',
                        'warn',
                        'node-not-tested',
                        'Эта поставка проверена на Node 24; минимальная версия не является рекомендацией production.',
                        fix='Выберите поддерживаемую LTS и проверьте свой frontend build; версии клиентов '
                        'проверяются отдельно.',
                        commands=[_command(['npm', 'run', 'build'], cwd='mini-app')],
                    )
            except (OSError, subprocess.TimeoutExpired, UnicodeError):
                check(
                    'node',
                    'fail',
                    'node-probe-failed',
                    'Локальная команда node --version завершилась ошибкой или timeout.',
                    fix='Проверьте установленный Node и PATH; вывод процесса в отчет не включается.',
                    commands=[_command(['node', '--version'], cwd='mini-app')],
                )
    return finish()
