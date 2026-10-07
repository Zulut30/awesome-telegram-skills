"""Execute the documented quickstart in a fresh external consumer: PowerShell on Windows, bash elsewhere.

Explicit verification installs dependencies (may use package registries), but
never supplies a Telegram token or starts the live app. It owns only its new
temporary project, log directory and preview process tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BLOCKS = ('parameters', 'setup', 'init', 'offline', 'frontend', 'preview')


WINDOWS = os.name == 'nt'


def quote(value: str | Path) -> str:
    """PowerShell single-quoted literal or POSIX shell word."""
    return "'" + str(value).replace("'", "''") + "'" if WINDOWS else shlex.quote(str(value))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--tarball', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New proof directory')
    parser.add_argument('--guide', type=Path, default=ROOT / 'docs/quickstart.md', help='Guide to execute, e.g. docs/en/quickstart.md')
    args = parser.parse_args()
    shell = (shutil.which('pwsh') or shutil.which('powershell')) if WINDOWS else shutil.which('bash')
    node = shutil.which('node')
    if not shell or not node:
        parser.error('PowerShell (Windows) or bash, and Node are required')
    guide = args.guide.resolve()
    document = guide.read_text(encoding='utf-8')
    if guide == (ROOT / 'docs/quickstart.md').resolve():
        portable = (ROOT / '.agents/skills/telegram-code-patterns/references/quickstart.md').read_text(encoding='utf-8')
        if document != portable:
            raise RuntimeError('Portable first-run guide differs from canonical guide')
    # The first bold version in the guide names the release it was written for.
    matched = re.search(r'\*\*(\d+\.\d+\.\d+)\*\*', document)
    if not matched:
        raise RuntimeError('Guide must identify its supplied local version')
    version = matched.group(1)
    marker, language = ('quickstart', 'powershell') if WINDOWS else ('quickstart-bash', 'bash')
    found = re.findall(rf'<!-- {marker}:([\w-]+) -->\s*```{language}\n(.*?)\n```', document, re.S)
    if tuple(name for name, _ in found) != BLOCKS:
        raise RuntimeError('Missing, reordered or duplicate documented command blocks')
    blocks = dict(found)
    sources = [supplied.resolve(strict=True) for supplied in (args.wheel, args.tarball)]
    if any(not source.is_file() for source in sources):
        raise RuntimeError('Provide existing local artifact files')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    consumer = Path(tempfile.mkdtemp(prefix='telegram first run ')).resolve()
    artifacts = consumer / 'supplied artifacts with spaces'
    artifacts.mkdir()
    artifact_proof = []
    for source in sources:
        target = artifacts / source.name
        shutil.copyfile(source, target)
        artifact_proof.append({'name': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    workspace = consumer / 'first project with spaces'
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1', 0))
        port = reserve.getsockname()[1]
    if WINDOWS:
        parameters = '\n'.join((f'$tgArtifacts = {quote(artifacts)}', f'$tgWorkspace = {quote(workspace)}', f'$tgPreviewPort = {port}'))
    else:  # set -e stops at the `false` that ends a failed documented chain
        parameters = '\n'.join(('set -e', f'TG_ARTIFACTS={quote(artifacts)}', f'TG_WORKSPACE={quote(workspace)}', f'TG_PREVIEW_PORT={port}'))
    suffix = '.ps1' if WINDOWS else '.sh'
    encoding = 'utf-8-sig' if WINDOWS else 'utf-8'
    def invoke(script: Path) -> list[str]:
        return [shell, '-NoProfile', '-NonInteractive', '-File', str(script)] if WINDOWS else [shell, str(script)]
    environment = dict(os.environ)
    for name in ('BOT_TOKEN', 'PYTHONPATH', 'PYTHONHOME', 'NODE_OPTIONS'):
        environment.pop(name, None)
    environment['PYTHONUTF8'] = '1'
    commands = parameters + '\n' + '\n'.join(blocks[name] for name in BLOCKS[1:-1]) + '\n'
    script = output / f'documented-commands{suffix}'
    script.write_text(commands, encoding=encoding, newline='\n')

    def stop_owned(process: subprocess.Popen) -> None:
        if process.poll() is None:
            if WINDOWS:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=20)
            else:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=20)

    def run(name: str, argv: list[str], *, cwd: Path, expected: int = 0) -> str:
        process = subprocess.Popen(argv, cwd=cwd, env=environment, stdout=subprocess.PIPE, start_new_session=not WINDOWS,
                                   stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        try:
            stdout, stderr = process.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            stop_owned(process)
            stdout, stderr = process.communicate()
            (output / f'{name}.log').write_text(stdout + stderr, encoding='utf-8', newline='\n')
            raise RuntimeError(f'{name}: timeout; stopped the owned process tree') from None
        (output / f'{name}.log').write_text(stdout + stderr, encoding='utf-8', newline='\n')
        if process.returncode != expected:
            raise RuntimeError(f'{name}: unexpected status; inspect the owned proof log')
        return stdout

    run('guide-install-and-build', invoke(script), cwd=consumer)
    project = workspace / 'my-bot'
    python = project / ('.venv/Scripts/python.exe' if WINDOWS else '.venv/bin/python')
    origins = json.loads(run('installed-origin', [str(python), '-c',
        "import json,sys,telegram_patterns,importlib.metadata as m; print(json.dumps({'prefix':sys.prefix,'module':telegram_patterns.__file__,'version':m.version('awesome-telegram-patterns'),'aiogram':m.version('aiogram')}))"], cwd=project))
    if origins['version'] != version or not Path(origins['module']).resolve().is_relative_to(project / '.venv'):
        raise RuntimeError('Bot does not use the newly installed local wheel')
    offline = json.loads(run('offline', [str(python), 'offline.py'], cwd=project))
    if not offline['passed'] or offline['network'] or not offline['session_closed'] or offline['methods'] != ['SendMessage', 'AnswerCallbackQuery', 'SendMessage']:
        raise RuntimeError('Offline bot behavior differs from the documented result')
    if offline.get('mini_app_backend') != {'signed': [200, 'Анна'], 'changed': [401, 'init-data-invalid'], 'missing': [401, 'authentication-required']}:
        raise RuntimeError('Mini App backend initData check differs from the documented result')
    doctor = json.loads(run('doctor', [str(python), '-m', 'telegram_patterns', 'doctor', '.'], cwd=project))
    if not doctor['passed'] or doctor['network']:
        raise RuntimeError('Local doctor did not pass without a token')
    manifest = json.loads((project / 'mini-app/node_modules/@awesome-telegram/patterns/package.json').read_text(encoding='utf-8'))
    if manifest['version'] != version:
        raise RuntimeError('Mini App did not install the provided tarball')
    marker = workspace / 'user-owned-marker.txt'
    marker.write_bytes(b'keep this first run')
    before = {str(file.relative_to(workspace)): hashlib.sha256(file.read_bytes()).hexdigest()
              for file in workspace.rglob('*') if file.is_file()}
    repeat = output / f'repeat-setup{suffix}'
    repeat.write_text(parameters + '\n' + blocks['setup'] + '\n', encoding=encoding, newline='\n')
    run('existing-workspace-refused', invoke(repeat), cwd=consumer, expected=1)
    after = {str(file.relative_to(workspace)): hashlib.sha256(file.read_bytes()).hexdigest()
             for file in workspace.rglob('*') if file.is_file()}
    if before != after:
        raise RuntimeError('Repeated first-run setup changed an existing workspace')
    preview = output / f'documented-preview{suffix}'
    preview.write_text(parameters + '\n' + blocks['preview'] + '\n', encoding=encoding, newline='\n')
    base = f'http://127.0.0.1:{port}'
    with (output / 'preview.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(invoke(preview), cwd=project / 'mini-app', env=environment,
                                   stdout=log, stderr=log, start_new_session=not WINDOWS)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Owned preview process stopped before readiness')
                try:
                    with opener.open(base, timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError('Owned loopback preview did not become ready')
            run('browser', [node, str(ROOT / 'scripts/check_quickstart_browser.mjs'), base, str(output / 'browser')], cwd=ROOT)
        finally:
            stop_owned(process)
    browser = json.loads((output / 'browser/report.json').read_text(encoding='utf-8'))
    if not browser['passed']:
        raise RuntimeError('First-run screen did not pass')
    report = {'passed': True, 'version': version, 'consumer': str(consumer), 'guide': str(guide.relative_to(ROOT)) if guide.is_relative_to(ROOT) else str(guide), 'guide_blocks': list(BLOCKS),
              'guide_sha256': hashlib.sha256(document.encode()).hexdigest(), 'artifact_hashes': artifact_proof,
              'origins': origins, 'offline': offline, 'doctor_passed': doctor['passed'],
              'existing_workspace_unchanged': True, 'browser': browser, 'telegram_requests': False,
              'shell': 'powershell' if WINDOWS else 'bash', 'platform': sys.platform,
              'limits': 'Documented commands for this OS and Chrome viewport preview; installers may use registries; backend initData checked offline only; no real Telegram client, live bot or usability study'}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
