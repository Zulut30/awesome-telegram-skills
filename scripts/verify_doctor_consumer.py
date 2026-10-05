"""Execute installed doctor reports and selected repair commands in new consumers.

Run with the SDK-free installed wheel interpreter. Diagnosis is read only;
this explicit verifier separately installs supplied packages into owned fixtures.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from telegram_patterns.cli import doctor

CANARY = '100:DOCTOR_FIXTURE_PRIVATE'
TRACE_DOCTOR = '''import json,sys,time
from pathlib import Path
from telegram_patterns.cli import main
from telegram_patterns import diagnostics
original=diagnostics.subprocess.run
calls=[]
def traced(*args,**kwargs):
    started=time.monotonic()
    probe='sdk' if '-I' in args[0] else 'node'
    try:
        result=original(*args,**kwargs)
        calls.append({'probe':probe,'seconds':round(time.monotonic()-started,3),'exit_code':result.returncode,
                      'ready':result.stdout.strip()=='ready','stderr_present':bool(result.stderr)})
        return result
    except Exception as error:
        calls.append({'probe':probe,'seconds':round(time.monotonic()-started,3),'exception':type(error).__name__})
        raise
diagnostics.subprocess.run=traced
try:
    status=main(sys.argv[2:])
finally:
    Path(sys.argv[1]).write_text(json.dumps(calls,indent=2)+'\\n',encoding='utf-8')
raise SystemExit(status)
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--tarball', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True); tarball = args.tarball.resolve(strict=True)
    assert importlib.util.find_spec('aiogram') is None
    assert Path(sys.modules[doctor.__module__].__file__).resolve().is_relative_to(Path(sys.prefix))
    args.output.mkdir()
    project = args.output / 'project with spaces'; project.mkdir()
    mini = project / 'mini-app'; mini.mkdir()
    (project / 'pyproject.toml').write_text('[project]\nname="doctor-fixture"\n', encoding='utf-8')
    (mini / 'package.json').write_text('{"private":true,"type":"module","dependencies":{}}', encoding='utf-8')
    (project / '.env').write_text('BOT_TOKEN=' + CANARY, encoding='utf-8')
    (project / 'app.py').write_text('raise RuntimeError("' + CANARY + '")', encoding='utf-8')
    environment = dict(os.environ)
    for name in ('BOT_TOKEN', 'PYTHONPATH', 'PYTHONHOME', 'NODE_OPTIONS'): environment.pop(name, None)
    environment['PYTHONUTF8'] = '1'
    cases = []

    def snapshot():
        return {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in project.rglob('*') if p.is_file()}

    def run(label, command, *, cwd=project, env=None, expected=0):
        done = subprocess.run(command, cwd=cwd, env=environment if env is None else env,
                              capture_output=True, text=True, encoding='utf-8', timeout=120, shell=False)
        if expected is not None and done.returncode != expected:
            raise RuntimeError('Doctor consumer operation failed: ' + label)
        return done

    def diagnostic(label, *, python=sys.executable, target='.', required=False, env=None, expected=1):
        before = snapshot()
        # Observe actual fixed tool calls without recording argv, env, output or exception payloads.
        command = [str(python), '-c', TRACE_DOCTOR, str((args.output / (label + '-timing.json')).resolve()), 'doctor', str(target)]
        if required: command.append('--require-token')
        done = run(label, command, env=env, expected=None)
        assert not done.stderr and CANARY not in done.stdout and 'DOCTOR_FIXTURE_PRIVATE' not in done.stdout
        report = json.loads(done.stdout)
        summary = {'case': label, 'exit_code': done.returncode, 'expected_exit': expected, 'checks': [
            {'name': c['name'], 'status': c['status'], 'reason': c['reason']} for c in report['checks']]}
        summary['tool_timing'] = json.loads((args.output / (label + '-timing.json')).read_text(encoding='utf-8'))
        (args.output / (label + '.json')).write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        if done.returncode != expected:
            failed = [c['reason'] for c in report['checks'] if c['status'] == 'fail']
            raise RuntimeError(f'Doctor consumer {label} returned {done.returncode}; expected {expected}; reasons: {failed}')
        assert not report['network'] and not report['suggestions_executed']
        assert before == snapshot()
        for check in report['checks']:
            assert check['reason'] and 'remediation' in check
            if check['status'] != 'pass':
                assert check['remediation']['summary'] and check['remediation']['commands']
        cases.append(summary)
        return report

    def named(report, name): return next(c for c in report['checks'] if c['name'] == name)

    missing = diagnostic('sdk-free-and-missing-dependency')
    assert named(missing, 'aiogram')['reason'] == 'sdk-missing'
    assert named(missing, 'token-format')['reason'] == 'token-missing'
    assert named(missing, 'mini-app-manifest')['reason'] == 'mini-app-dependency-missing'
    diagnostic('unavailable-target', target=project / 'DOCTOR_FIXTURE_PRIVATE')
    required = diagnostic('required-token', required=True)
    assert named(required, 'token-format')['status'] == 'fail'
    invalid_env = dict(environment, BOT_TOKEN='DOCTOR_FIXTURE_PRIVATE')
    invalid = diagnostic('invalid-token', env=invalid_env)
    assert named(invalid, 'token-format')['reason'] == 'token-format-invalid'
    (mini / 'package.json').write_text('{"dependencies":null}', encoding='utf-8')
    shape = diagnostic('wrong-dependency-shape')
    assert named(shape, 'mini-app-manifest')['reason'] == 'mini-app-dependency-missing'
    (mini / 'package.json').write_text('{"private":true,"type":"module","dependencies":{}}', encoding='utf-8')

    repair = args.output / 'repair environment with spaces'
    run('new-repair-venv', [sys.executable, '-m', 'venv', '--without-pip', str(repair)], cwd=args.output)
    python = repair / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    constraint = args.output / 'checked-sdk.txt'; constraint.write_text('aiogram==3.31.0\n', encoding='utf-8')
    install_env = dict(environment, PIP_CONSTRAINT=str(constraint.resolve()), PIP_DISABLE_PIP_VERSION_CHECK='1')
    repairs_executed = []
    for item in named(missing, 'aiogram')['remediation']['commands']:
        command = [str(python) if part == 'python' else str(wheel) + '[aiogram]' if part == '<PROVIDED_WHEEL>[aiogram]' else part
                   for part in item['argv']]
        run('repair-sdk', command, env=install_env)
        repairs_executed.append({'argv_template': item['argv'], 'cwd': item['cwd']})
    origin = json.loads(run('repaired-origin', [str(python), '-c',
        "import sys,json,telegram_patterns,importlib.metadata as m; print(json.dumps({'module':telegram_patterns.__file__,'prefix':sys.prefix,'aiogram':m.version('aiogram')}))"]).stdout)
    assert Path(origin['module']).resolve().is_relative_to(repair.resolve()) and origin['aiogram'] == '3.31.0'
    # Execute exactly the suggested tarball install, with only its placeholder replaced.
    item = named(missing, 'mini-app-manifest')['remediation']['commands'][0]
    command = [str(tarball) if part == '<PROVIDED_TARBALL>' else part for part in item['argv']]
    run('repair-typescript', command, cwd=mini)
    repairs_executed.append({'argv_template': item['argv'], 'cwd': item['cwd']})
    good_env = dict(environment, BOT_TOKEN=CANARY)
    good = diagnostic('repaired-sdk-and-mini-app', python=python, env=good_env, required=True, expected=0)
    assert good['passed'] and named(good, 'aiogram')['detail'] == '3.31.0'
    fixture = "from pathlib import Path\nPath(__file__).with_name('unexpected-write.txt').write_text('fixture')\nraise ImportError('DOCTOR_FIXTURE_PRIVATE')\n"
    shadow = project / 'aiogram.py'; shadow.write_text(fixture, encoding='utf-8')
    rejected = diagnostic('project-sdk-shadow-not-executed', python=python, env=good_env)
    assert named(rejected, 'python-exports')['reason'] == 'adapter-origin-unverified'
    assert not (project / 'unexpected-write.txt').exists()
    shadow.unlink()
    shadow = project / 'aiohttp.py'; shadow.write_text(fixture, encoding='utf-8')
    isolated = diagnostic('project-dependency-shadow-not-executed', python=python, env=good_env, expected=0)
    assert named(isolated, 'python-exports')['reason'] == 'adapter-ready'
    assert not (project / 'unexpected-write.txt').exists()
    shadow.unlink()
    (project / 'pyproject.toml').write_text('DOCTOR_FIXTURE_PRIVATE', encoding='utf-8')
    invalid = diagnostic('invalid-toml', python=python, env=good_env)
    check = named(invalid, 'pyproject'); assert check['reason'] == 'toml-invalid'
    (project / 'pyproject.toml').write_text('[project]\nname="doctor-fixture"\n', encoding='utf-8')
    suggestion = check['remediation']['commands'][0]
    assert suggestion['argv'] == ['python', '-m', 'telegram_patterns', 'doctor', '.']
    diagnostic('rerun-after-manual-toml-fix', python=python, env=good_env, expected=0)
    repairs_executed.append({'argv_template': suggestion['argv'], 'cwd': suggestion['cwd']})
    missing_tools = diagnostic('missing-node-and-npm', python=python, env=dict(good_env, PATH=''))
    assert named(missing_tools, 'node')['reason'] == 'node-missing'
    assert named(missing_tools, 'npm')['reason'] == 'npm-missing'
    assert missing_tools['tool_probes_attempted'] == ['python -I -B adapter imports']
    diagnostic('restored-tool-path', python=python, env=good_env, expected=0)
    report = {'passed': True, 'doctor_network': False, 'doctor_writes': False,
              'cases': cases, 'repairs_executed': repairs_executed, 'installed_origin': origin,
              'scope': 'Installed wheel, fresh SDK-free and repaired consumer, real supplied wheel/tarball installs; no Telegram requests or physical client proof',
              'sdk_project_shadow_rejected': True, 'dependency_shadow_not_executed': True,
              'installer_network': 'Explicit fixture repair installers may use registries; doctor never invokes them'}
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    if not __debug__: raise SystemExit('Doctor verification needs assertions enabled')
    raise SystemExit(main())
