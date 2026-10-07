"""Verify installed prerequisite plans, all Python fixtures, isolation and guards."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('core-python','sdk-python','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();args.output.mkdir()
    project=args.output/'caller project';project.mkdir()
    (project/'aiogram.py').write_text("from pathlib import Path\nPath('unexpected.txt').write_text('PRIVATE_CANARY')\nraise RuntimeError('PRIVATE_CANARY')\n",encoding='utf-8')
    (project/'.env').write_text('BOT_TOKEN=100:PRIVATE_CANARY',encoding='utf-8')
    environment=dict(os.environ,BOT_TOKEN='100:PRIVATE_CANARY',PAYMENT_SECRET='PRIVATE_CANARY',PYTHONPATH=str(project))
    environment['PYTHONUTF8']='1'
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in project.iterdir()}
    stages=[]
    def run(label,python,arguments,*,expected=0,cwd=project):
        done=subprocess.run([str(python),'-I','-B',*map(str,arguments)],cwd=cwd,env=environment,
                            capture_output=True,text=True,encoding='utf-8',timeout=120)
        assert 'PRIVATE_CANARY' not in done.stdout+done.stderr
        (args.output/(label+'.log')).write_text(done.stdout+done.stderr,encoding='utf-8')
        stages.append({'stage':label,'exit_code':done.returncode,'expected_exit':expected})
        if done.returncode!=expected:raise RuntimeError(label+' failed:\n'+'\n'.join((done.stdout+done.stderr).splitlines()[-40:]))
        return done
    origin_code="import json,sys,telegram_patterns,importlib.metadata as m;print(json.dumps({'module':telegram_patterns.__file__,'prefix':sys.prefix,'version':m.version('awesome-telegram-patterns')}))"
    origins=[]
    for label,python in [('core',args.core_python),('sdk',args.sdk_python)]:
        origin=json.loads(run(label+'-origin',python,['-c',origin_code]).stdout)
        assert Path(origin['module']).resolve().is_relative_to(Path(origin['prefix']).resolve())
        origins.append(origin)
    plan=json.loads(run('core-plan',args.core_python,['-m','telegram_patterns','run-recipe','demo-recovery']).stdout)
    assert plan['stage']=='plan' and plan['offline_ready'] and not plan['offline_environment'] and not plan['offline_permissions']
    core=run('core-run',args.core_python,['-m','telegram_patterns','run-recipe','demo-recovery','--offline'])
    records=[json.loads(x) for x in core.stdout.splitlines()]
    assert [r['stage'] for r in records]==['plan','result'] and records[-1]['checks']==['sqlite-one-effect','same-key-replay']
    for label,recipe in [('missing-sdk','two-columns'),('native-reference','native.requestContact')]:
        result=run(label,args.core_python,['-m','telegram_patterns','run-recipe',recipe,'--offline','--json'],expected=2)
        assert not json.loads(result.stdout)['offline_ready'] and json.loads(result.stderr)['error']=='UnsupportedCapability'
    run('unknown-id',args.core_python,['-m','telegram_patterns','run-recipe','../../PRIVATE_CANARY.py','--offline'],expected=2)
    worker=args.output/'all fixtures';worker.mkdir();(worker/'owned.txt').write_bytes(b'preserve caller notes')
    batch=json.loads(run('all-python-fixtures',args.sdk_python,['-m','telegram_patterns._offline_recipe','--all-python'],cwd=worker).stdout)
    failed=[{k:r.get(k) for k in ('recipe_id','passed','error','checks')} for r in batch['reports'] if not r['passed']]
    assert batch['passed'] and batch['recipes']==216 and not batch['telegram_requests'],(batch['recipes'],failed[:5])
    assert len({r['recipe_id'] for r in batch['reports']})==216
    assert all(r['passed'] and not r['telegram_requests'] and r['external_network_attempts']==0 and r['checks'] for r in batch['reports'])
    assert [p.name for p in worker.iterdir()]==['owned.txt'] and (worker/'owned.txt').read_bytes()==b'preserve caller notes',sorted(p.name for p in worker.iterdir())
    guards='''import asyncio,json,sys
from telegram_patterns._offline_recipe import _install_guards
from aiogram.client.session.aiohttp import AiohttpSession
counter=_install_guards(sdk=True)
denied=False
try:sys.audit('socket.connect',None,('198.51.100.1',443))
except RuntimeError:denied=True
assert denied and counter[0]==1
async def check():
 session=AiohttpSession()
 try:
  try:await session.make_request(None,None)
  except RuntimeError:pass
  else:raise AssertionError('HTTP was not refused')
 finally:await session.close()
asyncio.run(check())
assert counter[0]==2
print(json.dumps({'passed':True,'denied':counter[0],'network':False}))
'''
    guard=json.loads(run('guards',args.sdk_python,['-c',guards]).stdout);assert guard['passed'] and guard['denied']==2
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in project.iterdir()}
    report={'passed':True,'version':origins[0]['version'],'installed_origins':origins,'python_recipes':batch['recipes'],
            'recipes':batch['reports'],'native_reference_refused':True,'missing_sdk_refused':True,'plan_before_result':True,
            'caller_files_preserved':True,'owned_worker_notes_preserved':True,'no_secret_payload_reflected':True,
            'guard_checks':guard,'telegram_requests':False,'stages':stages,
            'scope':'Installed core/SDK wheel; all 216 Python fixtures. Native fragments remain reference. No live permissions, server auth, physical client or OS sandbox claim.'}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,ensure_ascii=False));return 0


if __name__=='__main__':
    if not __debug__:raise SystemExit('Verification needs assertions enabled')
    raise SystemExit(main())
