import asyncio
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import importlib.util
import math
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from aiogram import Bot, Dispatcher
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.methods import SendMessage, AnswerCallbackQuery
from aiogram.types import Message, Update
from telegram_patterns.aiogram import (AtomicFSMStorage, DialogLifetime, FSMSnapshot, FSMConflict,
    SnapshotFSMStorage, TextField, text_form_router, dialog_form_router, ContactField)
from telegram_patterns.testing import StubSession

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('dialog_restart_example', ROOT / 'examples/python/dialog_restart_bot.py')
example = importlib.util.module_from_spec(spec); spec.loader.exec_module(example)
ProjectSnapshotStore = example.ProjectSnapshotStore
DATE = datetime(2026, 10, 5, tzinfo=timezone.utc)
KEY = StorageKey(bot_id=100, chat_id=42, user_id=42)


class SnapshotTests(unittest.TestCase):
    def test_json_snapshot_detaches_nested_values_and_hides_answers(self):
        values = {'answer': {'private': ['canary-secret']}}
        snapshot = FSMSnapshot('form', values, 3)
        values['answer']['private'].append('changed')
        returned = snapshot.data; returned['answer']['private'].clear()
        self.assertEqual(snapshot.data, {'answer': {'private': ['canary-secret']}})
        self.assertNotIn('canary', repr(snapshot))
        self.assertEqual(snapshot, FSMSnapshot('form', snapshot.data, 3))

    def test_bad_json_and_revisions_are_refused_before_persistence(self):
        for values in ({'x': math.nan}, {'x': math.inf}, {1: 'bad'}, {'x': object()}, {'x': ('tuple',)},
                       {'x': '\ud800'}, {'x': 'a' * 65536}):
            with self.subTest(values=type(values)), self.assertRaises(ValueError): FSMSnapshot(None, values)
        for revision in (-1, True, 2**63-1):
            with self.assertRaises(ValueError): FSMSnapshot(None, {}, revision)
        nested = {}; cursor = nested
        for _ in range(18): cursor['x'] = {}; cursor = cursor['x']
        with self.assertRaises(ValueError): FSMSnapshot(None, nested)

    def test_lifetime_uses_original_deadline_and_rejects_corruption(self):
        clock = [100.0]; policy = DialogLifetime(60, lambda: clock[0]); value = policy.start()
        clock[0] = 159.0; self.assertFalse(policy.expired(value))
        clock[0] = 160.0; self.assertTrue(policy.expired(value))
        self.assertEqual(value, {'created_at': 100.0, 'expires_at': 160.0})
        for metadata in (None, {}, {'created_at': 1, 'expires_at': 1}, {'created_at': True, 'expires_at': 2},
                         {'created_at': 1, 'expires_at': math.nan}):
            with self.assertRaises(RuntimeError): policy.expired(metadata)
        for seconds in (True, 0, 2592001):
            with self.assertRaises(ValueError): DialogLifetime(seconds)


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='fsm storage tests ')
        self.database = Path(self.folder.name) / 'project.sqlite'
        self.store = ProjectSnapshotStore(self.database); self.store.initialize()
        self.storage = SnapshotFSMStorage(self.store)

    async def asyncTearDown(self):
        await self.storage.close(); self.folder.cleanup()

    async def test_whole_snapshot_visible_to_new_adapter_after_close(self):
        old = await self.storage.read_snapshot(KEY)
        saved = await self.storage.commit_snapshot(KEY, old, 'form', {'host': 'ru', 'form': {'step': 2, 'version': 3, 'expires': 160}})
        await self.storage.close()
        restarted = SnapshotFSMStorage(ProjectSnapshotStore(self.database))
        self.assertIsInstance(restarted, AtomicFSMStorage)
        self.assertEqual(await restarted.read_snapshot(KEY), saved)
        await restarted.close()

    async def test_stale_revision_refused_with_no_partial_overwrite(self):
        old = await self.storage.read_snapshot(KEY)
        current = await self.storage.commit_snapshot(KEY, old, 'new', {'answer': 'accepted'})
        with self.assertRaises(FSMConflict): await self.storage.commit_snapshot(KEY, old, 'stale', {'answer': 'lost'})
        self.assertEqual(await self.storage.read_snapshot(KEY), current)

    async def test_all_six_storage_key_fields_remain_isolated(self):
        keys = [KEY, replace(KEY, bot_id=101), replace(KEY, chat_id=43), replace(KEY, user_id=99),
            replace(KEY, thread_id=7), replace(KEY, business_connection_id='business'), replace(KEY, destiny='other')]
        for index, key in enumerate(keys): await self.storage.set_data(key, {'owner': index})
        for index, key in enumerate(keys): self.assertEqual(await self.storage.get_data(key), {'owner': index})

    async def test_sdk_facade_state_data_updates_and_tombstone_revision(self):
        await self.storage.set_state(KEY, State('step', group_name='Group'))
        await self.storage.set_data(KEY, {'host': {'language': 'ru'}})
        returned = await self.storage.update_data(KEY, {'form': {'step': 1}})
        self.assertEqual(returned, {'host': {'language': 'ru'}, 'form': {'step': 1}})
        self.assertEqual(await self.storage.get_state(KEY), 'Group:step')
        old = await self.storage.read_snapshot(KEY)
        cleared = await self.storage.commit_snapshot(KEY, old, None, {})
        restarted = SnapshotFSMStorage(ProjectSnapshotStore(self.database))
        self.assertEqual((await restarted.read_snapshot(KEY)).revision, cleared.revision)
        with self.assertRaises(FSMConflict): await restarted.commit_snapshot(KEY, FSMSnapshot(None, {}, 0), 'ABA', {})
        await restarted.close()

    async def test_invalid_payload_never_touches_existing_snapshot(self):
        await self.storage.set_data(KEY, {'host': 'preserved'}); old = await self.storage.read_snapshot(KEY)
        with self.assertRaises(ValueError): await self.storage.commit_snapshot(KEY, old, 'bad', {'x': math.inf})
        self.assertEqual(await self.storage.read_snapshot(KEY), old)

    async def test_canceled_commit_waits_for_owned_writer_before_propagating(self):
        started, release = threading.Event(), threading.Event()
        original = self.store._commit
        def delayed(*args):
            started.set(); release.wait(5); return original(*args)
        self.store._commit = delayed
        old = await self.storage.read_snapshot(KEY)
        task = asyncio.create_task(self.storage.commit_snapshot(KEY, old, 'saved', {'x': 1}))
        self.assertTrue(await asyncio.to_thread(started.wait, 3))
        task.cancel(); await asyncio.sleep(0); self.assertFalse(task.done())
        task.cancel(); release.set()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual((await self.storage.read_snapshot(KEY)).state, 'saved')

    async def test_corrupt_disk_record_is_not_silently_reset(self):
        await self.storage.set_state(KEY, 'active')
        with closing(sqlite3.connect(self.database)) as connection:
            with connection:
                connection.execute('UPDATE dialog_snapshots SET data=?', ('not-json',))
        with self.assertRaisesRegex(RuntimeError, 'migration'): await self.storage.read_snapshot(KEY)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute('SELECT data FROM dialog_snapshots').fetchone()[0], 'not-json')


class DurableFormTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='durable form tests ')
        self.database = Path(self.folder.name) / 'project.sqlite'
        self.now = 100.0; self.sent = []; self.index = 0; self.received = []; self.fail = False
        self.session = StubSession().respond(SendMessage, self.response).respond(AnswerCallbackQuery, True)
        self.bot = Bot('100:FSM_FIXTURE', session=self.session)
        self.dp = self.app()

    async def asyncTearDown(self):
        await self.dp.fsm.close(); await self.bot.session.close(); self.folder.cleanup()

    def response(self, method):
        reply = Message.model_validate({'message_id': 1000 + len(self.sent), 'date': 1,
            'chat': {'id': method.chat_id, 'type': 'private'}, 'text': method.text,
            'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'}})
        self.sent.append((method, reply)); return reply

    async def submit(self, submission):
        self.assertIsInstance(self.session.calls[-1], AnswerCallbackQuery)
        self.received.append(submission)
        if self.fail: raise TimeoutError('unknown')
        return 'Сохранено.'

    def app(self, kind='text', version=1, lifetime=True, storage=None, fields=None):
        self.kind = kind; self.data_key = '__telegram_patterns_form' if kind == 'text' else '__telegram_patterns_dialog'
        store = ProjectSnapshotStore(self.database); store.initialize()
        dp = Dispatcher(storage=storage or SnapshotFSMStorage(store), events_isolation=SimpleEventIsolation())
        factory = text_form_router if kind == 'text' else dialog_form_router
        dp.include_router(factory(fields or [TextField('one', 'Первый', 'Первый?'), TextField('two', 'Второй', 'Второй?')],
            self.submit, name='case', command='apply', schema_version=version,
            lifetime=DialogLifetime(60, lambda: self.now) if lifetime else None))
        return dp

    def context(self): return self.dp.fsm.get_context(bot=self.bot, chat_id=42, user_id=42)
    async def data(self): return (await self.context().get_data())[self.data_key]

    async def send(self, text):
        self.index += 1
        message = {'message_id': self.index, 'date': 1, 'chat': {'id': 42, 'type': 'private'},
            'from': {'id': 42, 'is_bot': False, 'first_name': 'Owner'}, 'text': text}
        if self.kind != 'text' and self.sent: message['reply_to_message'] = self.sent[-1][1].model_dump(mode='json', by_alias=True)
        await self.dp.feed_update(self.bot, Update.model_validate({'update_id': self.index, 'message': message}))

    def button(self):
        method, message = self.sent[-1]
        return message, method.reply_markup.inline_keyboard[0][0].callback_data

    async def click(self, chosen):
        self.index += 1; message, data = chosen
        await self.dp.feed_update(self.bot, Update.model_validate({'update_id': self.index, 'callback_query': {
            'id': str(self.index), 'chat_instance': 'fixture', 'from': {'id': 42, 'is_bot': False, 'first_name': 'Owner'},
            'message': message.model_dump(mode='json', by_alias=True), 'data': data}}))

    async def restart(self, **kwargs):
        await self.dp.fsm.close(); self.dp = self.app(**kwargs)

    async def test_text_restart_resumes_answers_identity_version_and_original_deadline(self):
        await self.context().update_data(host={'locale': 'ru'})
        await self.send('/apply'); await self.send('accepted'); before = await self.data()
        await self.restart(); self.now = 120; await self.send('/apply')
        after = await self.data()
        for key in ('values', 'operation_id', 'index', 'form_version', 'lifetime'): self.assertEqual(after[key], before[key])
        self.assertEqual(after['lifetime']['expires_at'], 160)
        await self.send('done'); await self.click(self.button())
        self.assertIsNone(await self.context().get_state())
        self.assertEqual(await self.context().get_data(), {'host': {'locale': 'ru'}})

    async def test_mixed_restart_resumes_current_reply_step(self):
        await self.restart(kind='mixed')
        await self.send('/apply'); await self.send('first'); before = await self.data()
        await self.restart(kind='mixed'); await self.send('/apply')
        self.assertEqual((await self.data())['values'], {'one': 'first'})
        self.assertEqual((await self.data())['operation_id'], before['operation_id'])
        await self.send('second'); await self.click(self.button())
        self.assertEqual(self.received[0].as_dict(), {'one': 'first', 'two': 'second'})

    async def test_expired_draft_clears_only_owned_form(self):
        await self.context().update_data(host='preserved'); await self.send('/apply'); await self.send('first')
        self.now = 160; await self.send('too late')
        self.assertIsNone(await self.context().get_state()); self.assertEqual(await self.context().get_data(), {'host': 'preserved'})
        self.assertFalse(self.received)
        self.assertTrue(any('истёк' in call.text for call, _ in self.sent))

    async def test_restart_and_back_do_not_extend_draft_lifetime(self):
        await self.send('/apply'); before = await self.data(); self.now = 140
        await self.send('one'); await self.send('/back'); await self.send('/apply')
        self.assertEqual((await self.data())['lifetime'], before['lifetime'])
        old = (await self.data())['operation_id']; self.now = 200; await self.send('/apply')
        self.assertNotEqual((await self.data())['operation_id'], old)
        self.assertEqual((await self.data())['lifetime']['expires_at'], 260)

    async def test_unknown_submission_survives_restart_and_expiry_with_same_id(self):
        await self.send('/apply'); await self.send('one'); await self.send('two'); chosen = self.button(); self.fail = True
        with self.assertRaises(TimeoutError): await self.click(chosen)
        pending = await self.data(); await self.restart(); self.now = 1000
        for command in ('/apply', '/cancel', '/back'): await self.send(command)
        self.assertEqual(await self.data(), pending)
        self.fail = False; await self.click(chosen); await self.click(chosen)
        self.assertEqual([s.operation_id for s in self.received], [pending['operation_id']] * 2)
        self.assertIsNone(await self.context().get_state())

    async def test_version_change_requires_explicit_migration_without_erasure(self):
        await self.send('/apply'); await self.send('accepted'); before = await self.dp.fsm.storage.read_snapshot(KEY)
        await self.restart(version=2); self.now = 200
        with self.assertRaisesRegex(RuntimeError, 'migration'): await self.send('/apply')
        self.assertEqual(await self.dp.fsm.storage.read_snapshot(KEY), before)

    async def test_atomic_start_failure_sends_no_prompt_or_partial_state(self):
        async def fail(*args): raise OSError('disk failure')
        self.dp.fsm.storage.store.compare_and_set = fail
        with self.assertRaises(OSError): await self.send('/apply')
        self.assertEqual(await self.dp.fsm.storage.read_snapshot(KEY), FSMSnapshot(None, {}, 0))
        self.assertFalse(self.sent)

    async def test_lost_prompt_recovers_committed_step_without_reset(self):
        def fail(method): raise TimeoutError('lost prompt')
        self.session.respond(SendMessage, fail)
        with self.assertRaises(TimeoutError): await self.send('/apply')
        before = await self.data(); self.session.respond(SendMessage, self.response)
        await self.restart(); await self.send('/apply')
        self.assertEqual((await self.data())['operation_id'], before['operation_id'])
        self.assertEqual((await self.data())['lifetime'], before['lifetime'])

    async def test_lifetime_requires_atomic_existing_storage_before_writes(self):
        await self.restart(storage=MemoryStorage())
        with self.assertRaisesRegex(RuntimeError, 'AtomicFSMStorage'): await self.send('/apply')
        self.assertIsNone(await self.context().get_state()); self.assertEqual(await self.context().get_data(), {})

    async def test_corrupt_lifetime_is_not_ignored_or_reset(self):
        await self.send('/apply'); values = await self.context().get_data()
        values[self.data_key]['lifetime']['expires_at'] = False
        await self.context().set_data(values); before = await self.dp.fsm.storage.read_snapshot(KEY)
        with self.assertRaisesRegex(RuntimeError, 'migration'): await self.send('/apply')
        self.assertEqual(await self.dp.fsm.storage.read_snapshot(KEY), before)

    async def test_atomic_storage_also_preserves_legacy_memory_demo_api(self):
        await self.restart(lifetime=False, storage=MemoryStorage())
        await self.send('/apply'); await self.send('first'); await self.send('/apply')
        self.assertEqual((await self.data())['index'], 0)  # Original reset behavior.

    async def test_pending_marker_commit_failure_acks_but_does_not_call_service(self):
        await self.send('/apply'); await self.send('one'); await self.send('two'); chosen = self.button()
        before = await self.dp.fsm.storage.read_snapshot(KEY)
        async def fail(*args): raise FSMConflict('stale')
        self.dp.fsm.storage.store.compare_and_set = fail
        with self.assertRaises(FSMConflict): await self.click(chosen)
        self.assertIsInstance(self.session.calls[-1], AnswerCallbackQuery)
        self.assertFalse(self.received); self.assertEqual(await self.dp.fsm.storage.read_snapshot(KEY), before)

    async def test_mixed_pending_survives_expiry_and_version_refusal(self):
        await self.restart(kind='mixed'); await self.send('/apply'); await self.send('one'); await self.send('two')
        chosen = self.button(); self.fail = True
        with self.assertRaises(TimeoutError): await self.click(chosen)
        old = await self.dp.fsm.storage.read_snapshot(KEY)
        await self.restart(kind='mixed', version=2); self.now = 1000
        with self.assertRaises(RuntimeError): await self.send('/apply')
        self.assertEqual(await self.dp.fsm.storage.read_snapshot(KEY), old)
        await self.restart(kind='mixed'); await self.send('/cancel')
        self.assertEqual(await self.dp.fsm.storage.read_snapshot(KEY), old)
        self.fail = False; await self.click(chosen)
        self.assertEqual(self.received[-1].operation_id, self.received[0].operation_id)

    async def test_native_candidate_is_restored_before_confirmation(self):
        fields = [ContactField('contact', 'Контакт', 'Контакт?')]
        await self.restart(kind='mixed', fields=fields); await self.send('/apply'); self.index += 1
        await self.dp.feed_update(self.bot, Update.model_validate({'update_id': self.index, 'message': {
            'message_id': self.index, 'date': 1, 'chat': {'id': 42, 'type': 'private'},
            'from': {'id': 42, 'is_bot': False, 'first_name': 'Owner'},
            'contact': {'user_id': 42, 'phone_number': '+48123456789', 'first_name': 'Owner'}}}))
        chosen = self.button(); before = await self.data()
        self.assertEqual(before['index'], 0); self.assertIsNotNone(before['candidate'])
        await self.restart(kind='mixed', fields=fields)
        self.assertEqual(await self.data(), before)
        await self.click(chosen); self.assertEqual((await self.data())['index'], 1)
        await self.click(self.button()); self.assertEqual(self.received[0].as_dict()['contact']['user_id'], 42)

    async def test_orphan_form_record_requires_reconciliation(self):
        await self.context().set_data({self.data_key: {'operation_id': 'preserve-me'}})
        old = await self.dp.fsm.storage.read_snapshot(KEY)
        with self.assertRaisesRegex(RuntimeError, 'Orphan'): await self.send('/apply')
        self.assertEqual(await self.dp.fsm.storage.read_snapshot(KEY), old)

    async def test_topic_callback_cannot_reuse_an_ordinary_private_form(self):
        await self.send('/apply'); await self.send('one'); await self.send('two')
        message, callback = self.button(); before = await self.dp.fsm.storage.read_snapshot(KEY)
        await self.click((message.model_copy(update={'message_thread_id': 7, 'is_topic_message': True}), callback))
        self.assertIsInstance(self.session.calls[-1], AnswerCallbackQuery)
        self.assertFalse(self.received); self.assertEqual(await self.dp.fsm.storage.read_snapshot(KEY), before)
