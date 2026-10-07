"""Exercise the installed CLI and bundled starters using the built wheel/tarball."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--tarball', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir()  # Must be a new directory, even in the verification helper.
    environment = dict(os.environ)
    environment.pop('BOT_TOKEN', None)
    environment['PYTHONUTF8'] = '1'
    results = []
    cli_stages = []
    console = Path(sys.executable).parent / ('telegram-patterns.exe' if os.name == 'nt' else 'telegram-patterns')
    if not console.is_file(): raise RuntimeError('Installed console entrypoint missing')

    def cli(*arguments: str, expected: int = 0) -> dict:
        completed = subprocess.run([str(console), *map(str, arguments), '--json'], env=environment,
                                   capture_output=True, text=True, encoding='utf-8', timeout=60)
        stage = {'action': arguments[0], 'exit_code': completed.returncode, 'expected_exit': expected}
        cli_stages.append(stage)
        (args.output / f'cli-{len(cli_stages):02d}-{arguments[0]}.log').write_text(
            completed.stdout + completed.stderr, encoding='utf-8')
        if completed.returncode != expected:
            raise RuntimeError(f'Installed CLI {arguments[0]} returned {completed.returncode}; '
                               f'expected {expected}; inspect {args.output / ("cli-%02d-%s.log" % (len(cli_stages), arguments[0]))}')
        return json.loads(completed.stdout if expected != 2 else completed.stderr)

    found = cli('recipes', 'две кнопки')
    assert found['recipes'][0]['id'] == 'two-columns'
    for template in ('bot', 'bot-mini-app'):
        target = args.output / template
        command = ['init', str(target), '--library', str(args.wheel), '--template', template]
        if template == 'bot-mini-app': command += ['--typescript', str(args.tarball)]
        dry = cli(*command, '--dry-run')
        assert not dry['created'] and not target.exists()
        created = cli(*command)
        assert created['created'] and not created['network']
        files = {str(path.relative_to(target)).replace('\\', '/'): path.read_bytes()
                 for path in target.rglob('*') if path.is_file()}
        assert len(files) == (7 if template == 'bot' else 11)
        cli(*command, expected=2)
        assert files == {str(path.relative_to(target)).replace('\\', '/'): path.read_bytes()
                         for path in target.rglob('*') if path.is_file()}
        project = tomllib.loads((target / 'pyproject.toml').read_text(encoding='utf-8'))
        assert project['project']['dependencies'] == ['awesome-telegram-patterns[aiogram] @ ' + args.wheel.resolve().as_uri()]
        manifest = json.loads((target / '.telegram-patterns.json').read_text(encoding='utf-8'))
        assert manifest['library_version'] == created['library_version']
        offline = subprocess.run([sys.executable, 'offline.py'], cwd=target, env=environment,
                                 capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert offline.returncode == 0, 'Generated starter offline scenario failed'
        proof = json.loads(offline.stdout)
        assert proof['passed'] and not proof['network']
        diagnostics = cli('doctor', str(target))
        assert diagnostics['passed'] and not diagnostics['network']
        assert cli('doctor', str(target), '--require-token', expected=1)['passed'] is False
        if template == 'bot-mini-app':
            mini = json.loads((target / 'mini-app/package.json').read_text(encoding='utf-8'))
            assert mini['dependencies']['@awesome-telegram/patterns'] == 'file:' + args.tarball.resolve().as_posix()
        results.append({'template': template, 'files': len(files), 'offline': proof, 'doctor': diagnostics})
    report = {'passed': True, 'network': False, 'installed_console': True, 'starters': results, 'cli_stages': cli_stages}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 0


if __name__ == '__main__': raise SystemExit(main())
