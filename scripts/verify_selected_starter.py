"""Installed CLI selection, dry-run, conflict and generated Dispatcher checks."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from telegram_patterns import starter_components


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--tarball',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    sources=[args.wheel.resolve(strict=True),args.tarball.resolve(strict=True)]
    args.output.mkdir()
    supplied=args.output/'supplied artifacts with spaces';supplied.mkdir()
    wheel,tarball=[supplied/source.name for source in sources]
    for source,target in zip(sources,(wheel,tarball)): shutil.copyfile(source,target)
    environment=dict(os.environ)
    for name in ('BOT_TOKEN','PYTHONPATH','PYTHONHOME'): environment.pop(name,None)
    environment['PYTHONUTF8']='1'
    def cli(*arguments,expected=0):
        done=subprocess.run([sys.executable,'-m','telegram_patterns',*map(str,arguments)],cwd=args.output,env=environment,
                            capture_output=True,text=True,encoding='utf-8',timeout=60)
        if done.returncode!=expected: raise RuntimeError('Installed selection CLI returned an unexpected status')
        return json.loads(done.stderr if expected else done.stdout)
    listed=cli('init','--list-components')
    groups=starter_components()
    assert [item['id'] for item in listed['components']]==[item.id for item in groups]
    target=args.output/'all selected'
    command=['init',target,'--library',wheel,'--typescript',tarball,'--template','bot-mini-app']
    for group in groups: command.extend(('--component',group.id))
    dry=cli(*command,'--dry-run');assert not dry['created'] and not target.exists()
    created=cli(*command);assert created['created'] and not created['network']
    files={p.relative_to(target).as_posix():p.read_bytes() for p in target.rglob('*') if p.is_file()}
    assert sorted(files)==dry['files']==created['files']
    assert dry['components']==created['components']==[group.id for group in groups]
    (target/'user-owned.txt').write_bytes(b'keep selected project')
    before={p.relative_to(target).as_posix():p.read_bytes() for p in target.rglob('*') if p.is_file()}
    cli(*command,expected=2)
    assert before=={p.relative_to(target).as_posix():p.read_bytes() for p in target.rglob('*') if p.is_file()}
    blocked=args.output/'blocked'
    for component,reason in (('api-client','component-template'),('SECRET_CANARY','unknown-component')):
        error=cli('init',blocked,'--library',wheel,'--component',component,expected=2)
        assert error['reason']==reason and 'SECRET_CANARY' not in json.dumps(error) and not blocked.exists()
    done=subprocess.run([sys.executable,'offline_components.py'],cwd=target,env=environment,capture_output=True,text=True,encoding='utf-8',timeout=60)
    if done.returncode: raise RuntimeError('Selected component Dispatcher failed')
    offline=json.loads(done.stdout)
    assert offline['passed'] and not offline['network'] and offline['checked_submissions']==1 and offline['session_closed']
    report={'passed':True,'network':False,'components':len(groups),'files':len(files),
            'project':str(target.resolve()),'dry_run_exact':True,'repeat_preserved':True,'conflicts_without_write':2,'offline':offline}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,ensure_ascii=False))
    return 0


if __name__=='__main__':
    if not __debug__: raise SystemExit('Selection verification needs assertions enabled')
    raise SystemExit(main())
