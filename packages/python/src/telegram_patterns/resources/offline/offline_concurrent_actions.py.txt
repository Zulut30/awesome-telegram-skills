"""Two independent SDK workers per race; owned SQLite and no Telegram HTTP."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import Update
from telegram_patterns.testing import StubSession
from concurrent_actions_bot import ActionOrigin, ProjectActions, action_button, attach_actions


async def app(database: Path,*,lost_feedback: bool = False,bot_id: int = 100):
    from telegram_patterns._offline_recipe import _install_guards
    attempts = _install_guards(sdk=True)
    session = StubSession().respond(AnswerCallbackQuery,True).respond(SendMessage,
        lambda m:{'message_id':901,'date':1,'chat':{'id':m.chat_id,'type':'private'},'text':m.text})
    bot = Bot(f'{bot_id}:CONCURRENCY_FIXTURE',session=session)
    dispatcher = Dispatcher()
    before_storage = dispatcher.fsm.storage
    before_isolation = dispatcher.fsm.events_isolation
    results = []
    host = Router(name='existing-help')
    @host.message(Command('help'))
    async def help(message):
        await message.answer('Existing help',parse_mode=None)
    dispatcher.include_router(host)
    async def notify(query,result):
        assert isinstance(session.calls[-1],AnswerCallbackQuery)
        results.append({'status':result.status,'text':result.text})
        if lost_feedback and result.status=='accepted':
            raise TimeoutError('Injected loss after the committed local effect')
    attach_actions(dispatcher,ProjectActions(database),notify)
    assert dispatcher.fsm.storage is before_storage and dispatcher.fsm.events_isolation is before_isolation
    assert dispatcher.sub_routers[0] is host
    return bot,dispatcher,session,results,attempts


def callback(operation: str,*,actor: int = 42,chat: int = 42,message_id: int = 900,
             bot_id: int = 100,thread: int | None = None,business: str | None = None,
             accessible: bool = True,inline: bool = False,user_bot: bool = False,
             chat_type: str | None = None) -> Update:
    message = {'message_id':message_id,'date':1 if accessible else 0,
               'chat':{'id':chat,'type':chat_type or ('private' if chat>0 else 'supergroup')},
               'from':{'id':bot_id,'is_bot':True,'first_name':'Fixture'}}
    if thread is not None:
        message.update(message_thread_id=thread,is_topic_message=True)
    if business is not None:
        message['business_connection_id'] = business
    body = {'id':str(time.monotonic_ns()),'chat_instance':'synthetic',
            'from':{'id':actor,'is_bot':user_bot,'first_name':'Actor'},'data':'once:'+operation}
    if inline:
        body['inline_message_id'] = 'inline-without-project-origin'
    else:
        body['message'] = message
    return Update.model_validate({'update_id':1,'callback_query':body})


async def close(bot,dispatcher,session,attempts):
    await dispatcher.fsm.close()
    await bot.session.close()
    assert session.closed and attempts[0]==0


async def worker(database: Path,operation: str,gate: Path,ready: Path,lost: bool) -> dict:
    bot,dispatcher,session,results,attempts = await app(database,lost_feedback=lost)
    try:
        ready.write_bytes(b'ready')
        deadline = time.monotonic()+45
        while not gate.is_file():
            if time.monotonic()>=deadline:
                raise TimeoutError('Owned fixture barrier expired')
            await asyncio.sleep(0.02)
        try:
            await dispatcher.feed_update(bot,callback(operation))
        except TimeoutError:
            assert lost and results[-1]['status']=='accepted'
            status = 'unknown-feedback'
        else:
            status = results[-1]['status']
        assert len(session.calls)==1 and isinstance(session.calls[0],AnswerCallbackQuery)
    finally:
        await close(bot,dispatcher,session,attempts)
    return {'status':status,'operation_id':operation,'session_closed':session.closed,
            'network':False,'external_network_attempts':attempts[0],
            'existing_dispatcher_preserved':True,'pid':os.getpid()}


def race(database: Path,operations: tuple[str,str],area: Path,*,lost: bool) -> list[dict]:
    environment = {k:v for k,v in os.environ.items() if k.upper() in
                   {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','PATHEXT','LANG','LC_ALL'}}
    environment['PYTHONUTF8'] = '1'
    bootstrap = ('import runpy,sys;from pathlib import Path;'
        'p=Path(sys.argv[1]).resolve(strict=True);sys.path.insert(0,str(p.parent));'
        'sys.argv=sys.argv[1:];runpy.run_path(str(p),run_name="__main__")')
    children = []
    try:
        for i,operation in enumerate(operations):
            command = [sys.executable,'-I','-B','-c',bootstrap,str(Path(__file__).resolve()),
                       '--worker','--database',str(database),'--operation',operation,
                       '--gate',str(area/'go'),'--ready',str(area/f'ready-{i}')]
            if lost: command.append('--lost-feedback')
            children.append(subprocess.Popen(command,cwd=area,env=environment,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,text=True,encoding='utf-8'))
        deadline = time.monotonic()+45
        while not all((area/f'ready-{i}').is_file() for i in range(2)):
            if any(p.poll() is not None for p in children) or time.monotonic()>=deadline:
                raise RuntimeError('Independent SDK workers failed to reach the owned barrier')
            time.sleep(0.02)
        (area/'go').write_bytes(b'go')
        results = []
        for p in children:
            stdout,stderr = p.communicate(timeout=45)
            if p.returncode: raise RuntimeError(stdout+stderr)
            results.append(json.loads(stdout))
        assert len({r['pid'] for r in results})==2
        assert all(r['session_closed'] and not r['network'] and r['external_network_attempts']==0 for r in results)
        return results
    finally:
        for p in children:
            if p.poll() is None: p.kill()
            p.communicate(timeout=15)


async def probes(database: Path,operation: str) -> dict:
    bot,dispatcher,session,results,attempts = await app(database)
    try:
        await dispatcher.feed_update(bot,callback(operation))
        assert results[-1]['status']=='replayed'
        for changes in ({'actor':99},{'chat':99},{'message_id':901},{'thread':7},
                        {'business':'foreign-connection'},{'accessible':False},
                        {'inline':True},{'user_bot':True}):
            await dispatcher.feed_update(bot,callback(operation,**changes))
            assert results[-1]['status']=='denied',changes
            assert results[-1]['text']=='Действие недоступно.'
        await dispatcher.feed_update(bot,callback('bad-token'))
        assert results[-1]['status']=='stale'
        await dispatcher.feed_update(bot,callback('0'*32))
        assert results[-1]['status']=='denied'
        with closing(sqlite3.connect(database)) as c,c:
            c.execute('UPDATE project_action_acl SET allowed=0')
        await dispatcher.feed_update(bot,callback(operation))
        assert results[-1]['status']=='denied' and results[-1]['text']=='Действие недоступно.'
        message = {'message_id':7,'date':1,'chat':{'id':42,'type':'private'},
                   'from':{'id':42,'is_bot':False,'first_name':'Actor'},'text':'/help'}
        await dispatcher.feed_update(bot,Update.model_validate({'update_id':2,'message':message}))
        assert session.calls[-1].text=='Existing help'
    finally:
        await close(bot,dispatcher,session,attempts)
    other_bot,other_dp,other_session,other_results,other_attempts = await app(database,bot_id=101)
    try:
        await other_dp.feed_update(other_bot,callback(operation,bot_id=101))
        assert other_results[-1]['status']=='denied'
    finally:
        await close(other_bot,other_dp,other_session,other_attempts)
    return {'fresh_acl_replay':True,'actor_origin_guards':True,'existing_dispatcher_preserved':True,
            'unknown_feedback_reconciled':True,'session_closed':session.closed and other_session.closed}


async def group_probe(database: Path,chat_type: str,thread: int | None) -> None:
    service = ProjectActions(database)
    service.initialize()
    origin = ActionOrigin(100,-100,42,900,thread)
    with closing(sqlite3.connect(database)) as c,c:
        c.execute('INSERT INTO project_resources VALUES(?,?,?)',('group-resource',0,1))
        c.execute('INSERT INTO project_action_acl VALUES(?,?,?,?,?)',('group-resource',100,-100,42,1))
    operation = service.issue(origin,'group-resource',5)
    bot,dp,session,results,attempts = await app(database)
    try:
        for expected in ('accepted','replayed'):
            await dp.feed_update(bot,callback(operation,chat=-100,chat_type=chat_type,thread=thread))
            assert results[-1]['status']==expected
        await dp.feed_update(bot,callback(operation,chat=-100,chat_type=chat_type,thread=8))
        assert results[-1]['status']=='denied'
    finally:
        await close(bot,dp,session,attempts)
    with closing(sqlite3.connect(database)) as c:
        assert c.execute('SELECT count(*) FROM project_action_changes').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM telegram_pattern_operations').fetchone()[0]==1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--database',type=Path)
    parser.add_argument('--operation')
    parser.add_argument('--gate',type=Path)
    parser.add_argument('--ready',type=Path)
    parser.add_argument('--lost-feedback',action='store_true')
    args = parser.parse_args()
    if args.worker:
        if any(v is None for v in (args.database,args.operation,args.gate,args.ready)):
            parser.error('Explicit owned worker paths and operation required')
        print(json.dumps(asyncio.run(worker(args.database,args.operation,args.gate,args.ready,args.lost_feedback))))
        return
    with tempfile.TemporaryDirectory(prefix='concurrent actions proof ') as folder:
        root = Path(folder)
        origin = ActionOrigin(100,42,42,900)
        outcomes = []
        effect_counts = []
        for name,same,lost in (('same-operation',True,True),('same-revision',False,False)):
            area = root/name
            area.mkdir()
            database = area/'project.sqlite'
            marker = area/'caller-owned.bin'
            marker.write_bytes(b'preserve\x00\xff')
            service = ProjectActions(database)
            service.initialize()
            with closing(sqlite3.connect(database)) as c,c:
                c.execute('INSERT INTO project_resources VALUES(?,?,?)',('fixture-resource',0,1))
                c.execute('INSERT INTO project_action_acl VALUES(?,?,?,?,?)',('fixture-resource',100,42,42,1))
            first = service.issue(origin,'fixture-resource',5)
            second = first if same else service.issue(origin,'fixture-resource',6)
            assert len(action_button(first).callback_data.encode())<=64
            results = race(database,(first,second),area,lost=lost)
            assert sorted(r['status'] for r in results)==(['replayed','unknown-feedback'] if same else ['accepted','stale'])
            if same:
                assert len({r['operation_id'] for r in results})==1
                proof = asyncio.run(probes(database,first))
            with closing(sqlite3.connect(database)) as c:
                effects = c.execute('SELECT count(*) FROM project_action_changes').fetchone()[0]
                assert effects==c.execute('SELECT count(*) FROM telegram_pattern_operations').fetchone()[0]==1
                assert c.execute('SELECT revision FROM project_resources').fetchone()[0]==2
            assert marker.read_bytes()==b'preserve\x00\xff'
            outcomes.append(results)
            effect_counts.append(effects)
        for chat_type,thread in (('group',None),('supergroup',7)):
            asyncio.run(group_probe(root/(chat_type+'.sqlite'),chat_type,thread))
            effect_counts.append(1)
    print(json.dumps(dict(proof,passed=True,network=False,workers=2,actual_worker_processes=4,
        business_effects=sum(effect_counts),effects_per_case=effect_counts,
        same_operation_replayed=True,different_operations_stale=True,stable_operation_id=True,
        caller_files_preserved=True,positive_group_topic=True,races=outcomes)))


if __name__=='__main__': main()
