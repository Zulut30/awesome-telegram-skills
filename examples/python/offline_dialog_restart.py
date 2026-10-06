"""Three actual processes on file SQLite, SDK Dispatcher and StubSession only."""
from __future__ import annotations
import argparse
import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import Update
from telegram_patterns import SQLiteOnce
from telegram_patterns.aiogram import DialogLifetime, SnapshotFSMStorage
from telegram_patterns.testing import StubSession
from dialog_restart_bot import ProjectSnapshotStore, attach_dialog


async def phase(database: Path, mode: str) -> dict:
    from telegram_patterns._offline_recipe import _install_guards
    attempts = _install_guards(sdk=True)
    store = ProjectSnapshotStore(database); store.initialize()
    effects = SQLiteOnce(database); effects.initialize()
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            connection.execute('CREATE TABLE IF NOT EXISTS bookings(operation TEXT PRIMARY KEY, body TEXT NOT NULL)')
    received = []
    now = 100.0 if mode == 'draft' else 120.0 if mode == 'unknown' else 1000.0
    lifetime = DialogLifetime(60, clock=lambda: now)
    replies = []
    def response(method):
        reply = {'message_id': 1000 + len(replies), 'date': 1,
            'chat': {'id': method.chat_id, 'type': 'private'}, 'text': method.text,
            'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'}}
        replies.append((method, reply)); return reply
    session = StubSession().respond(SendMessage, response).respond(AnswerCallbackQuery, True)
    bot = Bot('100:RESTART_FIXTURE', session=session)
    storage = SnapshotFSMStorage(store)
    dispatcher = Dispatcher(storage=storage, events_isolation=SimpleEventIsolation())
    existing = Router()
    @existing.message(Command('help'))
    async def help(message): await message.answer('Existing help preserved', parse_mode=None)
    dispatcher.include_router(existing)
    async def submit(value):
        assert isinstance(session.calls[-1], AnswerCallbackQuery)
        assert (value.bot_id, value.chat_id, value.actor_id) == (100, 42, 42)
        received.append(value.operation_id)
        def apply(connection):
            connection.execute('INSERT INTO bookings VALUES(?,?)',
                               (value.operation_id, json.dumps(value.as_dict())))
            return 'Бронь принята.'
        receipt = effects.run('booking:100:42:42', value.operation_id, value.as_dict(), apply)
        if mode == 'unknown':
            raise TimeoutError('Fixture receipt lost after a committed project effect')
        return receipt.value
    attach_dialog(dispatcher, submit, lifetime=lifetime)
    assert dispatcher.fsm.storage is storage and existing in dispatcher.sub_routers
    state = dispatcher.fsm.get_context(bot=bot, chat_id=42, user_id=42)
    index = {'draft': 0, 'unknown': 100, 'reconcile': 200}[mode]
    async def send(text, *, actor=42, reply_to=None):
        nonlocal index
        index += 1
        message = {'message_id': index, 'date': 1, 'chat': {'id': actor, 'type': 'private'},
            'from': {'id': actor, 'is_bot': False, 'first_name': 'Owner'}, 'text': text}
        if reply_to is not None: message['reply_to_message'] = reply_to
        await dispatcher.feed_update(bot, Update.model_validate({'update_id': index, 'message': message}))
    async def click(message, data):
        nonlocal index
        index += 1
        await dispatcher.feed_update(bot, Update.model_validate({'update_id': index, 'callback_query': {
            'id': str(index), 'chat_instance': 'fixture', 'from': {'id': 42, 'is_bot': False, 'first_name': 'Owner'},
            'message': message, 'data': data}}))
    async def data(): return (await state.get_data())['__telegram_patterns_dialog']
    try:
        if mode == 'draft':
            await state.update_data(host={'language': 'ru'})
            await send('/booking')
            await send('Owner@EXAMPLE.COM', reply_to=replies[-1][1])
            saved = await data()
            assert saved['index'] == 1 and saved['values'] == {'email': 'Owner@example.com'}
            assert saved['schema'][0] == 1 and saved['lifetime']['expires_at'] == 160.0
            result = {'accepted_step': 1, 'operation': saved['operation_id'], 'deadline': 160.0}
        elif mode == 'unknown':
            before = await data()
            await send('/booking'); saved = await data()
            assert saved['values'] == before['values'] and saved['operation_id'] == before['operation_id']
            assert saved['lifetime'] == before['lifetime']
            await send('2', reply_to=replies[-1][1]); saved = await data()
            review_method, review_message = replies[-1]
            callback = review_method.reply_markup.inline_keyboard[0][0].callback_data
            try: await click(review_message, callback)
            except TimeoutError: pass
            else: raise AssertionError('Unknown receipt was swallowed')
            pending = await data(); assert pending['submission_started']
            database.with_suffix('.ui.json').write_text(json.dumps({'message': review_message, 'callback': callback}), encoding='utf-8')
            await send('/booking', actor=99)
            result = {'resumed_answers': True, 'pending_operation': pending['operation_id'], 'deadline': pending['lifetime']['expires_at']}
        else:
            pending = await data(); assert pending['submission_started'] and lifetime.expired(pending['lifetime'])
            changed = Dispatcher(storage=SnapshotFSMStorage(ProjectSnapshotStore(database)), events_isolation=SimpleEventIsolation())
            attach_dialog(changed, submit, lifetime=lifetime, schema_version=2)
            try:
                before = await storage.read_snapshot(state.key)
                try:
                    await changed.feed_update(bot, Update.model_validate({'update_id': 999, 'message': {
                        'message_id': 999, 'date': 1, 'chat': {'id': 42, 'type': 'private'},
                        'from': {'id': 42, 'is_bot': False, 'first_name': 'Owner'}, 'text': '/booking'}}))
                except RuntimeError: pass
                else: raise AssertionError('Changed version reset pending identity')
                assert await storage.read_snapshot(state.key) == before
            finally: await changed.fsm.close()
            for command in ('/booking', '/back', '/cancel'): await send(command)
            assert await data() == pending
            await send('/cancel', actor=99)
            other = dispatcher.fsm.get_context(bot=bot, chat_id=99, user_id=99)
            assert await other.get_state() is None and await other.get_data() == {}
            ui = json.loads(database.with_suffix('.ui.json').read_text(encoding='utf-8'))
            await click(ui['message'], ui['callback']); await click(ui['message'], ui['callback'])
            assert received == [pending['operation_id']]
            assert await state.get_state() is None and await state.get_data() == {'host': {'language': 'ru'}}
            await send('/help'); assert replies[-1][0].text == 'Existing help preserved'
            with closing(sqlite3.connect(database)) as connection:
                rows = connection.execute('SELECT operation,body FROM bookings').fetchall()
            assert len(rows) == 1 and rows[0][0] == pending['operation_id']
            assert json.loads(rows[0][1]) == {'email': 'Owner@example.com', 'seats': '2'}
            result = {'reconciled_operation': pending['operation_id'], 'business_effects': 1,
                'expired_draft_removed': True, 'expired_pending_preserved': True, 'version_refused_without_reset': True,
                'host_data_preserved': True, 'existing_dispatcher_preserved': True}
        assert all(method.parse_mode is None for method, _ in replies)
        assert attempts[0] == 0
    finally:
        await dispatcher.fsm.close(); await bot.session.close()
    return dict(result, passed=True, network=False, session_closed=session.closed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('draft', 'unknown', 'reconcile'))
    parser.add_argument('--database', type=Path)
    args = parser.parse_args()
    if args.phase:
        if args.database is None: parser.error('--database required for phase')
        print(json.dumps(asyncio.run(phase(args.database, args.phase)))); return
    phases = []
    with tempfile.TemporaryDirectory(prefix='dialog restart proof ') as folder:
        database = Path(folder) / 'project.sqlite'
        environment = {k: v for k, v in os.environ.items() if k.upper() in
            {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'PATHEXT', 'LANG', 'LC_ALL'}}
        environment['PYTHONUTF8'] = '1'
        # -I removes caller cwd/PYTHONPATH; only our fresh trusted bundle is added.
        bootstrap = ('import runpy,sys;from pathlib import Path;'
            'p=Path(sys.argv[1]).resolve(strict=True);sys.path.insert(0,str(p.parent));'
            'sys.argv=sys.argv[1:];runpy.run_path(str(p),run_name="__main__")')
        for mode in ('draft', 'unknown', 'reconcile'):
            result = subprocess.run([sys.executable, '-I', '-B', '-c', bootstrap, str(Path(__file__).resolve()),
                '--phase', mode, '--database', str(database)], env=environment,
                capture_output=True, text=True, encoding='utf-8', timeout=60)
            if result.returncode: raise RuntimeError(result.stdout + result.stderr)
            phases.append(json.loads(result.stdout))
        assert phases[0]['operation'] == phases[1]['pending_operation'] == phases[2]['reconciled_operation']
        assert phases[0]['deadline'] == phases[1]['deadline'] == 160.0
    print(json.dumps(dict(phases[-1], processes=3, resumed_answers=True, original_deadline_preserved=True,
        operation_ids_match=True, separate_process_restart=True)))


if __name__ == '__main__': main()
