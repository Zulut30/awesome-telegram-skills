"""Behavioral SDK fixtures on file SQLite; native moderation is never live."""
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import threading
import unittest

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, AnswerChatJoinRequestQuery, CreateForumTopic, GetChat, GetChatMember, RestrictChatMember
from aiogram.types import CallbackQuery, Chat, ChatMemberMember, Message, Update, User

from telegram_group_example.bot import Application
from telegram_group_example.offline import BASE, BOT_USER, CHAT, OTHER, OWNER, TARGET, Fixture, administrator
from telegram_group_example.storage import connection, io_call


class GroupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='group example unit ')
        self.database = Path(self.temp.name)/'group.sqlite'
        self.f = Fixture(self.database)

    async def asyncTearDown(self):
        await self.f.close()
        self.temp.cleanup()

    async def preview(self):
        await self.f.command('/topic_create <b>Plain topic</b>')
        return self.f.operation('topic_create')

    async def test_bot_and_actor_missing_rights_explain_without_preview_or_effect(self):
        for user in (BOT_USER,OWNER):
            self.f.members[(CHAT,user.id)] = administrator(user,can_manage_topics=False)
            await self.f.command('/topic_create Permission denied')
            self.assertIn('can_manage_topics',self.f.sent[-1][0].text)
            self.assertFalse(self.f.effects())
            with connection(self.database) as db: self.assertEqual(db.execute('SELECT count(*) FROM group_operations').fetchone()[0],0)
            self.f.members[(CHAT,user.id)] = administrator(user)
        # A failed membership read also denies, rather than inventing permissions.
        def failed(method): raise TimeoutError('PRIVATE_CANARY')
        self.f.session.respond(GetChatMember,failed)
        await self.f.command('/topic_create Timeout')
        self.assertIn('Не удалось проверить',self.f.sent[-1][0].text)
        self.assertNotIn('PRIVATE_CANARY',self.f.sent[-1][0].text)
        self.assertFalse(self.f.effects())

    async def test_community_is_read_only_and_grants_no_rights(self):
        await self.f.command('/community')
        self.assertEqual(self.f.sent[-1][0].text,'Группа не входит в сообщество.')
        self.f.communities[CHAT] = {'id':2**51+7,'name':'Город'}
        await self.f.command('/community')
        self.assertIn('«Город» (2251799813685255)',self.f.sent[-1][0].text)
        self.assertEqual(self.f.sent[-1][0].message_thread_id,10)
        # Rights stay per chat: a member of the same community without rights still gets no preview.
        self.f.communities[OTHER] = self.f.communities[CHAT]
        self.f.members[(OTHER,OWNER.id)] = ChatMemberMember(user=OWNER)
        await self.f.command('/topic_create Not here',chat=OTHER)
        self.assertIn('нет прав администратора',self.f.sent[-1][0].text)
        def failed(method): raise TimeoutError('PRIVATE_CANARY')
        self.f.session.respond(GetChat,failed)
        await self.f.command('/community')
        self.assertIn('Не удалось прочитать сообщество',self.f.sent[-1][0].text)
        self.assertNotIn('PRIVATE_CANARY',self.f.sent[-1][0].text)
        self.assertFalse(self.f.effects())
        with connection(self.database) as db: self.assertEqual(db.execute('SELECT count(*) FROM group_operations').fetchone()[0],0)

    async def test_revocation_between_preview_and_confirmation_and_replay(self):
        op = await self.preview()
        self.f.members[(CHAT,OWNER.id)] = administrator(OWNER,can_manage_topics=False)
        await self.f.callback(op)
        self.assertFalse(self.f.effects())
        self.assertEqual(self.f.operation('topic_create')['status'],'ready')
        self.f.members[(CHAT,OWNER.id)] = administrator(OWNER)
        await self.f.callback(op)
        self.assertEqual(len(self.f.effects()),1)
        self.f.members[(CHAT,BOT_USER.id)] = ChatMemberMember(user=BOT_USER)
        await self.f.callback(op)
        self.assertEqual(len(self.f.effects()),1)
        self.assertIn('У бота нет прав администратора',self.f.sent[-1][0].text)

    async def test_callback_ack_and_actor_group_topic_message_binding(self):
        op = await self.preview()
        for changes in ({'user':TARGET},{'chat':OTHER},{'thread':20},{'prompt':op['prompt']+1}):
            start = len(self.f.session.calls)
            await self.f.callback(op,**changes)
            self.assertIsInstance(self.f.session.calls[start],AnswerCallbackQuery)
            self.assertFalse(self.f.effects())
        await self.f.callback(op)
        self.assertEqual(len(self.f.effects()),1)
        self.assertEqual(self.f.effects()[0].name,'<b>Plain topic</b>')
        self.assertIsNone(self.f.sent[0][0].parse_mode)

    async def test_unconfigured_anonymous_business_bot_and_inaccessible_callback(self):
        await self.f.command('/topic_create Ignore',chat=-100000000001)
        self.assertFalse(self.f.session.calls)
        await self.f.command('/topic_create Anonymous',sender_chat=Chat(id=CHAT,type='supergroup'))
        await self.f.command('/topic_create Bot',user=BOT_USER)
        await self.f.command('/topic_create Business',business='fixture')
        with connection(self.database) as db: self.assertEqual(db.execute('SELECT count(*) FROM group_operations').fetchone()[0],0)
        query = CallbackQuery(id='no-message',from_user=OWNER,chat_instance='fixture',inline_message_id='fixture',data='grp:confirm_'+'a'*16)
        await self.f.app.dispatcher.feed_update(self.f.bot,Update(update_id=100,callback_query=query))
        self.assertIsInstance(self.f.session.calls[-1],AnswerCallbackQuery)
        self.assertFalse(self.f.effects())

    async def test_two_topic_operations_and_general_refusal(self):
        await self.f.command('/topic_close',thread=1)
        self.assertIn('General',self.f.sent[-1][0].text)
        self.assertFalse(self.f.effects())
        for action,thread in (('topic_close',10),('topic_reopen',20)):
            await self.f.command('/'+action,thread=thread)
            await self.f.callback(self.f.operation(action))
            self.assertEqual(self.f.effects()[-1].message_thread_id,thread)
            self.assertEqual(self.f.effects()[-1].chat_id,CHAT)
        self.assertEqual(len(self.f.effects()),2)

    async def test_join_query_queues_once_then_owner_approves_observed_request(self):
        await self.f.join(query='assigned-fixture',update_id=50)
        await self.f.join(query='assigned-fixture',update_id=50)
        queued = [c for c in self.f.session.calls if isinstance(c,AnswerChatJoinRequestQuery)]
        self.assertEqual(len(queued),1)
        self.assertEqual(queued[0].result,'queue')
        await self.f.command('/joins')
        self.assertIn(str(TARGET.id),self.f.sent[-1][0].text)
        await self.f.command('/approve '+str(TARGET.id))
        op = self.f.operation('approve')
        await self.f.callback(op)
        await self.f.callback(op)
        self.assertEqual(len(self.f.effects()),1)
        self.assertEqual(self.f.effects()[0].user_id,TARGET.id)
        self.assertFalse(self.f.app.store.pending(self.f.app.context(self.f.sent[-1][1],self.f.bot,actor_id=OWNER.id)))
        with connection(self.database) as db:
            stored = '\n'.join(str(tuple(r)) for r in db.execute('SELECT * FROM group_joins'))
            self.assertNotIn('PRIVATE_FIXTURE_BIO',stored)
            self.assertNotIn('assigned-fixture',stored)
            self.assertNotIn('987654',stored)

    async def test_new_join_version_and_other_chat_cannot_reuse_old_confirmation(self):
        await self.f.join()
        await self.f.command('/decline '+str(TARGET.id))
        old = self.f.operation('decline')
        await self.f.join(stamp=1)
        await self.f.callback(old)
        self.assertFalse(self.f.effects())
        self.assertEqual(self.f.operation('decline')['status'],'stale')
        await self.f.join(chat=OTHER)
        await self.f.command('/decline '+str(TARGET.id),chat=OTHER)
        await self.f.callback(self.f.operation('decline',chat=OTHER))
        self.assertEqual(self.f.effects()[0].chat_id,OTHER)
        with connection(self.database) as db: self.assertEqual(db.execute('SELECT state FROM group_joins WHERE chat=?', (CHAT,)).fetchone()[0],'pending')

    async def test_failed_query_has_no_pending_approval_and_no_automatic_retry(self):
        def failed(method): raise TimeoutError('PRIVATE_CANARY')
        self.f.session.respond(AnswerChatJoinRequestQuery,failed)
        await self.f.join(query='unknown-fixture',update_id=50)
        await self.f.join(query='unknown-fixture',update_id=50)
        await self.f.command('/approve '+str(TARGET.id))
        self.assertIn('Нет свежей',self.f.sent[-1][0].text)
        self.assertEqual(len([c for c in self.f.session.calls if isinstance(c,AnswerChatJoinRequestQuery)]),1)
        self.assertFalse(self.f.effects())
        with connection(self.database) as db: self.assertEqual(db.execute('SELECT state FROM group_joins').fetchone()[0],'unknown')

    async def test_moderation_rechecks_target_and_has_bounded_ten_minute_permissions(self):
        reply = Message(message_id=2,date=BASE,chat=Chat(id=CHAT,type='supergroup',is_forum=True),from_user=TARGET,message_thread_id=10,is_topic_message=True,text='fixture')
        await self.f.command('/mute',reply=reply)
        op = self.f.operation('mute')
        self.f.members[(CHAT,TARGET.id)] = administrator(TARGET)
        await self.f.callback(op)
        self.assertFalse(self.f.effects())
        self.assertIn('не ограничивает',self.f.sent[-1][0].text)
        self.f.members[(CHAT,TARGET.id)] = ChatMemberMember(user=TARGET)
        await self.f.callback(op)
        effect = self.f.effects()[0]
        self.assertIsInstance(effect,RestrictChatMember)
        self.assertEqual(effect.until_date,int(self.f.now)+600)
        self.assertTrue(effect.use_independent_chat_permissions)
        self.assertTrue(all(v is False for v in effect.permissions.model_dump().values()))
        await self.f.callback(op); self.assertEqual(len(self.f.effects()),1)

    async def test_explicit_api_rejection_and_unknown_transport_are_not_resent(self):
        def rejected(method): raise TelegramBadRequest(method=method,message='PRIVATE_CANARY')
        self.f.session.respond(CreateForumTopic,rejected)
        op = await self.preview(); await self.f.callback(op); await self.f.callback(op)
        self.assertEqual(self.f.operation('topic_create')['status'],'rejected')
        self.assertEqual(len(self.f.effects()),1)
        def unknown(method): raise TimeoutError('PRIVATE_CANARY')
        self.f.session.respond(CreateForumTopic,unknown)
        op = await self.preview(); await self.f.callback(op); await self.f.callback(op)
        self.assertEqual(self.f.operation('topic_create')['status'],'unknown')
        self.assertEqual(len(self.f.effects()),2)
        self.assertNotIn('PRIVATE_CANARY','\n'.join(m.text for m,_ in self.f.sent))

    async def test_cancel_expiry_and_concurrent_confirm_produce_no_extra_effect(self):
        op = await self.preview(); await self.f.callback(op,cancel=True); await self.f.callback(op)
        self.assertFalse(self.f.effects())
        op = await self.preview(); self.f.now += 301; await self.f.callback(op)
        self.assertEqual(self.f.operation('topic_create')['status'],'stale')
        self.assertFalse(self.f.effects())
        op = await self.preview()
        await asyncio.gather(self.f.callback(op),self.f.callback(op))
        self.assertEqual(len(self.f.effects()),1)

    async def test_membership_and_migration_invalidate_context_without_implicit_redirect(self):
        op = await self.preview()
        await self.f.membership()
        self.f.members[(CHAT,OWNER.id)] = administrator(OWNER)
        await self.f.callback(op)
        self.assertEqual(self.f.operation('topic_create')['status'],'stale')
        await self.f.join()
        await self.f.membership(TARGET,stamp=2)
        await self.f.command('/approve '+str(TARGET.id))
        self.assertIn('Нет свежей',self.f.sent[-1][0].text)
        op = await self.preview()
        migration = Message(message_id=999,date=BASE,chat=Chat(id=CHAT,type='supergroup'),migrate_to_chat_id=-1002222222222)
        await self.f.app.dispatcher.feed_update(self.f.bot,Update(update_id=999,message=migration))
        await self.f.callback(op)
        self.assertFalse(self.f.effects())
        self.assertFalse(self.f.app.store.configured(CHAT))
        self.assertFalse(self.f.app.store.configured(-1002222222222))
        self.assertTrue(self.f.app.store.configured(OTHER))
        with connection(self.database) as db: self.assertEqual(db.execute('SELECT new_chat FROM group_migrations').fetchone()[0],-1002222222222)

    async def test_restart_preserves_ready_and_discards_orphan_preview(self):
        op = await self.preview()
        context = self.f.app.context(self.f.sent[-1][1],self.f.bot,actor_id=OWNER.id)
        orphan,_ = self.f.app.store.prepare(context,999,'topic_close',{})
        await self.f.close()
        self.f = Fixture(self.database,start=100)
        self.assertEqual(self.f.operation('topic_create')['status'],'ready')
        self.assertEqual(self.f.operation('topic_close')['status'],'stale')
        await self.f.callback(op)
        self.assertEqual(len(self.f.effects()),1)
        # Another bot cannot interpret this database or its previous approvals.
        await self.f.close()
        with self.assertRaisesRegex(ValueError,'another bot'): Application(self.database,200,{CHAT})
        self.f = Fixture(self.database,start=200)

    async def test_command_replay_uses_chat_message_id_even_when_update_id_resets(self):
        await self.f.command('/topic_create First',update_id=500,message_id=800)
        first = self.f.operation('topic_create')
        sent = len(self.f.sent)
        await self.f.command('/topic_create First',update_id=501,message_id=800)
        self.assertEqual(self.f.operation('topic_create')['key'],first['key'])
        self.assertEqual(len(self.f.sent),sent+1)  # Informational response, no new confirmation.
        await self.f.command('/topic_create Second',update_id=500,message_id=801)
        self.assertNotEqual(self.f.operation('topic_create')['key'],first['key'])
        self.assertFalse(self.f.effects())

    async def test_cancelled_sqlite_work_is_joined_before_owner_unwinds(self):
        started,release,finished = threading.Event(),threading.Event(),threading.Event()
        def owned_write():
            started.set(); release.wait(3)
            with connection(self.database,write=True) as db: db.execute("UPDATE group_meta SET version=1")
            finished.set()
        task = asyncio.create_task(io_call(owned_write))
        await asyncio.to_thread(started.wait,2)
        task.cancel(); await asyncio.sleep(0)
        self.assertFalse(task.done())
        task.cancel(); release.set()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(finished.is_set())

    async def test_receipt_storage_failure_retains_sending_then_recovers_without_resend(self):
        op = await self.preview()
        with connection(self.database,write=True) as db:
            db.execute("CREATE TRIGGER fail_receipt BEFORE UPDATE OF result ON group_operations BEGIN SELECT RAISE(ABORT,'PRIVATE_CANARY'); END")
        await self.f.callback(op)
        self.assertEqual(len(self.f.effects()),1)
        self.assertEqual(self.f.operation('topic_create')['status'],'sending')
        self.assertIn('не удалось сохранить',self.f.sent[-1][0].text)
        self.assertNotIn('PRIVATE_CANARY',self.f.sent[-1][0].text)
        await self.f.callback(op); self.assertEqual(len(self.f.effects()),1)
        with connection(self.database,write=True) as db: db.execute('DROP TRIGGER fail_receipt')
        await self.f.close(); self.f = Fixture(self.database,start=200)
        self.assertEqual(self.f.operation('topic_create')['status'],'unknown')
        await self.f.callback(op); self.assertFalse(self.f.effects())

    async def test_cancellation_after_dispatch_and_interrupted_queue_require_reconciliation(self):
        started = asyncio.Event()
        async def uncertain(method):
            started.set(); await asyncio.Event().wait()
        self.f.session.respond(CreateForumTopic,uncertain)
        op = await self.preview()
        task = asyncio.create_task(self.f.callback(op)); await started.wait(); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(self.f.operation('topic_create')['status'],'unknown')
        await self.f.callback(op); self.assertEqual(len(self.f.effects()),1)
        # A process interrupted before queue confirmation must not manufacture pending.
        self.f.app.store.observe_join(CHAT,TARGET.id,int(self.f.now),500,query=True)
        await self.f.close(); self.f = Fixture(self.database,start=600)
        with connection(self.database) as db: self.assertEqual(db.execute('SELECT state FROM group_joins').fetchone()[0],'unknown')
        await self.f.join(query='fixture',update_id=500)
        self.assertFalse([c for c in self.f.session.calls if isinstance(c,AnswerChatJoinRequestQuery)])
        await self.f.command('/approve '+str(TARGET.id)); self.assertFalse(self.f.effects())

    async def test_urgent_query_bypasses_moderation_lock_and_stale_query_is_not_sent(self):
        async with self.f.app.chat_lock(CHAT):
            await asyncio.wait_for(self.f.join(query='urgent-fixture'),timeout=2)
        queued = [c for c in self.f.session.calls if isinstance(c,AnswerChatJoinRequestQuery)]
        self.assertEqual(len(queued),1)
        await self.f.join(query='too-late-fixture',chat=OTHER,stamp=-11)
        self.assertEqual(len([c for c in self.f.session.calls if isinstance(c,AnswerChatJoinRequestQuery)]),1)
        with connection(self.database) as db: self.assertEqual(db.execute('SELECT state FROM group_joins WHERE chat=?', (OTHER,)).fetchone()[0],'unknown')
        self.assertFalse(self.f.effects())

    async def test_shutdown_joins_inflight_update_before_releasing_database_lock(self):
        started = asyncio.Event()
        async def uncertain(method):
            started.set(); await asyncio.Event().wait()
        self.f.session.respond(CreateForumTopic,uncertain)
        op = await self.preview()
        task = asyncio.create_task(self.f.callback(op)); await started.wait()
        self.assertIn(task,self.f.app.inflight)
        await self.f.app.close()
        self.assertTrue(task.done())
        self.assertTrue(task.cancelled())
        self.assertFalse(self.f.app.inflight)
        self.assertTrue(self.f.app.lock.file.closed)
        with connection(self.database) as db: self.assertEqual(db.execute('SELECT status FROM group_operations WHERE key=?', (op['key'],)).fetchone()[0],'unknown')
        await self.f.close()
        self.f = Fixture(self.database,start=200)
        await self.f.callback(op)
        self.assertFalse(self.f.effects())


if __name__=='__main__': unittest.main()
