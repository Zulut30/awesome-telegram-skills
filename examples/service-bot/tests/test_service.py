import asyncio
import contextlib
import io
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import SendMessage
from aiogram.types import Message, Chat
from telegram_patterns import PermissionDenied
from telegram_patterns.testing import StubSession
from telegram_service_example.bot import Application, main
from telegram_service_example.offline import BASE, guards
from telegram_service_example.service import Actor, Service, SlotUnavailable
from telegram_service_example.storage import SQLiteFSM, connection


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='service-domain-')
        self.database=Path(self.temp.name)/'service.sqlite'
        self.clock=[BASE.timestamp()]
        self.service=Service(self.database,100,now=lambda:self.clock[0])
        self.actor=Actor(100,42,42)

    def tearDown(self):self.temp.cleanup()

    def create(self, actor=None, key='a'*16, slot='slot-1'):
        return self.service.create(actor or self.actor,key,slot,'Учебная задача')

    async def test_concurrent_slot_and_replay_use_one_effect_with_owner_scope(self):
        def reserve(actor):
            try:return self.create(actor)
            except SlotUnavailable:return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(reserve,[self.actor,Actor(100,77,77)]))
        self.assertEqual(sum(r is not None for r in results),1)
        with connection(self.database) as db:
            row=db.execute('SELECT actor_id,id FROM service_bookings').fetchone()
            self.assertEqual(db.execute('SELECT count(*) FROM service_notifications').fetchone()[0],1)
        owner=Actor(100,row['actor_id'],row['actor_id'])
        self.service=Service(self.database,100,now=lambda:self.clock[0])
        self.assertTrue(self.create(owner)['replayed'])
        for foreign in (Actor(101,owner.user_id,owner.user_id),Actor(100,owner.user_id,1)):
            with self.assertRaises(PermissionDenied):self.create(foreign)
        with self.assertRaises(PermissionDenied):self.service.cancel(Actor(100,88,88),row['id'])
        self.service.cancel(owner,row['id'])
        self.assertEqual(self.create(owner)['status'],'cancelled')

    async def test_consent_cancel_and_expiry_prevent_delivery(self):
        booking=self.create();self.clock[0]+=2800
        self.assertIsNone(self.service.claim())
        self.service.reminders(self.actor,True);self.service.reminders(self.actor,False)
        self.assertIsNone(self.service.claim())
        self.service.reminders(self.actor,True)
        self.service.cancel(self.actor,booking['id']);self.assertIsNone(self.service.claim())
        self.create(key='b'*16,slot='slot-2');self.clock[0]+=8000
        self.assertIsNone(self.service.claim())
        with connection(self.database) as db:
            self.assertEqual({r[0] for r in db.execute('SELECT status FROM service_notifications')},{'skipped'})

    async def test_unknown_transport_and_cancel_preserve_identity_without_retry(self):
        self.create();self.service.reminders(self.actor,True);self.clock[0]+=2800
        def unknown(method):raise TimeoutError('PRIVATE_CANARY')
        session=StubSession().respond(SendMessage,unknown)
        async with Bot('100:TEST',session=session) as bot:
            self.assertEqual(await self.service.deliver_one(bot),'unknown')
            self.assertEqual(await self.service.deliver_one(bot),'idle')
        with connection(self.database) as db:
            self.assertEqual(tuple(db.execute('SELECT status,attempts FROM service_notifications').fetchone()),('unknown',1))
        self.create(key='b'*16,slot='slot-2');self.clock[0]+=3600
        def cancel(method):raise asyncio.CancelledError()
        session=StubSession().respond(SendMessage,cancel)
        async with Bot('100:TEST',session=session) as bot:
            with self.assertRaises(asyncio.CancelledError):await self.service.deliver_one(bot)
        with connection(self.database) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM service_notifications WHERE status='unknown'").fetchone()[0],2)

    async def test_definite_rejections_backoff_are_bounded_and_forbidden_stops_actor(self):
        self.create();self.service.reminders(self.actor,True);self.clock[0]+=2800
        def flood(method):raise TelegramRetryAfter(method=method,message='fixture',retry_after=10)
        session=StubSession().respond(SendMessage,flood)
        async with Bot('100:TEST',session=session) as bot:
            for index in range(3):
                self.assertEqual(await self.service.deliver_one(bot),'pending' if index<2 else 'failed')
                self.assertEqual(await self.service.deliver_one(bot),'idle');self.clock[0]+=10
        self.create(key='b'*16,slot='slot-2');self.clock[0]+=3600
        def blocked(method):raise TelegramForbiddenError(method=method,message='fixture')
        session=StubSession().respond(SendMessage,blocked)
        async with Bot('100:TEST',session=session) as bot:
            self.assertEqual(await self.service.deliver_one(bot),'blocked')
            self.assertEqual(await self.service.deliver_one(bot),'idle')
        with connection(self.database) as db:
            self.assertEqual(db.execute('SELECT enabled FROM service_preferences').fetchone()[0],0)

    async def test_fsm_scope_detached_data_restart_and_schema_corruption(self):
        key=StorageKey(bot_id=100,chat_id=42,user_id=42)
        old=SQLiteFSM(self.database);await old.set_state(key,'dialog');await old.set_data(key,{'operation':'a'*16})
        await old.close();new=SQLiteFSM(self.database)
        self.assertEqual(await new.get_state(key),'dialog')
        value=await new.get_data(key);value.clear()
        self.assertEqual(await new.get_data(key),{'operation':'a'*16})
        self.assertEqual(await new.get_data(StorageKey(bot_id=101,chat_id=42,user_id=42)),{})
        with connection(self.database,write=True) as db:db.execute('UPDATE service_fsm SET data=?',('[]',))
        with self.assertRaises(ValueError):await new.get_data(key)
        await new.close()
        with connection(self.database,write=True) as db:db.execute('UPDATE service_schema SET version=99')
        with self.assertRaises(ValueError):Service(self.database,100)

    async def test_reminder_recipient_must_match_booking_owner(self):
        self.create();self.service.reminders(self.actor,True)
        self.service.reminders(Actor(100,77,77),True);self.clock[0]+=2800
        with connection(self.database,write=True) as db:db.execute('UPDATE service_notifications SET actor_id=77')
        session=StubSession()
        async with Bot('100:TEST',session=session) as bot:
            self.assertEqual(await self.service.deliver_one(bot),'idle')
        self.assertFalse(session.calls)

    async def test_shutdown_joins_sqlite_claim_before_releasing_process_lock(self):
        self.create();self.service.reminders(self.actor,True);self.clock[0]+=2800
        app=Application(self.database,100,now=lambda:self.clock[0])
        entered,release=threading.Event(),threading.Event()
        original=app.service.claim
        def blocked_claim():
            entered.set()
            if not release.wait(5):raise RuntimeError('Fixture did not release SQLite worker')
            return original()
        app.service.claim=blocked_claim
        session=StubSession()
        async with Bot('100:TEST',session=session) as bot:
            await app.dispatcher.emit_startup(bot=bot)
            closing=None
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait,2))
                closing=asyncio.create_task(app.close())
                await asyncio.sleep(0.02)
                self.assertFalse(closing.done())
                self.assertFalse(app.lock.file.closed)
                app.task.cancel()  # Repeated cancellation must not detach its writer.
                await asyncio.sleep(0.02)
                self.assertFalse(closing.done())
            finally:
                release.set()
                if closing is not None:await asyncio.wait_for(closing,3)
                else:await app.close()
        self.assertTrue(app.lock.file.closed)
        self.assertFalse(session.calls)
        with connection(self.database) as db:
            self.assertEqual(db.execute('SELECT status FROM service_notifications').fetchone()[0],'sending')
        newer=Application(self.database,100,now=lambda:self.clock[0])
        self.assertEqual(newer.recovered_notifications,1)
        with connection(self.database) as db:
            self.assertEqual(db.execute('SELECT status FROM service_notifications').fetchone()[0],'unknown')
        await newer.close()

    async def test_runtime_owns_worker_fsm_and_process_lock_without_polling(self):
        app=Application(self.database,100,now=lambda:self.clock[0])
        session=StubSession()
        async with Bot('100:TEST',session=session) as bot:
            await app.dispatcher.emit_startup(bot=bot)
            self.assertIsNotNone(app.task)
            await app.dispatcher.emit_shutdown()
        await app.close()
        self.assertTrue(app.storage.closed and app.lock.file.closed and session.closed)
        self.assertFalse(session.calls)
        newer=Application(self.database,100,now=lambda:self.clock[0]);await newer.close()



class EntrypointTests(unittest.TestCase):
    def test_placeholder_token_exits_with_readable_error(self):
        with tempfile.TemporaryDirectory(prefix='service-entry-') as temp:
            stderr=io.StringIO()
            argv=['telegram-service-example','--database',str(Path(temp)/'service.sqlite')]
            with mock.patch.dict(os.environ,{'BOT_TOKEN':'123456789:REPLACE_WITH_YOUR_TEST_BOT_TOKEN'}),mock.patch('sys.argv',argv),\
                    contextlib.redirect_stderr(stderr),self.assertRaises(SystemExit) as exit_info:
                main()
            self.assertEqual(exit_info.exception.code,2)
            self.assertIn('error: Replace the BOT_TOKEN placeholder',stderr.getvalue())
            self.assertNotIn('Traceback',stderr.getvalue())
            self.assertFalse((Path(temp)/'service.sqlite').exists())

if __name__=='__main__':unittest.main()
