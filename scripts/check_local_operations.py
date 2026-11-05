"""Проверка эксплуатационных команд только в собственной synthetic test-среде.

Нужен отдельный consumer с установленными pattern/shop wheels. Не принимает
рабочую БД, токен, .env, URL или команду активации. Сеть fixture ограничена loopback.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import queue
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener


class CheckFailure(RuntimeError):
    """Сообщения содержат только фиксированное имя проваленной стадии."""


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CheckFailure('invalid-arguments')


def require(condition: bool, stage: str) -> None:
    if not condition:
        raise CheckFailure(stage)


def child_environment() -> dict[str, str]:
    # Не читаем .env; не передаем credentials, PYTHONPATH или proxy в fixture.
    allowed = {'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP',
               'TMPDIR', 'LANG', 'LC_ALL', 'USERPROFILE', 'HOME', 'LOCALAPPDATA'}
    result = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    result['PYTHONUTF8'] = '1'
    return result


def new_output(path: Path) -> Path:
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise CheckFailure('output-link-refused')
    path.mkdir(parents=True, exist_ok=False)
    return path


def run_command(argv: list[str], root: Path, *, expected: int = 0) -> dict:
    result = subprocess.run(argv, cwd=root, env=child_environment(), capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=90)
    require(result.returncode == expected, 'child-command-exit')
    # Не копируем сырой stdout/stderr в report или exception.
    value = json.loads(result.stdout if result.stdout.strip() else result.stderr)
    require(isinstance(value, dict), 'child-command-json')
    return value


def schema_fingerprint(path: Path) -> tuple:
    with closing(sqlite3.connect(path.absolute().as_uri() + '?mode=ro', uri=True)) as db:
        definitions = tuple(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"))
        # Версии хранятся в строках, поэтому один sqlite_master их не проверяет.
        versions = tuple((table, tuple(db.execute(f'SELECT {column} FROM {table} ORDER BY {column}')))
                         for table, column in (('shop_schema', 'version'),
                                               ('payment_ledger_meta', 'version'),
                                               ('telegram_pattern_outbox_meta', 'schema_version')))
        return definitions, versions


def fixture_rollback_gate(path: Path, expected_schema: tuple) -> str:
    """Только test gate для повторного запуска ТОГО ЖЕ установленного артефакта.

    Не доказывает совместимость двух разных releases и не запускает приложение.
    OS lock координирует соблюдающих его writers; внешних writers останавливает owner.
    """
    from telegram_shop_example.recovery_state import readiness
    from telegram_shop_example.storage import ProcessLock

    if not path.is_file():
        return 'database-unverified'
    try:
        owner = ProcessLock(path)
    except RuntimeError:
        return 'writer-active'
    try:
        if not readiness(path)['ready']:
            return 'maintenance'
        if schema_fingerprint(path) != expected_schema:
            return 'compatibility-unverified'
        return 'same-artifact-restart-only'
    finally:
        owner.close()


class FixtureProcess:
    def __init__(self, root: Path, database: Path, frontend: Path):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.process = subprocess.Popen(
            [sys.executable, '-I', '-X', 'utf8', '-m', 'telegram_shop_example.offline',
             '--database', str(database), '--frontend', str(frontend), '--port', str(self.port)],
            cwd=root, env=child_environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1)
        self.lines: queue.Queue[str | None] = queue.Queue()
        def read() -> None:
            for line in self.process.stdout:
                self.lines.put(line)
            self.lines.put(None)
        threading.Thread(target=read, daemon=True).start()

    def message(self, phase: str) -> dict:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            require(line is not None, 'fixture-exited')
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if value.get('phase') == phase or value.get('action') == phase:
                return value
        raise CheckFailure('fixture-message-timeout')

    def request(self, action: str) -> dict:
        self.process.stdin.write(json.dumps({'action': action}) + '\n')
        self.process.stdin.flush()
        return self.message(action)

    def probe(self) -> dict:
        start = time.monotonic()
        # ProxyHandler({}) не отправляет даже loopback через proxy пользователя.
        with build_opener(ProxyHandler({})).open(
                f'http://127.0.0.1:{self.port}/api/readiness', timeout=5) as response:
            result = json.load(response)
            require(response.status == 200 and result['ready'], 'readiness-not-ready')
        return {'http_status': 200, 'ready': True,
                'latency_ms': round((time.monotonic() - start) * 1000, 2)}

    def close(self) -> None:
        if self.process.poll() is not None:
            for stream in (self.process.stdin, self.process.stdout):
                stream.close()
            return
        try:
            self.process.stdin.write('{"action":"stop"}\n')
            self.process.stdin.flush()
            result = self.message('closed')
            require(result['session_closed'] and result['lock_released'] and
                    result['external_network_attempts'] == 0 and
                    result['telegram_requests'] is False, 'fixture-close')
            require(self.process.wait(timeout=10) == 0, 'fixture-close-exit')
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=10)
            for stream in (self.process.stdin, self.process.stdout):
                stream.close()


def worker(root: Path) -> dict:
    from importlib.metadata import version
    import telegram_patterns
    import telegram_shop_example
    from telegram_patterns import SQLiteOutbox
    from telegram_shop_example.offline import TOKEN, guards
    from telegram_shop_example.store import Store

    network_attempts = guards()
    origin = {}
    for name, module in (('library', telegram_patterns), ('application', telegram_shop_example)):
        module_path = Path(module.__file__).resolve()
        require(module_path.is_relative_to(Path(sys.prefix).resolve()), 'installed-origin-required')
        origin[name + '_module_sha256'] = hashlib.sha256(module_path.read_bytes()).hexdigest()
    require(version('awesome-telegram-patterns') == '0.28.0' and
            version('awesome-telegram-shop-example') == '0.1.0', 'review-version-before-use')
    folders = {name: root / name for name in ('data', 'backups', 'recovery', 'frontend')}
    for folder in folders.values():
        folder.mkdir(mode=0o700)
    (folders['frontend'] / 'assets').mkdir(mode=0o700)
    (folders['frontend'] / 'index.html').write_text('<html>Local operations fixture</html>', encoding='utf-8')
    live = folders['data'] / 'live.sqlite'
    Store(live, TOKEN, terms_version='demo-v1')
    outbox = SQLiteOutbox(live)
    outbox.initialize()
    with closing(sqlite3.connect(live)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        outbox.enqueue(db, 'operations-fixture', 'original-unknown', {'synthetic': True}, now=100)
    claim = outbox.claim('operations-fixture', 'old-writer', now=101)
    outbox.mark_unknown(claim, now=102)
    original = outbox.get('operations-fixture', 'original-unknown')
    stages = []
    process = FixtureProcess(root, live, folders['frontend'])
    try:
        process.message('ready')
        baseline_schema = schema_fingerprint(live)  # Includes the application's startup-owned tables.
        probe = process.probe()
        require(fixture_rollback_gate(live, baseline_schema) == 'writer-active', 'active-writer-refusal')
        stats = process.request('stats')
        require(stats['external_network_attempts'] == 0 and stats['telegram_requests'] is False,
                'fixture-network')
        stages.extend(['installed-loopback-start', 'readiness-probe', 'active-writer-refused'])
    finally:
        process.close()
    require(fixture_rollback_gate(live, baseline_schema) == 'same-artifact-restart-only', 'stopped-lock-release')
    stages.append('graceful-stop-and-lock-release')

    python = [sys.executable, '-I', '-X', 'utf8', '-m']
    snapshot = folders['backups'] / 'checkpoint.sqlite'
    backup = python + ['telegram_patterns', 'backup-sqlite', str(live), str(snapshot),
                       '--source-root', str(folders['data']), '--target-root', str(folders['backups']), '--json']
    backup_result = run_command(backup, root)
    snapshot_sha = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    require(backup_result['published'] and backup_result['cleanup_complete'] and
            backup_result['sha256'] == snapshot_sha, 'backup-result-verified')
    run_command(backup, root, expected=2)
    require(hashlib.sha256(snapshot.read_bytes()).hexdigest() == snapshot_sha, 'backup-overwrite-preserved')
    stages.extend(['backup-cli', 'existing-backup-refused'])
    # Generic restore доказывает данные; сырой restored-файл НИКОГДА не запускается.
    raw = folders['recovery'] / 'raw-inspect-only.sqlite'
    restore = python + ['telegram_patterns', 'restore-sqlite-new', str(snapshot), str(raw),
                        '--source-root', str(folders['backups']), '--target-root', str(folders['recovery']), '--json']
    restore_result = run_command(restore, root)
    raw_sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    require(restore_result['published'] and restore_result['cleanup_complete'] and
            restore_result['sha256'] == raw_sha, 'restore-result-verified')
    run_command(restore, root, expected=2)
    require(hashlib.sha256(raw.read_bytes()).hexdigest() == raw_sha, 'restore-overwrite-preserved')
    require(SQLiteOutbox(raw).get('operations-fixture', 'original-unknown') == original,
            'raw-restore-retains-unknown')
    stages.extend(['restore-new-cli', 'existing-restore-refused', 'unknown-identity-preserved'])
    candidate = folders['recovery'] / 'closed-candidate.sqlite'
    prepare = python + ['telegram_shop_example.recovery', 'prepare', '--live', str(live),
                        '--snapshot', str(snapshot), '--candidate', str(candidate),
                        '--live-root', str(folders['data']), '--snapshot-root', str(folders['backups']),
                        '--target-root', str(folders['recovery']), '--bot-id', '100',
                        '--expected-snapshot-sha256', snapshot_sha]
    prepared = run_command(prepare, root)
    require(not prepared['ready'] and prepared['cleanup_complete'], 'prepare-remains-closed')
    inspected = run_command(python + ['telegram_shop_example.recovery', 'inspect',
                                     '--candidate', str(candidate), '--target-root', str(folders['recovery'])],
                            root, expected=3)
    require(not inspected['ready'] and inspected['prepared'], 'closed-candidate-required')
    candidate_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
    require(fixture_rollback_gate(candidate, schema_fingerprint(candidate)) == 'maintenance', 'marker-refusal')
    require(hashlib.sha256(candidate.read_bytes()).hexdigest() == candidate_sha, 'marker-refusal-no-write')
    stages.extend(['prepare-closed-cli', 'inspect-maintenance-cli', 'marker-rollback-refused'])
    # Ошибка совместимости на отдельной synthetic copy; production schema не изменяется.
    future = folders['recovery'] / 'future-fixture.sqlite'
    with closing(sqlite3.connect(live)) as source, closing(sqlite3.connect(future)) as target:
        source.backup(target)
    with closing(sqlite3.connect(future)) as db, db:
        db.execute('UPDATE shop_schema SET version=999')  # Same SQL definition, incompatible version rows.
    future_sha = hashlib.sha256(future.read_bytes()).hexdigest()
    require(fixture_rollback_gate(future, baseline_schema) == 'compatibility-unverified', 'schema-refusal')
    require(hashlib.sha256(future.read_bytes()).hexdigest() == future_sha, 'schema-refusal-no-write')
    stages.append('schema-rollback-refused')
    # Повтор прежней команды, прежний файл данных, тот же установленный wheel.
    process = FixtureProcess(root, live, folders['frontend'])
    try:
        process.message('ready')
        process.probe()
        require(outbox.get('operations-fixture', 'original-unknown') == original, 'restart-retains-unknown')
        stages.append('same-artifact-command-restart')
    finally:
        process.close()
    try:
        with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{process.port}/api/readiness', timeout=1):
            raise CheckFailure('stopped-probe-still-ready')
    except (OSError, HTTPError):
        stages.append('stopped-probe-unavailable')
    require(network_attempts[0] == 0, 'worker-external-network')
    return {'passed': True, 'kind': 'local-operations-fixture', 'library_version': '0.28.0',
            'application_version': '0.1.0', 'installed_origins_verified': True, **origin,
            'stages': stages, 'readiness': probe,
            'backup_directory_synced': backup_result['directory_synced'],
            'restore_directory_synced': restore_result['directory_synced'],
            'candidate_ready': False, 'schema_refusal_same_sql_definition': True,
            'external_network_attempts': 0,
            'scope': 'Synthetic local installed consumer; no selected production host, live secret store, Telegram or provider.',
            'rollback_scope': 'Same installed artifact command restart; writer/marker/schema refusal witnesses. No cross-version compatibility or restored-service activation.'}


def main() -> int:
    parser = SafeParser(description=__doc__)
    parser.add_argument('--python', type=Path, help='Python отдельного установленного consumer')
    parser.add_argument('--output', type=Path, help='Новый каталог агрегированного report.json')
    parser.add_argument('--_worker', type=Path, help=argparse.SUPPRESS)
    try:
        args = parser.parse_args()
        if args._worker:
            require(Path.cwd().resolve() == args._worker.resolve(), 'owned-worker-directory')
            result = worker(args._worker)
        else:
            require(args.python is not None and args.python.is_file() and args.output is not None,
                    'provide-installed-python-and-new-output')
            output = new_output(args.output)
            with tempfile.TemporaryDirectory(prefix='telegram-operations-') as folder:
                root = Path(folder).resolve()
                result = run_command([str(args.python.resolve()), '-I', '-X', 'utf8', str(Path(__file__).resolve()),
                                      '--_worker', str(root)], root)
            (output / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                                              encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        # Paths, child stdout, credentials and SQLite diagnostics stay out of errors.
        code = str(error) if isinstance(error, CheckFailure) else 'local-operations-failed'
        print(json.dumps({'passed': False, 'code': code}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
