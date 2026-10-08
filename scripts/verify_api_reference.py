"""Run exact fenced documentation in installed wheel/tarball consumers outside repo."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import url2pathname

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('wheel', 'tarball', 'core-python', 'sdk-python', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--skip-browser', action='store_true')
    args = parser.parse_args()
    for source in (args.wheel, args.tarball, args.core_python, args.sdk_python): source.resolve(strict=True)
    output = args.output.resolve()
    if output.is_relative_to(ROOT): raise ValueError('Reference consumer must be outside source tree')
    output.mkdir()
    index = json.loads((ROOT / 'catalog/api-reference-index.json').read_text(encoding='utf-8'))
    spec = json.loads((ROOT / 'catalog/api-reference.json').read_text(encoding='utf-8'))
    environment = dict(os.environ)
    for name in ('BOT_TOKEN', 'PYTHONPATH', 'PYTHONHOME', 'NODE_OPTIONS'): environment.pop(name, None)
    environment['PYTHONUTF8'] = '1'
    stages = []
    def run(label, command, *, cwd=output, expected_exit=0):
        done = subprocess.run(list(map(str, command)), cwd=cwd, env=environment, capture_output=True,
                              text=True, encoding='utf-8', timeout=180, shell=False)
        (output / (label + '.log')).write_text(done.stdout + done.stderr, encoding='utf-8', newline='\n')
        stages.append({'stage': label, 'exit_code': done.returncode})
        if done.returncode != expected_exit: raise RuntimeError('Reference consumer failed: ' + label)
        return done.stdout

    definitions = {}
    for section in ('core', 'bot', 'typescript'):
        text = (ROOT / f'docs/api-reference-{section}.md').read_text(encoding='utf-8')
        portable = ROOT / f'.agents/skills/telegram-code-patterns/references/api-reference-{section}.md'
        assert text == portable.read_text(encoding='utf-8')
        for match in re.finditer(r'<a id="ref-([a-z_]+)"></a>.*?```(?:python|typescript)\n(.*?)\n```', text, re.S):
            definitions[match.group(1)] = match.group(2) + '\n'
    py = output / 'python'; py.mkdir()
    ts = output / 'typescript'; ts.mkdir(); (ts / 'src').mkdir()
    for group in spec['groups']:
        content = definitions[group['id']]
        record = next(row for row in index['symbols'] if row['recipe'] == 'ref.' + group['id'])
        assert hashlib.sha256(content.encode('utf-8')).hexdigest() == record['example_sha256']
        assert hashlib.sha256((ROOT / group['example']).read_bytes()).hexdigest() == record['example_source_sha256']
        target = (py if group['section'] != 'typescript' else ts / 'src') / Path(group['example']).name
        target.write_text(content, encoding='utf-8', newline='\n')
    # Copy the shared helpers from their exact first fenced documentation block.
    for section, name, folder in (('bot', 'bot_fixture.py', py), ('typescript', 'check.ts', ts / 'src')):
        text = (ROOT / f'docs/api-reference-{section}.md').read_text(encoding='utf-8')
        first = re.search(r'```(?:python|typescript)\n(.*?)\n```', text, re.S)
        assert first is not None
        (folder / name).write_text(first.group(1) + '\n', encoding='utf-8', newline='\n')
    text = (ROOT / 'docs/api-reference-typescript.md').read_text(encoding='utf-8')
    driver = re.search(r'## Entry — run.ts\n.*?```typescript\n(.*?)\n```', text, re.S)
    assert driver is not None
    (ts / 'src/run.ts').write_text(driver.group(1) + '\n', encoding='utf-8', newline='\n')
    shutil.copyfile(ROOT / 'examples/api-reference/typescript/negative-types.ts', ts / 'src/negative-types.ts')
    installed = []
    for label, python, sdk in [('core', args.core_python, False), ('sdk', args.sdk_python, True)]:
        probe = """import importlib,importlib.metadata as m,importlib.util,json,sys
from pathlib import Path
import telegram_patterns
assert Path(telegram_patterns.__file__).resolve().is_relative_to(Path(sys.prefix))
assert (importlib.util.find_spec('aiogram') is not None)==(sys.argv[1]=='yes')
modules=['telegram_patterns','telegram_patterns.cli']
if sys.argv[1]=='yes':modules+=['telegram_patterns.aiogram','telegram_patterns.testing','telegram_patterns.ptb']
exports={name:(importlib.import_module(name).__all__ if name!='telegram_patterns.cli' else ['doctor']) for name in modules}
print(json.dumps({'version':m.version('awesome-telegram-patterns'),'module':telegram_patterns.__file__,'exports':exports}))
"""
        origin = json.loads(run(label + '-origin', [python, '-c', probe, 'yes' if sdk else 'no']))
        assert origin['version'] == index['library_version']
        if sdk:
            actual = {(module, name) for module, names in origin['exports'].items() for name in names}
            expected = {(r['module'], r['name']) for r in index['symbols'] if not r['module'].startswith('@')}
            assert actual == expected
        installed.append(origin)
    python_cases = []
    for group in spec['groups']:
        if group['section'] == 'typescript': continue
        interpreter = args.core_python if group['section'] == 'core' else args.sdk_python
        command = [interpreter, py / Path(group['example']).name]
        if group['id'] == 'core_starter': command.append(args.wheel.resolve())
        result = json.loads(run(group['id'], command, cwd=py))
        assert result['passed'] and not result['network'] and result['case'] == group['id']
        python_cases.append(result)
    run('example-python-types', [args.sdk_python, '-m', 'mypy', '--follow-imports=silent', '--no-incremental', '--check-untyped-defs', str(py)], cwd=output)
    manifest = {'private': True, 'type': 'module', 'dependencies': {'@awesome-telegram/patterns': 'file:' + args.tarball.resolve().as_posix()}}
    (ts / 'package.json').write_text(json.dumps(manifest), encoding='utf-8')
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm'); node = shutil.which('node')
    run('tarball-install', [npm, 'install', '--ignore-scripts'], cwd=ts)
    tsc = ROOT / 'node_modules/typescript/bin/tsc'
    run('example-typescript-types', [node, tsc, '--strict', '--target', 'ES2022', '--module', 'NodeNext', '--lib', 'ES2022,DOM',
                                    '--outDir', 'dist', '--rootDir', 'src', *sorted((ts / 'src').glob('*.ts'))], cwd=ts)
    audit = json.loads(run('example-import-symbols', [node, ROOT / 'scripts/inspect_api_reference_types.mjs', ts, ROOT / 'catalog/api-reference-index.json']))
    esm = json.loads(run('example-esm', [node, '--input-type=module', '-e',
        "import * as p from '@awesome-telegram/patterns';import{referenceClient}from './dist/client.js';import{referenceDraft}from './dist/draft.js';import{referenceNative}from './dist/native.js';import{referenceErrors}from './dist/errors.js';await referenceClient();referenceDraft();referenceNative();referenceErrors();console.log(JSON.stringify({passed:true,exports:Object.keys(p),css:import.meta.resolve('@awesome-telegram/patterns/styles.css')}));"], cwd=ts))
    assert set(esm['exports']) == {r['name'] for r in index['symbols'] if r['module'].startswith('@') and r['kind'] == 'value'}
    css_url = urlsplit(esm['css'])
    assert css_url.scheme == 'file' and not css_url.netloc
    assert Path(url2pathname(css_url.path)).is_file()
    html = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/node_modules/@awesome-telegram/patterns/dist/styles.css"><h1>Справочник API</h1><p id="status">Проверка примеров</p>
<script type="importmap">{"imports":{"@awesome-telegram/patterns":"/node_modules/@awesome-telegram/patterns/dist/index.js"}}</script>
<script type="module">import{runReference}from '/dist/run.js';const cases=await runReference(document);window.referenceReport={passed:true,cases};document.querySelector('#status').textContent='Примеры прошли: '+cases.join(', ');</script></html>'''
    (ts / 'index.html').write_text(html, encoding='utf-8', newline='\n')
    browser = {'passed': False, 'skipped': True, 'checks': 0}
    if not args.skip_browser:
        browser = json.loads(run('example-browser', [node, ROOT / 'scripts/check_api_reference_browser.mjs', ts, output / 'browser']))
        assert browser['passed'] and browser['checks'] == 36
    cli = json.loads(run('example-cli-recipes', [args.core_python, '-m', 'telegram_patterns', 'recipes', 'две кнопки']))
    assert cli['recipes'][0]['id'] == 'two-columns'
    target = output / 'cli new bot'
    preview = json.loads(run('example-cli-init', [args.core_python, '-m', 'telegram_patterns', 'init', target, '--library', args.wheel.resolve(), '--dry-run']))
    assert not preview['created'] and not target.exists()
    target.mkdir(); (target / 'pyproject.toml').write_text('[project]\nname="fixture"\nversion="0.0.0"\n', encoding='utf-8')
    diagnosis = json.loads(run('example-cli-doctor', [args.core_python, '-m', 'telegram_patterns', 'doctor', target], expected_exit=1))
    assert not diagnosis['passed'] and not diagnosis['suggestions_executed']
    assert any(item.get('name') == 'aiogram' and item.get('reason') == 'sdk-missing' for item in diagnosis['checks'])
    report = {'passed': True, 'version': index['library_version'], 'symbols': len(index['symbols']),
              'python_symbols': index['python_symbols'], 'typescript_symbols': index['typescript_symbols'],
              'python_cases': python_cases, 'typescript_audit': audit, 'runtime_typescript_exports': len(esm['exports']),
              'browser': browser, 'installed_origins': installed, 'cli_recipes': True, 'cli_init_dry_run': True,
              'cli_doctor': True, 'browser_skipped': args.skip_browser,
              'stages': stages, 'consumer': str(output), 'scope': 'Exact fenced doc code; installed package/type/ESM/DOM evidence, no physical Telegram/live provider/blind agent proof'}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, ensure_ascii=False)); return 0


if __name__ == '__main__':
    if not __debug__: raise SystemExit('Reference verification needs assertions enabled')
    raise SystemExit(main())
