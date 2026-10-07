"""From a wheel to a running offline bot in clean environments: the path a new user takes on any OS.

    python scripts/verify_fresh_install.py --wheel dist/awesome_telegram_patterns-X.Y.Z-py3-none-any.whl --output DIR

1. A new virtual environment gets only the wheel; the `telegram-patterns` console command must exist there.
2. `telegram-patterns --version` and `telegram-patterns init <project> --template bot` run from that command.
3. The generated project gets its own new environment (`pip install .` pulls aiogram from the wheel's extra),
   `offline.py` answers /start and a button through StubSession, and `doctor` passes without a token.
No token, network to Telegram or Node.js is used; pip may use the package index for aiogram.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

WINDOWS = os.name == 'nt'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new directory for logs and the report')
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    workspace = Path(tempfile.mkdtemp(prefix='fresh install ')).resolve()  # a space in the path on purpose
    try:
        return verify(wheel, output, workspace)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def verify(wheel: Path, output: Path, workspace: Path) -> int:
    environment = {key: value for key, value in os.environ.items() if key not in {'BOT_TOKEN', 'PYTHONPATH', 'PYTHONHOME'}}
    environment['PYTHONUTF8'] = '1'
    steps: list[dict] = []

    def run(name: str, argv: list[str | Path], cwd: Path) -> str:
        done = subprocess.run([str(item) for item in argv], cwd=cwd, env=environment, capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=600, check=False)
        (output / f'{name}.log').write_text(done.stdout + done.stderr, encoding='utf-8')
        steps.append({'step': name, 'exit_code': done.returncode})
        if done.returncode:
            sys.stderr.write(f'--- {name} failed ---\n' + '\n'.join((done.stdout + done.stderr).splitlines()[-40:]) + '\n')
            raise SystemExit(1)
        return done.stdout

    def environment_in(folder: Path) -> tuple[Path, Path]:
        venv.EnvBuilder(with_pip=True).create(folder)
        scripts = folder / ('Scripts' if WINDOWS else 'bin')
        return scripts / ('python.exe' if WINDOWS else 'python'), scripts

    tools_python, tools_scripts = environment_in(workspace / 'tools')
    run('install-wheel', [tools_python, '-m', 'pip', 'install', '--disable-pip-version-check', wheel], workspace)
    console = tools_scripts / ('telegram-patterns.exe' if WINDOWS else 'telegram-patterns')
    if not console.is_file():
        sys.stderr.write('The wheel did not install the telegram-patterns console command\n')
        return 1
    version = run('version', [console, '--version'], workspace).strip()
    project = workspace / 'my bot'
    created = json.loads(run('init', [console, 'init', project, '--library', wheel, '--template', 'bot', '--json'], workspace))
    if not created['created'] or created['network']:
        sys.stderr.write('init did not create the project offline\n')
        return 1
    bot_python, _ = environment_in(project / '.venv')
    run('install-project', [bot_python, '-m', 'pip', 'install', '--disable-pip-version-check', '.'], project)
    offline = json.loads(run('offline', [bot_python, 'offline.py'], project))
    expected = ['SendMessage', 'AnswerCallbackQuery', 'SendMessage']
    if not offline['passed'] or offline['network'] or offline['methods'] != expected or not offline['session_closed']:
        sys.stderr.write(f'offline.py differs from the documented result: {offline}\n')
        return 1
    doctor = json.loads(run('doctor', [bot_python, '-m', 'telegram_patterns', 'doctor', '.', '--json'], project))
    if not doctor['passed'] or doctor['network']:
        sys.stderr.write('doctor did not pass without a token\n')
        return 1
    report = {'passed': True, 'platform': sys.platform, 'python': sys.version.split()[0], 'console_version': version,
              'template': 'bot', 'files': len(created['files']), 'offline': offline, 'doctor_passed': True, 'steps': steps,
              'limits': 'Clean virtual environments from one wheel; aiogram comes from the package index; no Telegram token or network'}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
