import asyncio
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram import methods as m
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import (
    BufferedInputFile,
    InputStoryContentPhoto,
    ReactionTypeCustomEmoji,
    ReactionTypeEmoji,
    ReactionTypePaid,
    Update,
)

from telegram_patterns import ConflictFailure, PatternError, PermissionDenied, UnknownOutcome, ValidationFailure
from telegram_patterns.aiogram import (
    PlatformAction,
    PlatformPermit,
    PlatformScope,
    SecretToken,
    StoryPhotoUpload,
    StoryVideoUpload,
    execute_platform_action,
    managed_bot_link,
    platform_contracts,
    platform_event,
    platform_events_router,
)
from telegram_patterns.testing import StubSession

spec = importlib.util.spec_from_file_location(
    'platform_host_example', Path(__file__).resolve().parents[3] / 'examples/python/platform_bot.py'
)
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)

USER = {'id': 42, 'is_bot': False, 'first_name': 'User'}
BOT = {
    'id': 100,
    'is_bot': True,
    'first_name': 'Bot',
    'username': 'fixture_bot',
    'has_topics_enabled': True,
    'supports_join_request_queries': True,
    'can_manage_bots': True,
}
CHILD = {'id': 500, 'is_bot': True, 'first_name': 'Child'}
CHAT = {
    'id': -100,
    'type': 'supergroup',
    'title': 'Group',
    'is_forum': True,
    'accent_color_id': 0,
    'max_reaction_count': 1,
    'accepted_gift_types': {
        'unlimited_gifts': True,
        'limited_gifts': True,
        'unique_gifts': True,
        'premium_subscription': True,
        'gifts_from_channels': True,
    },
}
MEMBER = {'status': 'creator', 'user': BOT, 'is_anonymous': False}
RIGHTS = {
    name: True
    for name in (
        'can_reply',
        'can_read_messages',
        'can_delete_sent_messages',
        'can_delete_all_messages',
        'can_edit_name',
        'can_edit_bio',
        'can_edit_username',
        'can_edit_profile_photo',
        'can_change_gift_settings',
        'can_view_gifts_and_stars',
        'can_convert_gifts_to_stars',
        'can_transfer_and_upgrade_gifts',
        'can_transfer_stars',
        'can_manage_stories',
    )
}
CONNECTION = {
    'id': 'business-a',
    'user': USER,
    'user_chat_id': 42,
    'date': 1780000000,
    'is_enabled': True,
    'rights': RIGHTS,
}
STICKER = {
    'file_id': 'f',
    'file_unique_id': 'u',
    'type': 'custom_emoji',
    'width': 512,
    'height': 512,
    'is_animated': False,
    'is_video': False,
    'custom_emoji_id': '123',
}
GIFT = {'id': 'gift-a', 'sticker': STICKER, 'star_count': 20, 'upgrade_star_count': 5}


class PlatformTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='platform-host-')
        self.db = sqlite3.connect(Path(self.tmp.name) / 'host.sqlite3')
        self.permit = PlatformPermit(allowed=True)

        async def policy(action):
            return self.permit

        self.hooks = example.PlatformJournal(self.db, policy)
        self.db.execute('INSERT INTO platform_actors VALUES (100,42,0,1)')
        self.db.execute('INSERT INTO platform_budgets VALUES (100,42,10000)')
        self.db.commit()
        self.session = StubSession().respond(m.GetMe, BOT).respond(m.GetChatMember, MEMBER)
        self.session.respond(
            m.GetChat, lambda r: dict(CHAT, id=r.chat_id, type='private' if r.chat_id > 0 else 'supergroup')
        )
        self.session.respond(m.GetBusinessConnection, lambda r: dict(CONNECTION, id=r.business_connection_id))
        self.session.respond(m.GetForumTopicIconStickers, [STICKER]).respond(m.GetAvailableGifts, {'gifts': [GIFT]})
        self.session.respond(m.CreateForumTopic, {'message_thread_id': 17, 'name': 'Topic', 'icon_color': 7322096})
        self.session.respond(m.PostStory, {'id': 1, 'chat': {'id': 42, 'type': 'private'}})
        self.bot = Bot('100:PLATFORM_COMPOSITION_FIXTURE', session=self.session)

    async def asyncTearDown(self):
        await self.bot.session.close()
        self.db.close()
        self.tmp.cleanup()

    def scope(self, **kwargs):
        return PlatformScope(100, 42, 'action-1', **kwargs)

    def action(self, request, **scope):
        return PlatformAction(self.scope(**scope), request)

    async def run_action(self, action):
        return await execute_platform_action(self.bot, action, self.hooks)

    def effects(self, cls):
        return [r for r in self.session.calls if isinstance(r, cls)]

    def status(self):
        return self.db.execute('SELECT status FROM platform_intents').fetchone()

    async def test_forum_create_receipt_and_restart_do_not_send_again(self):
        action = self.action(m.CreateForumTopic(chat_id=-100, name='Topic', icon_custom_emoji_id='123'), chat_id=-100)
        result = await self.run_action(action)
        self.assertEqual(result.receipt.result_id, 17)
        self.assertEqual(self.status(), ('succeeded',))
        self.db.close()
        self.db = sqlite3.connect(Path(self.tmp.name) / 'host.sqlite3')

        async def policy(a):
            return self.permit

        self.hooks = example.PlatformJournal(self.db, policy)
        with self.assertRaises(ConflictFailure):
            await self.run_action(action)
        self.assertEqual(len(self.effects(m.CreateForumTopic)), 1)

    async def test_unknown_send_is_durable_and_blocks_replay(self):
        def lost(r):
            raise OSError('PRIVATE PAYLOAD TOKEN')

        self.session.respond(m.CreateForumTopic, lost)
        action = self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100)
        with self.assertRaises(UnknownOutcome) as caught:
            await self.run_action(action)
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertEqual(self.status(), ('unknown',))
        with self.assertRaises(ConflictFailure):
            await self.run_action(action)
        self.assertEqual(len(self.effects(m.CreateForumTopic)), 1)

    async def test_cancelled_send_marks_unknown_and_preserves_cancellation(self):
        entered = asyncio.Event()

        async def waiting(r):
            entered.set()
            await asyncio.Event().wait()

        self.session.respond(m.CreateForumTopic, waiting)
        action = self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100)
        task = asyncio.create_task(self.run_action(action))
        try:
            await asyncio.wait_for(entered.wait(), 3)
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.status(), ('unknown',))

    async def test_explicit_sdk_rejection_is_recorded_without_retry_or_payload(self):
        def forbidden(r):
            raise TelegramForbiddenError(r, 'PRIVATE TOKEN')

        self.session.respond(m.CreateForumTopic, forbidden)
        with self.assertRaises(PermissionDenied) as caught:
            await self.run_action(self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100))
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertEqual(self.status(), ('rejected',))

    async def test_rate_limit_is_a_retry_later_rejection_not_a_permission_problem(self):
        def flood(r):
            raise TelegramRetryAfter(r, 'Too Many Requests', retry_after=12)

        self.session.respond(m.CreateForumTopic, flood)
        with self.assertRaises(PatternError) as caught:
            await self.run_action(self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100))
        self.assertNotIsInstance(caught.exception, PermissionDenied)
        self.assertEqual(caught.exception.retry_after, 12)
        report = caught.exception.report(operation='write')
        self.assertEqual((report.code, report.outcome, report.recovery), ('rate-limited', 'rejected', 'retry-later'))
        self.assertEqual(self.status(), ('rejected',))
        self.assertEqual(len(self.effects(m.CreateForumTopic)), 1)  # no automatic retry

    async def test_timeout_before_claim_has_no_intent_or_native_write(self):
        async def slow_rights(r):
            await asyncio.Event().wait()

        self.session.respond(m.GetChat, slow_rights)
        action = self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100)
        with self.assertRaises(TimeoutError):
            await execute_platform_action(self.bot, action, self.hooks, timeout=0.03)
        self.assertIsNone(self.status())
        self.assertEqual(self.effects(m.CreateForumTopic), [])

    async def test_timeout_after_claim_stays_unknown_and_cannot_send_again(self):
        async def slow_send(r):
            await asyncio.Event().wait()

        self.session.respond(m.CreateForumTopic, slow_send)
        action = self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100)
        with self.assertRaises((TimeoutError, UnknownOutcome)):
            # Long enough for the claim and the send to start on a slow runner; the send itself never returns.
            await execute_platform_action(self.bot, action, self.hooks, timeout=0.5)
        self.assertEqual(self.status(), ('unknown',))
        with self.assertRaises(ConflictFailure):
            await self.run_action(action)
        self.assertEqual(len(self.effects(m.CreateForumTopic)), 1)

    async def test_cancellation_during_receipt_preserves_task_cancellation(self):
        entered = asyncio.Event()

        async def slow_record(a, r):
            entered.set()
            await asyncio.Event().wait()

        self.hooks.record = slow_record
        action = self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100)
        task = asyncio.create_task(self.run_action(action))
        try:
            await asyncio.wait_for(entered.wait(), 3)
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.status(), ('sending',))
        self.assertEqual(len(self.effects(m.CreateForumTopic)), 1)

    async def test_foreign_membership_cannot_authorize_topic_action(self):
        self.session.respond(m.GetChatMember, dict(MEMBER, user=CHILD))
        with self.assertRaises(PermissionDenied):
            await self.run_action(self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100))
        self.assertIsNone(self.status())
        self.assertEqual(self.effects(m.CreateForumTopic), [])

    async def test_invalid_unicode_is_local_validation_not_unknown_outcome(self):
        with self.assertRaises(ValidationFailure):
            self.action(m.CreateForumTopic(chat_id=-100, name='bad\ud800'), chat_id=-100)
        self.assertEqual(self.session.calls, [])

    async def test_decimal_story_upload_byte_limit_is_checked_before_native_io(self):
        content = StoryPhotoUpload(photo=BufferedInputFile(b'x' * 10_000_001, 'oversized.jpg'))
        with self.assertRaises(ValidationFailure):
            self.action(
                m.PostStory(business_connection_id='business-a', content=content, active_period=21600, parse_mode=None),
                business_connection_id='business-a',
                owner_id=42,
            )
        self.assertEqual(self.session.calls, [])

    async def test_reviewed_contract_catalog_matches_all_public_native_contracts(self):
        from dataclasses import asdict

        root = Path(__file__).resolve().parents[3]
        catalog = json.loads((root / 'catalog/platform-contracts.json').read_text(encoding='utf-8'))
        self.assertEqual(catalog['contracts'], [asdict(c) for c in platform_contracts()])
        self.assertEqual(len(catalog['contracts']), 51)
        self.assertEqual(catalog['verification'], 'sdk')

    async def test_confirmed_native_result_with_failed_storage_is_unknown(self):
        async def fail(a, r):
            raise sqlite3.OperationalError('PRIVATE DATABASE PATH')

        self.hooks.record = fail
        with self.assertRaises(UnknownOutcome):
            await self.run_action(self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100))
        self.assertEqual(self.status(), ('sending',))
        self.assertEqual(len(self.effects(m.CreateForumTopic)), 1)

    async def test_actor_revocation_is_checked_before_any_telegram_io(self):
        self.db.execute('UPDATE platform_actors SET enabled=0')
        self.db.commit()
        with self.assertRaises(PermissionDenied):
            await self.run_action(self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100))
        self.assertEqual(self.session.calls, [])
        self.assertIsNone(self.status())

    async def test_journal_initialization_preserves_open_host_transaction(self):
        self.db.execute('INSERT INTO platform_actors VALUES (100,99,0,1)')
        self.assertTrue(self.db.in_transaction)

        async def policy(action):
            return self.permit

        with self.assertRaises(ConflictFailure):
            example.PlatformJournal(self.db, policy)
        self.assertTrue(self.db.in_transaction)
        self.assertEqual(self.db.execute('SELECT actor_id FROM platform_actors WHERE actor_id=99').fetchone(), (99,))
        separate = sqlite3.connect(Path(self.tmp.name) / 'host.sqlite3')
        try:
            self.assertIsNone(separate.execute('SELECT actor_id FROM platform_actors WHERE actor_id=99').fetchone())
        finally:
            separate.close()

    async def test_receipt_recording_preserves_unrelated_open_host_transaction(self):
        def host_changed(request):
            self.db.execute('INSERT INTO platform_actors VALUES (100,99,0,1)')
            return {'message_thread_id': 17, 'name': 'Topic', 'icon_color': 7322096}

        self.session.respond(m.CreateForumTopic, host_changed)
        action = self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100)
        with self.assertRaises(UnknownOutcome):
            await self.run_action(action)
        self.assertTrue(self.db.in_transaction)
        self.assertEqual(self.status(), ('sending',))
        self.assertEqual(self.db.execute('SELECT actor_id FROM platform_actors WHERE actor_id=99').fetchone(), (99,))
        separate = sqlite3.connect(Path(self.tmp.name) / 'host.sqlite3')
        try:
            self.assertIsNone(separate.execute('SELECT actor_id FROM platform_actors WHERE actor_id=99').fetchone())
            self.assertEqual(separate.execute('SELECT status FROM platform_intents').fetchone(), ('sending',))
        finally:
            separate.close()
        self.assertEqual(len(self.effects(m.CreateForumTopic)), 1)

    async def test_host_revision_change_after_rights_is_checked_inside_claim(self):
        def changing(r):
            self.db.execute('UPDATE platform_actors SET revision=1')
            self.db.commit()
            return MEMBER

        self.session.respond(m.GetChatMember, changing)
        with self.assertRaises(PermissionDenied):
            await self.run_action(self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100))
        self.assertEqual(self.effects(m.CreateForumTopic), [])
        self.assertIsNone(self.status())

    async def test_wrong_bot_chat_thread_message_user_and_connection_rejected(self):
        cases = [
            lambda: self.action(m.CreateForumTopic(chat_id=-200, name='Topic'), chat_id=-100),
            lambda: self.action(m.ApproveChatJoinRequest(chat_id=-100, user_id=43), chat_id=-100, subject_user_id=42),
            lambda: self.action(
                m.SendMessage(chat_id=42, business_connection_id='business-a', text='x', parse_mode=None),
                chat_id=42,
                message_thread_id=17,
                business_connection_id='business-a',
                owner_id=42,
            ),
            lambda: self.action(
                m.ReadBusinessMessage(business_connection_id='business-b', chat_id=42, message_id=10),
                chat_id=42,
                message_id=10,
                business_connection_id='business-a',
                owner_id=42,
            ),
        ]
        for build in cases:
            with self.assertRaises((PermissionDenied, ValidationFailure)):
                build()
        other = Bot('101:OTHER_PLATFORM_FIXTURE', session=self.session)
        with self.assertRaises(PermissionDenied):
            await execute_platform_action(
                other, self.action(m.CreateForumTopic(chat_id=-100, name='Topic'), chat_id=-100), self.hooks
            )
        self.assertEqual(self.session.calls, [])

    async def test_mutating_original_or_returned_request_does_not_change_action(self):
        native = m.CreateForumTopic(chat_id=-100, name='Topic')
        action = self.action(native, chat_id=-100)
        native.chat_id = -200
        action.request.name = 'Other'
        await self.run_action(action)
        self.assertEqual(self.effects(m.CreateForumTopic)[0].name, 'Topic')

    async def test_private_topics_use_getme_capability_without_admin_membership(self):
        action = self.action(m.CreateForumTopic(chat_id=42, name='Topic'), chat_id=42)
        await self.run_action(action)
        self.assertEqual(self.effects(m.GetChatMember), [])

    async def test_private_topics_disabled_do_not_create(self):
        self.session.respond(m.GetMe, dict(BOT, has_topics_enabled=False))
        with self.assertRaises(PermissionDenied):
            await self.run_action(self.action(m.CreateForumTopic(chat_id=42, name='Topic'), chat_id=42))
        self.assertEqual(self.effects(m.CreateForumTopic), [])

    async def test_closed_topic_method_does_not_invent_private_support(self):
        with self.assertRaises(PermissionDenied):
            await self.run_action(
                self.action(m.CloseForumTopic(chat_id=42, message_thread_id=17), chat_id=42, message_thread_id=17)
            )

    async def test_topic_creator_exception_requires_current_host_receipt(self):
        self.session.respond(m.GetChatMember, {'status': 'member', 'user': BOT})
        self.session.respond(m.EditForumTopic, True)
        action = self.action(
            m.EditForumTopic(chat_id=-100, message_thread_id=17, name='Edited'), chat_id=-100, message_thread_id=17
        )
        with self.assertRaises(PermissionDenied):
            await self.run_action(action)
        self.permit = replace(self.permit, topic_created_by_bot=True)
        await self.run_action(action)

    async def test_invalid_icon_and_color_rejected_before_create(self):
        with self.assertRaises(ValidationFailure):
            self.action(m.CreateForumTopic(chat_id=-100, name='Topic', icon_color=99), chat_id=-100)
        with self.assertRaises(PermissionDenied):
            await self.run_action(
                self.action(m.CreateForumTopic(chat_id=-100, name='Topic', icon_custom_emoji_id='999'), chat_id=-100)
            )
        self.assertEqual(self.effects(m.CreateForumTopic), [])

    async def test_paid_and_multiple_reactions_rejected_before_io(self):
        for reactions in ([ReactionTypePaid()], [ReactionTypeEmoji(emoji='👍'), ReactionTypeEmoji(emoji='❤')]):
            with self.assertRaises(ValidationFailure):
                self.action(
                    m.SetMessageReaction(chat_id=-100, message_id=10, reaction=reactions), chat_id=-100, message_id=10
                )

    async def test_custom_reaction_needs_current_message_or_chat_evidence(self):
        self.session.respond(m.SetMessageReaction, True)
        action = self.action(
            m.SetMessageReaction(
                chat_id=-100, message_id=10, reaction=[ReactionTypeCustomEmoji(custom_emoji_id='123')]
            ),
            chat_id=-100,
            message_id=10,
        )
        with self.assertRaises(PermissionDenied):
            await self.run_action(action)
        self.permit = replace(self.permit, existing_custom_reactions=('123',))
        await self.run_action(action)

    async def test_reaction_clear_is_native_empty_list(self):
        self.session.respond(m.SetMessageReaction, True)
        await self.run_action(
            self.action(m.SetMessageReaction(chat_id=-100, message_id=10, reaction=[]), chat_id=-100, message_id=10)
        )
        self.assertEqual(self.effects(m.SetMessageReaction)[0].reaction, [])

    async def test_reaction_moderation_requires_delete_right_and_one_actor(self):
        with self.assertRaises(ValidationFailure):
            self.action(m.DeleteMessageReaction(chat_id=-100, message_id=10), chat_id=-100, message_id=10)
        self.session.respond(m.GetChatMember, {'status': 'member', 'user': BOT})
        with self.assertRaises(PermissionDenied):
            await self.run_action(
                self.action(
                    m.DeleteMessageReaction(chat_id=-100, message_id=10, user_id=42),
                    chat_id=-100,
                    message_id=10,
                    subject_user_id=42,
                )
            )

    async def test_join_query_queue_and_deadline_not_legacy_approval(self):
        self.session.respond(m.AnswerChatJoinRequestQuery, True)
        self.permit = replace(self.permit, join_request_active=True, join_received_at=datetime.now(timezone.utc))
        action = self.action(
            m.AnswerChatJoinRequestQuery(chat_join_request_query_id='q', result='queue'),
            chat_id=-100,
            subject_user_id=42,
            join_query_id='q',
        )
        await self.run_action(action)
        self.assertEqual(self.effects(m.GetChatMember), [])
        with self.assertRaises(ValidationFailure):
            await self.run_action(
                self.action(
                    m.ApproveChatJoinRequest(chat_id=-100, user_id=42),
                    chat_id=-100,
                    subject_user_id=42,
                    join_query_id='q',
                )
            )

    async def test_expired_join_query_is_rejected_without_claim_or_native_answer(self):
        self.permit = replace(
            self.permit, join_request_active=True, join_received_at=datetime.now(timezone.utc) - timedelta(seconds=11)
        )
        with self.assertRaises(PermissionDenied):
            await self.run_action(
                self.action(
                    m.AnswerChatJoinRequestQuery(chat_join_request_query_id='q', result='approve'),
                    chat_id=-100,
                    subject_user_id=42,
                    join_query_id='q',
                )
            )
        self.assertIsNone(self.status())
        self.assertEqual(self.effects(m.AnswerChatJoinRequestQuery), [])

    async def test_join_webapp_requires_https_and_current_query_support(self):
        with self.assertRaises(ValidationFailure):
            self.action(
                m.SendChatJoinRequestWebApp(chat_join_request_query_id='q', web_app_url='http://localhost'),
                chat_id=-100,
                subject_user_id=42,
                join_query_id='q',
            )
        self.permit = replace(self.permit, join_request_active=True, join_received_at=datetime.now(timezone.utc))
        self.session.respond(m.GetMe, dict(BOT, supports_join_request_queries=False))
        with self.assertRaises(PermissionDenied):
            await self.run_action(
                self.action(
                    m.SendChatJoinRequestWebApp(chat_join_request_query_id='q', web_app_url='https://example.com/app'),
                    chat_id=-100,
                    subject_user_id=42,
                    join_query_id='q',
                )
            )

    async def test_legacy_join_has_separate_current_invite_right(self):
        self.permit = replace(self.permit, join_request_active=True)
        self.session.respond(m.ApproveChatJoinRequest, True)
        await self.run_action(
            self.action(m.ApproveChatJoinRequest(chat_id=-100, user_id=42), chat_id=-100, subject_user_id=42)
        )
        self.assertEqual(len(self.effects(m.GetChatMember)), 1)

    async def test_business_owner_and_revocation_prevent_write(self):
        action = self.action(
            m.SetBusinessAccountBio(business_connection_id='business-a', bio='Literal'),
            business_connection_id='business-a',
            owner_id=42,
        )
        for changed in (dict(CONNECTION, is_enabled=False), dict(CONNECTION, user=dict(USER, id=43))):
            self.session.respond(m.GetBusinessConnection, changed)
            with self.assertRaises(PermissionDenied):
                await self.run_action(action)
        self.assertEqual(self.effects(m.SetBusinessAccountBio), [])

    async def test_business_rights_are_not_interchangeable(self):
        self.session.respond(m.GetBusinessConnection, dict(CONNECTION, rights={'can_reply': True}))
        self.permit = replace(self.permit, business_chat_eligible=True)
        with self.assertRaises(PermissionDenied):
            await self.run_action(
                self.action(
                    m.ReadBusinessMessage(business_connection_id='business-a', chat_id=42, message_id=10),
                    business_connection_id='business-a',
                    owner_id=42,
                    chat_id=42,
                    message_id=10,
                )
            )

    async def test_business_sent_delete_exception_needs_verified_ownership(self):
        self.session.respond(m.GetBusinessConnection, dict(CONNECTION, rights={'can_delete_sent_messages': True}))
        self.session.respond(m.DeleteBusinessMessages, True)
        action = self.action(
            m.DeleteBusinessMessages(business_connection_id='business-a', message_ids=[10]),
            business_connection_id='business-a',
            owner_id=42,
            chat_id=42,
        )
        with self.assertRaises(PermissionDenied):
            await self.run_action(action)
        self.permit = replace(self.permit, messages_sent_by_bot=True)
        await self.run_action(action)

    async def test_business_recent_eligibility_is_not_inferred_from_connection(self):
        action = self.action(
            m.ReadBusinessMessage(business_connection_id='business-a', chat_id=42, message_id=10),
            business_connection_id='business-a',
            owner_id=42,
            chat_id=42,
            message_id=10,
        )
        with self.assertRaises(PermissionDenied):
            await self.run_action(action)
        self.permit = replace(self.permit, business_chat_eligible=True)
        self.session.respond(m.ReadBusinessMessage, True)
        await self.run_action(action)

    async def test_story_upload_needs_codec_dimensions_acl_and_manage_stories(self):
        native = m.PostStory(
            business_connection_id='business-a',
            content=StoryPhotoUpload(photo=BufferedInputFile(b'fixture', 'story.jpg')),
            active_period=21600,
            caption='<b>literal</b>',
            parse_mode=None,
        )
        action = self.action(native, business_connection_id='business-a', owner_id=42)
        with self.assertRaises(PermissionDenied):
            await self.run_action(action)
        self.permit = replace(self.permit, story_media_verified=True)
        result = await self.run_action(action)
        self.assertEqual(result.receipt.result_id, 1)
        self.assertEqual(self.effects(m.PostStory)[0].caption, '<b>literal</b>')

    async def test_story_file_id_period_and_default_parse_mode_do_not_pass(self):
        for content, period, mode in [
            (InputStoryContentPhoto(photo='reusable-id'), 21600, None),
            (StoryPhotoUpload(photo=BufferedInputFile(b'f', 's.jpg')), 1, None),
            (StoryPhotoUpload(photo=BufferedInputFile(b'f', 's.jpg')), 21600, 'HTML'),
        ]:
            with self.assertRaises(ValidationFailure):
                self.action(
                    m.PostStory(
                        business_connection_id='business-a', content=content, active_period=period, parse_mode=mode
                    ),
                    business_connection_id='business-a',
                    owner_id=42,
                )

    async def test_repost_requires_both_current_connections_and_own_source_story(self):
        self.session.respond(
            m.GetBusinessConnection,
            lambda r: dict(
                CONNECTION, id=r.business_connection_id, user_chat_id=43 if r.business_connection_id == 'source' else 42
            ),
        )
        self.session.respond(m.RepostStory, {'id': 2, 'chat': {'id': 42, 'type': 'private'}})
        action = self.action(
            m.RepostStory(business_connection_id='business-a', from_chat_id=43, from_story_id=1, active_period=86400),
            business_connection_id='business-a',
            owner_id=42,
            source_business_connection_id='source',
        )
        with self.assertRaises(PermissionDenied):
            await self.run_action(action)
        self.permit = replace(self.permit, source_story_posted_by_bot=True)
        await self.run_action(action)
        self.assertEqual(len(self.effects(m.RepostStory)), 1)

    async def test_gift_current_quote_atomic_budget_and_duplicate(self):
        self.permit = replace(self.permit, financial_authorized=True, star_cost=25, max_stars=25)
        self.session.respond(m.SendGift, True)
        action = self.action(
            m.SendGift(gift_id='gift-a', user_id=42, pay_for_upgrade=True, text='Literal', text_parse_mode=None),
            subject_user_id=42,
        )
        await self.run_action(action)
        with self.assertRaises(ConflictFailure):
            await self.run_action(action)
        self.assertEqual(self.db.execute('SELECT remaining FROM platform_budgets').fetchone(), (9975,))
        self.assertEqual(len(self.effects(m.SendGift)), 1)

    async def test_gift_stale_price_or_unavailable_does_not_reserve_budget(self):
        self.permit = replace(self.permit, financial_authorized=True, star_cost=19, max_stars=100)
        with self.assertRaises(PermissionDenied):
            await self.run_action(
                self.action(m.SendGift(gift_id='gift-a', user_id=42, text_parse_mode=None), subject_user_id=42)
            )
        self.assertIsNone(self.status())
        self.assertEqual(self.db.execute('SELECT remaining FROM platform_budgets').fetchone(), (10000,))

    async def test_insufficient_atomic_budget_prevents_gift_send(self):
        self.permit = replace(self.permit, financial_authorized=True, star_cost=20, max_stars=20)
        self.db.execute('UPDATE platform_budgets SET remaining=19')
        self.db.commit()
        with self.assertRaises(PermissionDenied):
            await self.run_action(
                self.action(m.SendGift(gift_id='gift-a', user_id=42, text_parse_mode=None), subject_user_id=42)
            )
        self.assertEqual(self.effects(m.SendGift), [])
        self.assertIsNone(self.status())

    async def test_limited_gift_cannot_be_sent_to_channel(self):
        self.permit = replace(self.permit, financial_authorized=True, star_cost=20, max_stars=20)
        self.session.respond(m.GetAvailableGifts, {'gifts': [dict(GIFT, total_count=100)]})
        with self.assertRaises(PermissionDenied):
            await self.run_action(
                self.action(m.SendGift(gift_id='gift-a', chat_id=-100, text_parse_mode=None), chat_id=-100)
            )

    async def test_paid_upgrade_needs_additional_transfer_stars_right(self):
        self.permit = replace(self.permit, financial_authorized=True, star_cost=5, max_stars=5)
        self.session.respond(m.GetBusinessConnection, dict(CONNECTION, rights={'can_transfer_and_upgrade_gifts': True}))
        with self.assertRaises(PermissionDenied):
            await self.run_action(
                self.action(
                    m.UpgradeGift(business_connection_id='business-a', owned_gift_id='owned', star_count=5),
                    business_connection_id='business-a',
                    owner_id=42,
                )
            )

    async def test_premium_month_price_pair_and_zero_omitted_gift_charge(self):
        with self.assertRaises(ValidationFailure):
            self.action(
                m.GiftPremiumSubscription(user_id=42, month_count=3, star_count=1500, text_parse_mode=None),
                subject_user_id=42,
            )
        with self.assertRaises(ValidationFailure):
            self.action(
                m.TransferGift(business_connection_id='business-a', owned_gift_id='owned', new_owner_chat_id=43),
                business_connection_id='business-a',
                owner_id=42,
            )

    async def test_managed_token_is_child_scoped_secret_and_read_does_not_claim(self):
        self.permit = replace(self.permit, managed_bot_bound=True)
        self.session.respond(m.GetManagedBotToken, '500:SECRET_MANAGED_TOKEN_123456789')
        result = await self.run_action(self.action(m.GetManagedBotToken(user_id=500), child_bot_id=500, owner_id=42))
        self.assertIsInstance(result.value, SecretToken)
        self.assertNotIn('SECRET', repr(result))
        self.assertNotIn('SECRET', repr(result.value))
        self.assertIsNone(self.status())
        self.assertTrue(result.value.reveal().startswith('500:'))

    async def test_managed_binding_owner_or_capability_denial_does_not_read_token(self):
        action = self.action(m.GetManagedBotToken(user_id=500), child_bot_id=500, owner_id=42)
        with self.assertRaises(PermissionDenied):
            await self.run_action(action)
        self.permit = replace(self.permit, managed_bot_bound=True)
        self.session.respond(m.GetMe, dict(BOT, can_manage_bots=False))
        with self.assertRaises(PermissionDenied):
            await self.run_action(action)
        self.assertEqual(self.effects(m.GetManagedBotToken), [])

    async def test_rotation_lost_response_is_unknown_without_second_rotation(self):
        self.permit = replace(self.permit, managed_bot_bound=True)

        def lost(r):
            raise OSError('lost')

        self.session.respond(m.ReplaceManagedBotToken, lost)
        action = self.action(m.ReplaceManagedBotToken(user_id=500), child_bot_id=500, owner_id=42)
        with self.assertRaises(UnknownOutcome):
            await self.run_action(action)
        with self.assertRaises(ConflictFailure):
            await self.run_action(action)
        self.assertEqual(len(self.effects(m.ReplaceManagedBotToken)), 1)

    async def test_wrong_child_rotation_response_is_unknown_not_local_rejection(self):
        self.permit = replace(self.permit, managed_bot_bound=True)
        self.session.respond(m.ReplaceManagedBotToken, '501:OTHER_CHILD_TOKEN_1234567890')
        with self.assertRaises(UnknownOutcome):
            await self.run_action(self.action(m.ReplaceManagedBotToken(user_id=500), child_bot_id=500, owner_id=42))
        self.assertEqual(self.status(), ('unknown',))

    async def test_creation_link_is_user_confirmation_and_encodes_name(self):
        link = managed_bot_link('ManagerBot', 'ExampleBot', name='Example & Bot')
        self.assertEqual(link, 'https://t.me/newbot/ManagerBot/ExampleBot?name=Example+%26+Bot')
        self.assertEqual(self.session.calls, [])
        for username in ('@ManagerBot', 'Bad/PathBot', 'bot'):
            with self.assertRaises(ValidationFailure):
                managed_bot_link(username, 'ExampleBot')

    async def test_anonymous_reaction_preserves_chat_actor_and_raw_unknown_fields(self):
        update = Update.model_validate(
            {
                'update_id': 1,
                'message_reaction': {
                    'chat': {'id': -100, 'type': 'supergroup'},
                    'message_id': 10,
                    'date': 1780000000,
                    'actor_chat': {'id': -200, 'type': 'channel', 'title': 'Anonymous'},
                    'old_reaction': [],
                    'new_reaction': [],
                    'new_native_fact': None,
                },
            }
        )
        event = platform_event(update, bot_id=100)
        self.assertIsNone(event.source_user_id)
        self.assertEqual(event.source_chat_id, -200)
        self.assertIn('new_native_fact', event.details_json)
        self.assertNotIn('new_native_fact', repr(event))

    async def test_managed_update_uses_actual_sdk_bot_user_field_and_owner(self):
        event = platform_event(
            Update.model_validate({'update_id': 2, 'managed_bot': {'user': USER, 'bot_user': CHILD}}), bot_id=100
        )
        self.assertEqual((event.owner_id, event.child_bot_id), (42, 500))

    async def test_router_binding_dedup_revocation_and_existing_dispatcher(self):
        observed = []
        revoked = False

        async def lookup(event):
            return None if revoked else self.scope(chat_id=-100, message_id=10)

        async def observe(event, scope):
            with self.db:
                self.db.execute(
                    'CREATE TABLE IF NOT EXISTS updates (bot_id INTEGER,update_id INTEGER,PRIMARY '
                    'KEY(bot_id,update_id))'
                )
                changed = self.db.execute('INSERT OR IGNORE INTO updates VALUES (?,?)', (event.bot_id, event.update_id))
                if changed.rowcount:
                    observed.append(event)

        dispatcher = Dispatcher()
        dispatcher.include_router(platform_events_router(lookup, observe))
        host = Router()
        helped = []

        async def help(message):
            helped.append(message.text)

        host.message.register(help, F.text == '/help')
        dispatcher.include_router(host)
        update = Update.model_validate(
            {
                'update_id': 3,
                'message_reaction_count': {
                    'chat': {'id': -100, 'type': 'supergroup'},
                    'message_id': 10,
                    'date': 1780000000,
                    'reactions': [],
                },
            }
        )
        await dispatcher.feed_update(self.bot, update)
        await dispatcher.feed_update(self.bot, update)
        self.assertEqual(len(observed), 1)
        data = update.model_dump(mode='json')
        data['update_id'] = 4
        data['message_reaction_count']['chat']['id'] = -200
        foreign = Update.model_validate(data)
        await dispatcher.feed_update(self.bot, foreign)
        revoked = True
        await dispatcher.feed_update(self.bot, update.model_copy(update={'update_id': 5}))
        self.assertEqual(len(observed), 1)
        await dispatcher.feed_update(
            self.bot,
            Update.model_validate(
                {
                    'update_id': 6,
                    'message': {
                        'message_id': 6,
                        'date': 1780000000,
                        'chat': {'id': 42, 'type': 'private'},
                        'from': USER,
                        'text': '/help',
                    },
                }
            ),
        )
        self.assertEqual(helped, ['/help'])

    async def test_unrelated_and_ambiguous_updates_do_not_invent_platform_event(self):
        ordinary = {'message_id': 1, 'date': 1780000000, 'chat': {'id': 42, 'type': 'private'}, 'text': 'normal'}
        self.assertIsNone(platform_event(Update.model_validate({'update_id': 1, 'message': ordinary}), bot_id=100))
        self.assertIsNone(
            platform_event(
                Update.model_validate(
                    {'update_id': 1, 'message': ordinary, 'managed_bot': {'user': USER, 'bot_user': CHILD}}
                ),
                bot_id=100,
            )
        )

    async def test_contracts_cover_every_required_family_with_version_and_source(self):
        contracts = platform_contracts()
        self.assertEqual(
            {c.family for c in contracts}, {'topics', 'reactions', 'join', 'business', 'stories', 'gifts', 'managed'}
        )
        self.assertEqual(len({c.method for c in contracts}), len(contracts))
        for contract in contracts:
            self.assertEqual(contract.bot_api, '10.3')
            self.assertEqual(contract.verification, 'sdk')
            self.assertTrue(contract.source.endswith(contract.method.lower()))

    async def test_actual_story_multipart_serialization_binds_uploaded_bytes(self):
        from aiogram.client.session.aiohttp import AiohttpSession

        session = AiohttpSession()

        class Writer:
            def __init__(self):
                self.data = bytearray()

            async def write(self, chunk):
                self.data.extend(chunk)

        try:
            for content, filename, data in [
                (
                    StoryPhotoUpload(photo=BufferedInputFile(b'PHOTO-WIRE-BYTES', 'story.jpg')),
                    'story.jpg',
                    b'PHOTO-WIRE-BYTES',
                ),
                (
                    StoryVideoUpload(video=BufferedInputFile(b'VIDEO-WIRE-BYTES', 'story.mp4'), duration=2),
                    'story.mp4',
                    b'VIDEO-WIRE-BYTES',
                ),
            ]:
                request = m.PostStory(
                    business_connection_id='business-a', content=content, active_period=21600, parse_mode=None
                )
                files = {}
                payload = self.bot.session.prepare_value(request.model_dump(warnings=False), self.bot, files)
                parsed = json.loads(payload)
                key = parsed['content'][content.type].removeprefix('attach://')
                self.assertEqual(files[key].filename, filename)
                self.assertEqual(files[key].data, data)
                form = session.build_form_data(self.bot, request)
                writer = Writer()
                await form().write(writer)
                self.assertIn(data, writer.data)
                self.assertIn(filename.encode(), writer.data)
                self.assertIn(b'attach://', writer.data)
        finally:
            await session.close()

    async def test_every_reviewed_method_executes_through_native_sdk_and_host_hooks(self):
        from aiogram.types import InputProfilePhotoStatic

        fixtures = json.loads(
            (Path(__file__).resolve().parents[3] / 'catalog/bot-api-request-fixtures.json').read_text('utf-8')
        )['methods']
        seen = []
        for contract in platform_contracts():
            with self.subTest(method=contract.method):
                name = contract.method
                data = dict(fixtures[name])
                cls = getattr(m, name[0].upper() + name[1:])
                fields = {}
                cost = 0
                if 'chat_id' in data:
                    data['chat_id'] = 42 if contract.family == 'business' else -100
                    fields['chat_id'] = data['chat_id']
                if 'message_thread_id' in data:
                    data['message_thread_id'] = 17
                    fields['message_thread_id'] = 17
                if 'message_id' in data:
                    data['message_id'] = 10
                    fields['message_id'] = 10
                if 'user_id' in data:
                    data['user_id'] = 500 if contract.family == 'managed' else 42
                    fields['subject_user_id'] = 42 if contract.family != 'managed' else None
                if 'business_connection_id' in data:
                    data['business_connection_id'] = 'business-a'
                    fields.update(business_connection_id='business-a', owner_id=42)
                if name in ('sendMessage', 'sendPhoto', 'editMessageText'):
                    data.update(parse_mode=None, business_connection_id='business-a', chat_id=42)
                    fields.update(business_connection_id='business-a', owner_id=42, chat_id=42)
                    if name == 'editMessageText':
                        data['message_id'] = 10
                        fields['message_id'] = 10
                if name == 'deleteBusinessMessages':
                    fields['chat_id'] = 42
                    data['message_ids'] = [10]
                if name == 'setBusinessAccountProfilePhoto':
                    data['photo'] = InputProfilePhotoStatic(photo=BufferedInputFile(b'profile-fixture', 'profile.jpg'))
                if name == 'sendGift':
                    data.update(user_id=42, gift_id='gift-a', text_parse_mode=None)
                    fields['subject_user_id'] = 42
                    cost = 20
                if name == 'giftPremiumSubscription':
                    data.update(month_count=3, star_count=1000, text_parse_mode=None)
                    cost = 1000
                if name in ('upgradeGift', 'transferGift'):
                    data['star_count'] = 0
                if name == 'transferBusinessAccountStars':
                    data['star_count'] = 1
                    cost = 1
                if name == 'transferGift':
                    data['new_owner_chat_id'] = 43
                if name == 'setMessageReaction':
                    data['reaction'] = [ReactionTypeEmoji(emoji='👍')]
                if name in ('deleteMessageReaction', 'deleteAllMessageReactions'):
                    data['user_id'] = 42
                    fields['subject_user_id'] = 42
                if name in ('answerChatJoinRequestQuery', 'sendChatJoinRequestWebApp'):
                    data['chat_join_request_query_id'] = 'query'
                    fields.update(join_query_id='query', chat_id=-100, subject_user_id=42)
                    if name == 'answerChatJoinRequestQuery':
                        data['result'] = 'queue'
                    else:
                        data['web_app_url'] = 'https://example.com/app'
                if name in ('postStory', 'editStory'):
                    data.update(
                        content=StoryPhotoUpload(photo=BufferedInputFile(b'story-fixture', 'story.jpg')),
                        parse_mode=None,
                    )
                if name in ('postStory', 'repostStory'):
                    data['active_period'] = 21600
                if name == 'repostStory':
                    data.update(from_chat_id=42, from_story_id=1)
                    fields['source_business_connection_id'] = 'business-a'
                if contract.family == 'managed':
                    fields.update(child_bot_id=500, owner_id=42)
                if name == 'setManagedBotAccessSettings':
                    data.update(is_access_restricted=True, added_user_ids=[42])
                self.permit = PlatformPermit(
                    allowed=True,
                    topic_created_by_bot=True,
                    business_chat_eligible=True,
                    messages_sent_by_bot=True,
                    join_request_active=True,
                    join_received_at=datetime.now(timezone.utc),
                    financial_authorized=True,
                    star_cost=cost,
                    max_stars=cost,
                    managed_bot_bound=True,
                    source_story_posted_by_bot=True,
                    story_media_verified=True,
                    transfer_destination_active=True,
                )
                request = cls(**data)
                response = True
                if cls.__returning__ is not bool:
                    response = {'id': 1, 'chat': {'id': 42, 'type': 'private'}}
                    if name in ('sendMessage', 'sendPhoto', 'editMessageText'):
                        response = {'message_id': 10, 'date': 1780000000, 'chat': {'id': 42, 'type': 'private'}}
                    elif name == 'createForumTopic':
                        response = {'message_thread_id': 17, 'name': 'Topic', 'icon_color': 7322096}
                    elif name == 'getForumTopicIconStickers':
                        response = [STICKER]
                    elif name == 'getBusinessConnection':
                        response = CONNECTION
                    elif name == 'getAvailableGifts':
                        response = {'gifts': [GIFT]}
                    elif name in ('getUserGifts', 'getChatGifts', 'getBusinessAccountGifts'):
                        response = {'total_count': 0, 'gifts': []}
                    elif name == 'getBusinessAccountStarBalance':
                        response = {'amount': 0}
                    elif name in ('getManagedBotToken', 'replaceManagedBotToken'):
                        response = '500:ALL_METHOD_SECRET_TOKEN_12345678'
                    elif name == 'getManagedBotAccessSettings':
                        response = {'is_access_restricted': True, 'added_users': [USER]}
                self.session.respond(cls, response)
                action = PlatformAction(PlatformScope(100, 42, 'all-' + name, **fields), request)
                result = await self.run_action(action)
                self.assertEqual(result.receipt.outcome, 'succeeded')
                self.assertEqual(result.receipt.method, name)
                seen.append(name)
        self.assertEqual(len(seen), 51)


if __name__ == '__main__':
    unittest.main()
