"""Install the independent shop and prove server-owned orders in actual Chrome."""
from __future__ import annotations
import argparse
import base64
import csv
import hashlib
import io
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
from _environment import minimal_environment, planted_link  # noqa: E402

ROOT=Path(__file__).resolve().parents[1]


def library_version() -> str:
    """Version of the pattern library in this checkout; examples must use the current one."""
    return re.search(r'^version\s*=\s*"([^"]+)"', (ROOT/'packages/python/pyproject.toml').read_text(encoding='utf-8'), re.M).group(1)


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--tarball',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for p in (args.output,*args.output.parents):
        if planted_link(p):raise ValueError('Output links are not supported')
    sources=[p.resolve(strict=True) for p in (args.wheel,args.tarball)]
    if any(not p.is_file() for p in sources) or sources[0].suffix!='.whl' or sources[1].suffix!='.tgz':raise ValueError('Provide trusted local wheel/tarball')
    output=args.output.resolve();output.mkdir(parents=True)  # parent links were refused above; the leaf must be new
    consumer=Path(tempfile.mkdtemp(prefix='telegram shop consumer '));venv=consumer/'environment'
    env=minimal_environment();env['PYTHONUTF8']='1'
    if 'CHROME_PATH' not in env:
        chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
        if chrome.is_file():env['CHROME_PATH']=str(chrome)
    stages=[]
    def run(label,argv,*,cwd=consumer,timeout=180):
        p=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',timeout=timeout)
        assert 'PRIVATE_CANARY' not in p.stdout+p.stderr
        (output/(label+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        stages.append({'stage':label,'exit_code':p.returncode})
        if p.returncode:raise RuntimeError(label+' failed; inspect saved log')
        return p.stdout
    uv=shutil.which('uv');node=shutil.which('node');npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm');assert uv and node and npm
    dist=output/'dist';dist.mkdir()
    run('build-example',[uv,'build','--wheel','--out-dir',dist,ROOT/'examples/shop'])
    example=dist/'awesome_telegram_shop_example-0.1.0-py3-none-any.whl'
    package=ROOT/'examples/shop/src';expected={p.relative_to(package).as_posix():p.read_bytes() for p in package.rglob('*') if p.is_file() and p.suffix in {'.py','.typed'}}
    with zipfile.ZipFile(example) as archive:
        actual={n for n in archive.namelist() if n.startswith('telegram_shop_example/')}
        assert actual==set(expected) and all(archive.read(n)==v for n,v in expected.items())
        records=[n for n in archive.namelist() if n.endswith('.dist-info/RECORD')];assert len(records)==1
        entries=list(csv.reader(io.StringIO(archive.read(records[0]).decode())))
        assert {r[0] for r in entries}==set(archive.namelist())
        for name,encoded,size in entries:
            if name==records[0]:assert not encoded and not size;continue
            value=archive.read(name);assert encoded=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(value).digest()).decode().rstrip('=') and int(size)==len(value)
        entrypoints=[n for n in archive.namelist() if n.endswith('.dist-info/entry_points.txt')];assert len(entrypoints)==1 and b'telegram-shop-example = telegram_shop_example.runtime:main' in archive.read(entrypoints[0])
    run('environment',[uv,'venv','--python',sys.executable,venv]);python=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    run('install',[uv,'pip','install','--python',python,str(sources[0])+'[aiogram]',example,'aiogram==3.31.0','mypy==2.4.0'])
    origin=json.loads(run('origin',[python,'-I','-c',"import sys,json,telegram_patterns,telegram_shop_example,importlib.metadata as m;print(json.dumps({'prefix':sys.prefix,'library':telegram_patterns.__file__,'example':telegram_shop_example.__file__,'library_version':m.version('awesome-telegram-patterns'),'aiogram':m.version('aiogram'),'python':sys.version.split()[0],'aiohttp':m.version('aiohttp')}))"]))
    assert all(Path(origin[k]).is_relative_to(Path(origin['prefix'])) for k in ('library','example')) and origin['library_version']==library_version()
    console=python.parent/('telegram-shop-example.exe' if os.name=='nt' else 'telegram-shop-example')
    help_text=run('entrypoint-help',[console,'--help']);assert all(option in help_text for option in ('--origin','--terms-version','--database','--support'))
    run('typecheck',[python,'-m','mypy','--check-untyped-defs','--warn-unused-ignores',ROOT/'examples/shop/src'])
    run('tests',[python,'-I','-m','unittest','discover','-s',ROOT/'examples/shop/tests','-v'])
    test_log=(output/'tests.log').read_text(encoding='utf-8')
    matched=re.search(r'Ran (\d+) tests',test_log)
    if not matched:
        raise RuntimeError('Shop test runner did not report executed tests')
    unit_tests=int(matched.group(1))
    required_tests=('test_rotation_and_current_session_revoke_are_durable_and_actor_bound',
                    'test_every_private_object_route_uses_server_actor_and_owner_acl',
                    'test_lost_order_and_rotation_replies_reconcile_same_operation_after_restart',
                    'test_http_session_order_and_revoke_survive_actual_process_death',
                    'test_current_roles_gate_reads_writes_invoice_and_saved_replay',
                    'test_role_revocation_precedes_queued_writer_and_late_receipt_is_reviewed',
                    'test_additive_v1_role_migration_preserves_sessions_orders_and_access',
                    'test_start_payload_is_a_bounded_screen_hint_and_group_launch_is_not_sent',
                    'test_actual_process_crashes_preserve_refund_and_block_content_before_projection',
                    'test_actual_process_crash_before_handler_replays_durable_sdk_batch_after_restart',
                    'test_actual_sdk_polling_retries_failed_admission_without_advancing_offset',
                    'test_current_operator_and_session_are_rechecked_between_reserve_and_send',
                    'test_mismatched_or_optional_history_fields_never_confirm_and_never_resend',
                    'test_cancelled_worker_joins_owned_sqlite_write_then_retains_claim_for_safe_replay',
                    'test_actual_sdk_polling_precheckout_answers_before_blocked_ordinary_handler_is_released',
                    'test_expired_real_admission_never_sends_positive_after_backlog_or_restart',
                    'test_failed_batch_cannot_be_ready_or_approve_and_retry_retains_first_admission',
                    'test_capacity_overflow_is_durable_quarantine_without_late_positive',
                    'test_lost_positive_answer_is_unknown_and_replay_restart_never_resends_true',
                    'test_legacy_zero_lane_query_is_never_promoted_or_given_fresh_deadline',
                    'test_actual_process_crash_before_storage_refuses_unknown_first_admission',
                    'test_actual_process_crash_after_positive_rpc_never_resends_on_restart',
                    'test_prepare_default_shop_needs_no_optional_outbox_and_preserves_paid_facts',
                    'test_post_checkpoint_effect_does_not_make_restored_pending_safely_retryable',
                    'test_real_http_and_sdk_requests_stay_closed_for_old_and_new_actors',
                    'test_runtime_maintenance_opens_readiness_without_recover_polling_or_sdk',
                    'test_actual_old_or_candidate_owner_refuses_before_restoration',
                    'test_process_crashes_leave_final_absent_or_already_guarded',
                    'test_bad_digest_existing_target_wrong_context_and_unknown_marker_fail_closed',
                    'test_operator_cli_prepare_inspect_and_no_activation_or_secret_echo')
    if unit_tests < 61 or not test_log.rstrip().endswith('OK') or any(name not in test_log for name in required_tests):
        raise RuntimeError('Shop acceptance requires all existing tests and durable session/ACL/restart scenarios')
    frontend=consumer/'frontend';shutil.copytree(ROOT/'examples/shop/frontend',frontend,ignore=shutil.ignore_patterns('node_modules','dist'))
    supplied=consumer/'provided artifacts';supplied.mkdir();tarball=supplied/sources[1].name;shutil.copyfile(sources[1],tarball)
    package_json=frontend/'package.json';data=json.loads(package_json.read_text());data['dependencies']['@awesome-telegram/patterns']='file:'+tarball.as_posix();package_json.write_text(json.dumps(data,indent=2)+'\n')
    run('frontend-install',[npm,'install','--ignore-scripts'],cwd=frontend)
    run('frontend-build',[npm,'run','build'],cwd=frontend)
    domain_log=run('headless-domain',[node,'--test','tests/domain.test.mjs'],cwd=frontend)
    headless_count=re.search(r'\btests\s+(\d+)\b',domain_log)
    required_headless=('reload and missing original operation never dispatch',
                       'changed terms and account scope prevent a stale saved-intent retry',
                       'transport captures immutable server credential',
                       'launch hints distinguish signed-field routing',
                       'a server-confirmed refund completes only its original pending pointer')
    if not headless_count or int(headless_count.group(1))<5 or not re.search(r'\bfail\s+0\b',domain_log) or not re.search(r'\bskipped\s+0\b',domain_log) or any(name not in domain_log for name in required_headless):
        raise RuntimeError('Headless shop requires all five domain/transport/launch/refund cases without skips')
    installed=frontend/'node_modules/@awesome-telegram/patterns';metadata=json.loads((installed/'package.json').read_text());assert metadata['version']==library_version()
    copied_files=0
    for p in (installed/'dist').rglob('*'):
        if p.is_file():assert p.read_bytes()==(frontend/'dist/assets/vendor'/p.relative_to(installed/'dist')).read_bytes();copied_files+=1
    assert (frontend/'dist/assets/vendor/styles.css').is_file()  # the stylesheet ships in the library's dist
    caller=consumer/'caller project';caller.mkdir();(caller/'aiogram.py').write_text("raise RuntimeError('PRIVATE_CANARY')");(caller/'.env').write_text('BOT_TOKEN=100:PRIVATE_CANARY');(caller/'owned.txt').write_text('preserve caller')
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in caller.iterdir()}
    run('browser',[node,ROOT/'scripts/check_shop_browser.mjs',python,frontend/'dist',output/'browser',caller],timeout=480)
    browser=json.loads((output/'browser/report.json').read_text(encoding='utf-8'));assert browser['passed'] and len(browser['cases'])==7 and browser['telegram_web_iframe'] is True and browser['read_only_recovery'] is True and browser['explicit_original_retry'] is True and browser['stars_refund_ui'] is True and len(browser['launch_profiles'])==5 and browser['external_requests']==0 and browser['telegram_requests'] is False
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in caller.iterdir()}
    report={'passed':True,'roadmap_item':18,'library_version':library_version(),'application_version':'0.1.0','installed_origins':origin,'typescript_consumer':str(installed),'typescript_version':metadata['version'],'vendor_byte_exact_files':copied_files,'archive_source_exact_files':len(expected),'wheel_record_verified':True,'installed_entrypoint_help':True,'unit_tests':unit_tests,'headless_domain_tests':int(headless_count.group(1)),'stages':stages,'browser':browser,'caller_files_preserved':True,'artifacts':[{'name':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (*sources,example)],'scope':'Installed Python application and pattern wheel/tarball; real SQLite, HTTP, process restart and Chrome, including a cross-site iframe as in Telegram Web. Synthetic launch/native/SDK transport. No live Telegram/Stars test environment or physical devices.'}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report));return 0


if __name__=='__main__':
    if not __debug__:raise SystemExit('Verification needs assertions enabled')
    raise SystemExit(main())
