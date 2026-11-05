"""Install a trusted local tarball and check the UI example in an isolated Chrome consumer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _environment import minimal_environment, planted_link

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tarball', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--node', default=shutil.which('node'))
    parser.add_argument('--npm', default=shutil.which('npm.cmd' if os.name == 'nt' else 'npm'))
    args = parser.parse_args()
    for path in (args.output, *args.output.parents):
        if planted_link(path):
            raise ValueError('Output links are not supported')
    artifact = args.tarball.resolve(strict=True)
    if not artifact.is_file() or artifact.suffix != '.tgz':
        raise ValueError('Provide a trusted local tarball')
    if not args.node or not args.npm:
        raise ValueError('Node and npm are required')
    output = args.output.resolve()
    output.mkdir(parents=True)  # Existing output is preserved; the leaf must be new.
    consumer = Path(tempfile.mkdtemp(prefix='telegram UI consumer ')).resolve()
    if consumer.is_relative_to(ROOT):
        raise ValueError('UI consumer must be outside the source checkout')
    environment = minimal_environment()
    environment['PYTHONUTF8'] = '1'
    if 'CHROME_PATH' not in environment:
        chrome = Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe'
        if chrome.is_file():
            environment['CHROME_PATH'] = str(chrome)
    stages: list[dict[str, object]] = []
    artifact_record = {'name': artifact.name, 'bytes': artifact.stat().st_size,
                       'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}

    def run(label: str, argv: list[object], *, timeout: int = 180) -> str:
        completed = subprocess.run(list(map(str, argv)), cwd=consumer, env=environment,
                                   capture_output=True, text=True, encoding='utf-8', timeout=timeout, check=False)
        (output / (label + '.log')).write_text(completed.stdout + completed.stderr,
                                             encoding='utf-8', newline='\n')
        stages.append({'stage': label, 'exit_code': completed.returncode})
        if completed.returncode:
            raise RuntimeError(label + ' failed; inspect saved log')
        return completed.stdout

    try:
        expected = json.loads((ROOT / 'packages/typescript/package.json').read_text(encoding='utf-8'))
        quality = json.loads((ROOT / 'tools/mini-app-quality/package.json').read_text(encoding='utf-8'))
        source_names = ('examples/ui-kit/main.ts', 'examples/ui-kit/screens.ts',
                        'examples/ui-kit/index.html', 'examples/api-reference/typescript/ui.ts',
                        'examples/api-reference/typescript/check.ts',
                        'packages/typescript/tests/types/ui.ts', 'packages/typescript/tests/ui.test.mjs',
                        'examples/ui-kit/server.mjs', 'packages/typescript/tests/ui-browser.mjs',
                        'scripts/verify_ui_example.py')
        source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_names}
        supplied = consumer / 'provided artifact.tgz'
        shutil.copyfile(artifact, supplied)
        package = {'private': True, 'type': 'module',
                   'dependencies': {'@awesome-telegram/patterns': 'file:' + supplied.as_posix()},
                   'devDependencies': {'typescript': expected['devDependencies']['typescript'],
                                       'axe-core': quality['devDependencies']['axe-core']}}
        (consumer / 'package.json').write_text(json.dumps(package, indent=2) + '\n', encoding='utf-8')
        run('install', [args.npm, 'install', '--ignore-scripts', '--no-audit', '--no-fund'])
        probe = """import fs from 'node:fs';import path from 'node:path';import{fileURLToPath}from 'node:url';
const resolve=name=>fs.realpathSync(fileURLToPath(import.meta.resolve(name)));
const metadata=JSON.parse(fs.readFileSync(resolve('@awesome-telegram/patterns/package.json'),'utf8'));
console.log(JSON.stringify({version:metadata.version,index:resolve('@awesome-telegram/patterns'),
styles:resolve('@awesome-telegram/patterns/styles.css'),tokens:resolve('@awesome-telegram/patterns/tokens.css'),
typescript:JSON.parse(fs.readFileSync('node_modules/typescript/package.json','utf8')).version,
axe:JSON.parse(fs.readFileSync('node_modules/axe-core/package.json','utf8')).version}));"""
        origin = json.loads(run('public-origin', [args.node, '--input-type=module', '-e', probe]))
        assert origin['version'] == expected['version']
        assert origin['typescript'] == package['devDependencies']['typescript']
        assert origin['axe'] == package['devDependencies']['axe-core']
        installed = (consumer / 'node_modules/@awesome-telegram/patterns').resolve(strict=True)
        assert installed.is_relative_to(consumer)
        public_assets = {}
        with tarfile.open(supplied, 'r:gz') as archive:
            for name in ('index', 'styles', 'tokens'):
                path = Path(origin[name]).resolve(strict=True)
                assert path.is_relative_to(installed / 'dist')
                member = archive.extractfile('package/' + path.relative_to(installed).as_posix())
                assert member is not None and member.read() == path.read_bytes()
                public_assets[name] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        source = consumer / 'src'
        for folder in ('example', 'reference'):
            (source / folder).mkdir(parents=True)
        for name in ('main.ts', 'screens.ts'):
            shutil.copyfile(ROOT / 'examples/ui-kit' / name, source / 'example' / name)
        for name in ('ui.ts', 'check.ts'):
            shutil.copyfile(ROOT / 'examples/api-reference/typescript' / name, source / 'reference' / name)
        shutil.copyfile(ROOT / 'examples/ui-kit/index.html', consumer / 'index.html')
        types = (ROOT / 'packages/typescript/tests/types/ui.ts').read_text(encoding='utf-8')
        assert types.count("from '../../dist/index.js'") == 1
        (source / 'ui-types.ts').write_text(types.replace("from '../../dist/index.js'", "from '@awesome-telegram/patterns'"),
                                          encoding='utf-8', newline='\n')
        tests = (ROOT / 'packages/typescript/tests/ui.test.mjs').read_text(encoding='utf-8')
        assert tests.count("from '../dist/index.js'") == 1
        (consumer / 'ui.test.mjs').write_text(tests.replace("from '../dist/index.js'", "from '@awesome-telegram/patterns'"),
                                            encoding='utf-8', newline='\n')
        config = {'compilerOptions': {'target': 'ES2022', 'module': 'NodeNext', 'moduleResolution': 'NodeNext',
                                     'lib': ['ES2022', 'DOM'], 'strict': True, 'exactOptionalPropertyTypes': True,
                                     'noUncheckedIndexedAccess': True, 'noEmitOnError': True,
                                     'rootDir': 'src', 'outDir': 'dist', 'types': []}, 'include': ['src/**/*.ts']}
        (consumer / 'tsconfig.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
        run('strict-types-and-build', [args.node, consumer / 'node_modules/typescript/bin/tsc', '-p', 'tsconfig.json'])
        run('navigation-tests', [args.node, '--test', 'ui.test.mjs'])
        browser_configuration = {'mode': 'installed', 'vendorDirectory': str(Path(origin['index']).parent),
                                 'exampleDirectory': str(consumer / 'dist/example'),
                                 'referenceDirectory': str(consumer / 'dist/reference'),
                                 'htmlPath': str(consumer / 'index.html'),
                                 'axeDirectory': str(consumer / 'node_modules/axe-core'),
                                 'output': str(output / 'browser')}
        browser_config = consumer / 'browser-config.json'
        browser_config.write_text(json.dumps(browser_configuration, indent=2) + '\n', encoding='utf-8')
        run('browser', [args.node, ROOT / 'packages/typescript/tests/ui-browser.mjs', browser_config], timeout=480)
        browser = json.loads((output / 'browser/report.json').read_text(encoding='utf-8'))
        assert browser['passed'] and browser['mode'] == 'installed' and browser['externalRequests'] == []
        assert len(browser['checks']) == 35 and len(browser['geometry']) == 96 and len(browser['audits']) == 24
        assert all(not audit['violations'] for audit in browser['audits'])
        assert Path(browser['served']['vendor']).resolve() == Path(origin['index']).parent
        assert all(Path(browser['served'][name]).resolve().is_relative_to(consumer)
                   for name in ('vendor', 'example', 'reference', 'html'))
        assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                   for name, digest in source_hashes.items()), 'UI source changed during consumer verification'
        report = {'passed': True, 'library_version': origin['version'], 'consumer': str(consumer),
                  'artifact': artifact_record, 'public_assets': public_assets, 'tools': origin,
                  'source_sha256': source_hashes, 'stages': stages, 'browser': browser,
                  'scope': 'Installed tarball, strict public API types, six copied UI compositions and public UI fixture. '
                           'Synthetic Chrome/axe geometry, focus and state evidence; no physical devices, native '
                           'keyboards, screen readers, approved visual baselines or live Telegram/payment proof.'}
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                                          encoding='utf-8', newline='\n')
        print(json.dumps({'passed': True, 'library_version': origin['version'], 'checks': 35,
                          'geometry': 96, 'axe_states': 24, 'artifact': artifact_record,
                          'report': str(output / 'report.json')}))
        return 0
    except Exception as error:
        (output / 'report.json').write_text(json.dumps({'passed': False, 'consumer': str(consumer),
                                                       'artifact': artifact_record, 'stages': stages,
                                                       'error': str(error)}, ensure_ascii=False, indent=2) + '\n',
                                          encoding='utf-8', newline='\n')
        raise


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('UI verification needs assertions enabled')
    raise SystemExit(main())
