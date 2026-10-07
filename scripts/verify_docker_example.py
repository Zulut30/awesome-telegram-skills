"""Build the optional service-bot container and run its offline phases through Docker Compose.

The check never reads a real token: it writes a placeholder .env next to compose.yaml
(refusing to touch an existing one), expects the readable placeholder error, runs the
offline start/review phases against the named volume and removes the project afterwards.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/service-bot'
PLACEHOLDER_ERROR = 'error: Replace the BOT_TOKEN placeholder with the token issued by @BotFather'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compose-file', action='append', default=[], type=Path,
                        help='extra Compose override, e.g. build network or proxy CA for a restricted host')
    args = parser.parse_args()
    env_file = EXAMPLE / '.env'
    if env_file.exists():
        parser.error(f'{env_file} already exists; move it away so the check cannot read or overwrite a real token')
    project = f'tg-docker-check-{secrets.token_hex(4)}'
    compose = ['docker', 'compose', '-p', project, '-f', str(EXAMPLE / 'compose.yaml')]
    for extra in args.compose_file:
        compose += ['-f', str(extra.resolve())]

    def run(*argv: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run([*compose, *argv], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
        if result.returncode != expected:
            sys.stderr.write(result.stdout + result.stderr)
            raise SystemExit(f'{" ".join(argv[:3])}: exit {result.returncode}, expected {expected}')
        return result

    report: dict[str, object] = {'project': project}
    env_file.write_text((EXAMPLE / '.env.example').read_text(encoding='utf-8'), encoding='utf-8')
    try:
        run('build')
        error = run('run', '--rm', '-T', 'service-bot', expected=2).stderr
        assert PLACEHOLDER_ERROR in error and 'Traceback' not in error, error
        report['placeholder_error'] = True
        phases = []
        for phase in ('start', 'review'):
            output = run('run', '--rm', '-T', 'service-bot', 'python', '-m', 'telegram_service_example.offline',
                         '--database', '/data/offline.sqlite', '--phase', phase).stdout
            record = json.loads(output)
            assert record['passed'] and record['lock_released'] and not record['telegram_requests'], record
            phases.append({'phase': phase, 'checks': record['checks']})
            if phase == 'start':
                run('down')  # keeps the named volume: the next phase must resume from it
        report['phases'] = phases
        owner = run('run', '--rm', '-T', 'service-bot', 'stat', '-c', '%u', '/data/offline.sqlite').stdout.strip()
        assert owner == '10001', owner
        report['database_owner_uid'] = 10001
    finally:
        env_file.unlink(missing_ok=True)
        subprocess.run([*compose, 'down', '-v', '--rmi', 'local', '--remove-orphans'], cwd=ROOT, capture_output=True)
    report['passed'] = True
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
