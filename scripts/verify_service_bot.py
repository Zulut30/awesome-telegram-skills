"""Build/install the service example and prove actual process restart on SQLite."""
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
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared helpers live next to this script
from _environment import minimal_environment  # noqa: E402

ROOT=Path(__file__).resolve().parents[1]


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel',type=Path,required=True,help='Previously accepted local pattern wheel')
    parser.add_argument('--output',type=Path,required=True,help='New evidence directory')
    args=parser.parse_args()
    for p in (args.output,*args.output.parents):
        if p.is_symlink() or bool(getattr(p,'is_junction',lambda:False)()):raise ValueError('Output links are not supported')
    wheel=args.wheel.resolve(strict=True)
    if not wheel.is_file() or wheel.suffix!='.whl':raise ValueError('Provide the trusted local pattern wheel')
    output=args.output.resolve();output.mkdir(parents=True)  # parent links were refused above; the leaf must be new
    project=Path(tempfile.mkdtemp(prefix='telegram service consumer '))
    env=minimal_environment()
    env['PYTHONUTF8']='1'
    stages=[]
    def run(label,argv,*,expected=0,cwd=project,environment=env):
        p=subprocess.run(list(map(str,argv)),cwd=cwd,env=environment,capture_output=True,text=True,encoding='utf-8',timeout=180)
        assert 'PRIVATE_CANARY' not in p.stdout+p.stderr
        (output/(label+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        stages.append({'stage':label,'exit_code':p.returncode,'expected_exit':expected})
        if p.returncode!=expected:raise RuntimeError(label+' failed; inspect saved log')
        return p.stdout
    artifacts=output/'dist';artifacts.mkdir()
    uv=shutil.which('uv');assert uv
    run('build-example',[uv,'build','--wheel','--out-dir',artifacts,ROOT/'examples/service-bot'])
    example=artifacts/'awesome_telegram_service_example-0.1.0-py3-none-any.whl'
    package=ROOT/'examples/service-bot/src'
    expected={p.relative_to(package).as_posix():p.read_bytes() for p in package.rglob('*') if p.is_file() and p.suffix in {'.py','.typed'}}
    with zipfile.ZipFile(example) as archive:
        actual={n for n in archive.namelist() if n.startswith('telegram_service_example/')}
        assert actual==set(expected) and all(archive.read(n)==data for n,data in expected.items())
    venv=project/'environment';run('environment',[uv,'venv','--python',sys.executable,venv])
    python=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    run('install',[uv,'pip','install','--python',python,str(wheel)+'[aiogram]',example,'aiogram==3.31.0','mypy==2.4.0'])
    origin=json.loads(run('origin',[python,'-I','-c',"import sys,json,telegram_patterns,telegram_service_example,importlib.metadata as m;print(json.dumps({'prefix':sys.prefix,'library':telegram_patterns.__file__,'example':telegram_service_example.__file__,'library_version':m.version('awesome-telegram-patterns'),'aiogram':m.version('aiogram')}))"]))
    assert all(Path(origin[k]).is_relative_to(Path(origin['prefix'])) for k in ('library','example'))
    run('typecheck',[python,'-m','mypy','--check-untyped-defs','--warn-unused-ignores',ROOT/'examples/service-bot/src'])
    run('tests',[python,'-I','-m','unittest','discover','-s',ROOT/'examples/service-bot/tests','-v'])
    test_log=(output/'tests.log').read_text(encoding='utf-8')
    unit_tests=int(re.search(r'Ran (\d+) tests',test_log).group(1));assert unit_tests==8 and test_log.rstrip().endswith('OK')
    caller=project/'caller project';caller.mkdir()
    (caller/'aiogram.py').write_text("raise RuntimeError('PRIVATE_CANARY')",encoding='utf-8')
    (caller/'.env').write_text('BOT_TOKEN=100:PRIVATE_CANARY',encoding='utf-8')
    (caller/'owned.txt').write_bytes(b'preserve caller notes')
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in caller.iterdir()}
    isolated=dict(env,BOT_TOKEN='100:PRIVATE_CANARY',PAYMENT_SECRET='PRIVATE_CANARY',PYTHONPATH=str(caller))
    database=project/'service.sqlite';phases=[]
    def phase(name,path=database,expected=0,label=None):
        result=run(label or name,[python,'-I','-B','-m','telegram_service_example.offline','--database',path,'--phase',name],expected=expected,cwd=caller,environment=isolated)
        assert 'PRIVATE_CANARY' not in result
        record=json.loads(result)
        assert record['phase']==name and record['telegram_requests'] is False and record['external_network_attempts']==0
        if expected==0:assert record['passed'] and record['checks'] and record['session_closed'] and record['fsm_closed'] and record['lock_released']
        elif expected==73:assert record['committed'] and record['booking_id']==1 and record['ack_before_commit']
        elif expected==74:assert record['stub_transport_effect'] and record['message_id']>0
        phases.append(record);return record
    phase('start');phase('review');phase('crash-submit',expected=73);phase('recover')
    ambiguous=project/'ambiguous.sqlite';shutil.copyfile(database,ambiguous)
    phase('reminder');phase('crash-reminder',ambiguous,expected=74);phase('recover-reminder',ambiguous)
    # A second process cannot own the database until the OS releases its lock.
    locktest="""import json,subprocess,sys
from pathlib import Path
from telegram_service_example.storage import ProcessLock

p=Path(sys.argv[1]);lock=ProcessLock(p)
code="from telegram_service_example.storage import ProcessLock;from pathlib import Path;import sys;ProcessLock(Path(sys.argv[1]))"
child=subprocess.run([sys.executable,'-I','-c',code,str(p)],capture_output=True,text=True)
assert child.returncode!=0 and 'Another service process' in child.stderr
lock.close();next_lock=ProcessLock(p);next_lock.close()
print(json.dumps({'passed':True,'second_process_refused':True,'released_reacquired':True}))
"""
    lock=json.loads(run('process-lock',[python,'-I','-c',locktest,database]))
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in caller.iterdir()}
    report={'passed':True,'roadmap_item':17,'library_version':origin['library_version'],'installed_origins':origin,
            'consumer':str(project),'phases':phases,'process_lock':lock,'stages':stages,'unit_tests':unit_tests,'archive_source_exact_files':len(expected),
            'caller_files_preserved':True,'telegram_requests':False,'external_network_attempts':0,
            'artifacts':[{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in (wheel,example)],
            'scope':'Installed application and accepted library wheel, real SQLite and distinct crash/restart processes, synthetic SDK Dispatcher/transport. No live Telegram, physical device, multiworker or payment acceptance.'}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report));return 0


if __name__=='__main__':
    if not __debug__:raise SystemExit('Verification needs assertions enabled')
    raise SystemExit(main())
