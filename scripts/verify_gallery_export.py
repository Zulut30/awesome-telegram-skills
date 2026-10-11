"""Exercise standalone gallery export, read-only check and installed CLI outside repo."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

if __package__:
    from .verification_process import run_command
else:
    from verification_process import run_command

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--skip-browser', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT): raise ValueError('Consumer must be outside repository')
    output.mkdir(); gallery = output / 'gallery'
    environment = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'BOT_TOKEN'): environment.pop(key, None)
    environment['PYTHONUTF8'] = '1'
    stages = []
    def run(label, command, expected=0, *, timeout=90):
        started = time.monotonic()
        try:
            result = run_command(command, cwd=output, env=environment, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            def partial(value):
                return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
            (output / (label + '.log')).write_text(partial(error.stdout) + partial(error.stderr)
                + f'\nTIMEOUT after {error.timeout} seconds\n', encoding='utf-8', newline='\n')
            stages.append({'stage': label, 'exit_code': 124, 'timed_out': True,
                           'timeout_seconds': timeout, 'elapsed_seconds': round(time.monotonic()-started,3)})
            (output / 'stage-report.json').write_text(json.dumps({'passed': False,'stages': stages},indent=2)+'\n',encoding='utf-8')
            raise
        (output / (label + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8', newline='\n')
        stages.append({'stage': label, 'exit_code': result.returncode, 'expected_exit': expected,
                       'timeout_seconds': timeout, 'elapsed_seconds': round(time.monotonic()-started,3)})
        (output / 'stage-report.json').write_text(json.dumps({'passed': False, 'stages': stages}, indent=2)+'\n', encoding='utf-8')
        if result.returncode != expected: raise RuntimeError(label + ' failed')
        return result.stdout
    builder = ROOT / 'scripts/build_recipe_gallery.py'
    result = json.loads(run('export', [sys.executable, builder, '--output-dir', gallery], timeout=120))
    assert result['recipes'] == 311 and not result['telegram_network']
    marker = gallery / 'owned.txt'; marker.write_bytes(b'preserve consumer notes\n')
    before = {p.relative_to(gallery): hashlib.sha256(p.read_bytes()).hexdigest() for p in gallery.rglob('*') if p.is_file()}
    run('check', [sys.executable, builder, '--output-dir', gallery, '--check'], timeout=120)
    assert before == {p.relative_to(gallery): hashlib.sha256(p.read_bytes()).hexdigest() for p in gallery.rglob('*') if p.is_file()}
    data = json.loads((gallery / 'recipes.json').read_text(encoding='utf-8'))
    links = {name for r in data['recipes'] for name in (*r['source_files'], *r['check_files'])}
    for name in links: assert (gallery / 'files' / name).read_bytes() == (ROOT / name).read_bytes()
    # Readiness/rights are not inferred; search never executes returned fixture code.
    cases = [('rows', ['две кнопки', '--task', 'keyboards', '--context', 'private', '--sdk', 'aiogram', '--sdk-version', '3.31.0'], 'two-columns'),
             ('back', ['назад', '--sdk', 'telegram-webapp'], None),
             ('recovery', ['потерянный ответ', '--task', 'recovery', '--context', 'backend'], 'demo-recovery'),
             ('navigation', ['история', '--task', 'navigation', '--context', 'private', '--sdk', 'aiogram'], 'demo-navigation'),
             ('selection', ['multiselect', '--task', 'input', '--context', 'private', '--sdk', 'aiogram'], 'demo-selection'),
             ('calendar', ['календарь', '--task', 'input', '--context', 'private', '--sdk', 'aiogram'], 'demo-calendar'),
             ('concurrent-actions', ['workers', '--task', 'recovery', '--context', 'private', '--sdk', 'aiogram'], 'demo-concurrent-actions'),
             ('dialog-fields', ['поля', '--task', 'input', '--context', 'private', '--sdk', 'aiogram'], 'demo-dialog-fields'),
             ('profiles', ['локализация', '--task', 'profiles', '--context', 'private', '--sdk', 'aiogram'], 'demo-profiles'),
             ('media', ['скачивание', '--task', 'media', '--context', 'private', '--sdk', 'aiogram'], 'demo-media'),
             ('message-text', ['форматирование', '--task', 'bot', '--context', 'private', '--sdk', 'aiogram'], 'demo-message-text')]
    for label, arguments, expected in cases:
        response = json.loads(run(label, [sys.executable, '-m', 'telegram_patterns', 'recipes', *arguments]))
        assert response['matches'] and response['recipes'][0]['source_files'] and response['recipes'][0]['check_files']
        if expected: assert response['recipes'][0]['id'] == expected
        else: assert all(r['id'].startswith('native.BackButton.') for r in response['recipes'])
    browser = {'passed': False, 'skipped': True, 'checks': 0}
    if not args.skip_browser:
        browser = json.loads(run('browser', [shutil.which('node'), ROOT / 'tests/gallery-browser.mjs', gallery, output / 'browser'], timeout=180))
        assert browser['passed']
    report = {'passed': True, 'version': data['library_version'], 'recipes': len(data['recipes']), 'source_check_files': len(links),
              'byte_exact_copies': True, 'check_read_only': True, 'owned_file_preserved': marker.read_bytes() == b'preserve consumer notes\n',
              'cli_cases': len(cases), 'browser': browser, 'browser_skipped': args.skip_browser, 'stages': stages, 'consumer': str(output),
              'scope': 'Standalone static gallery and installed CLI; no live Telegram, permission or compatibility range proof'}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    (output / 'stage-report.json').write_text(json.dumps({'passed': True, 'stages': stages}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False)); return 0


if __name__ == '__main__':
    if not __debug__: raise SystemExit('Verification needs assertions enabled')
    raise SystemExit(main())
