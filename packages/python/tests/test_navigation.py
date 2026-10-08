"""Native SDK dispatcher, ownership, history, concurrent updates and uncertain edits."""

import asyncio
import unittest

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Update

from telegram_patterns import ConflictFailure, UnknownOutcome, ValidationFailure
from telegram_patterns.aiogram import (
    ActionButton,
    KeyboardCapabilities,
    KeyboardLayout,
    MessageNavigation,
    NavigationScreen,
    navigation_router,
)
from telegram_patterns.testing import StubSession


def screens():
    return [
        NavigationScreen(
            'home', 'Главная <без HTML>', [ActionButton('Каталог', 'catalog'), ActionButton('Помощь', 'help')]
        ),
        NavigationScreen('catalog', 'Каталог', [ActionButton('Товар', 'item')]),
        NavigationScreen('item', 'Карточка товара'),
        NavigationScreen('help', 'Помощь'),
    ]


class NavigationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session = StubSession().respond(AnswerCallbackQuery, True)
        self.bot = Bot('100:NAVIGATION_FIXTURE', session=self.session, default=DefaultBotProperties(parse_mode='HTML'))
        self.serial = 0
        self.chat_type, self.thread_id = 'private', None

        def message(method):
            if isinstance(method, SendMessage):
                self.serial += 1
            return {
                'message_id': self.serial if isinstance(method, SendMessage) else method.message_id,
                'date': 1,
                'chat': {'id': method.chat_id, 'type': self.chat_type},
                'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'},
                'message_thread_id': self.thread_id,
                'text': method.text,
                'reply_markup': method.reply_markup.model_dump(exclude_none=True),
            }

        self.message = message
        self.session.respond(SendMessage, message).respond(EditMessageText, message)
        self.nav = MessageNavigation(screens())
        self.dp = Dispatcher()
        self.results = []

        async def result(query, feedback):
            self.results.append(feedback)

        self.dp.include_router(navigation_router(self.nav, on_result=result))
        self.uid = 0

    async def asyncTearDown(self):
        await self.dp.fsm.close()
        await self.bot.session.close()
        self.assertTrue(self.session.closed)

    def data(self, target, *, revision=None, nav=None):
        nav = nav or self.nav
        state = nav.get_state(100, 7, -70 if self.thread_id else 7, message_thread_id=self.thread_id)
        return f'{nav.prefix}{state.session_id}:{state.revision if revision is None else revision}:{target}'

    def query(self, data, *, actor=7, chat=None, message=None, thread='normal', bot=100):
        state = self.nav.get_state(100, 7, -70 if self.thread_id else 7, message_thread_id=self.thread_id)
        self.uid += 1
        payload = {
            'id': f'q{self.uid}',
            'from': {'id': actor, 'is_bot': False, 'first_name': 'Owner'},
            'chat_instance': 'synthetic',
            'data': data,
            'message': {
                'message_id': state.message_id if message is None else message,
                'date': 1,
                'chat': {'id': state.chat_id if chat is None else chat, 'type': self.chat_type},
                'from': {'id': bot, 'is_bot': True, 'first_name': 'Fixture'},
                'message_thread_id': self.thread_id if thread == 'normal' else thread,
            },
        }
        return CallbackQuery.model_validate(payload, context={'bot': self.bot})

    async def feed(self, data, **kwargs):
        query = self.query(data, **kwargs)
        await self.dp.feed_update(self.bot, Update(update_id=self.uid, callback_query=query))
        return self.results[-1]

    def edits(self):
        return [c for c in self.session.calls if isinstance(c, EditMessageText)]

    async def test_history_back_and_reopen_edit_only_the_original_message(self):
        start = await self.nav.open(self.bot, 7, 7)
        old = self.data('catalog')
        self.assertEqual((await self.feed(old)).status, 'accepted')
        self.assertEqual((await self.feed(self.data('item'))).state.history, ('home', 'catalog'))
        self.assertEqual((await self.feed(self.data('_back'))).state.screen, 'catalog')
        self.assertEqual((await self.feed(self.data('_back'))).state.history, ())
        self.assertEqual((await self.feed(self.data('_back'))).status, 'stale')
        self.assertEqual((await self.feed(old)).status, 'stale')
        final = await self.nav.open(self.bot, 7, 7, screen='help')
        self.assertEqual((final.screen, final.history, final.message_id), ('help', (), start.message_id))
        self.assertEqual(len([c for c in self.session.calls if isinstance(c, SendMessage)]), 1)
        self.assertEqual(
            [c.text for c in self.edits()], ['Каталог', 'Карточка товара', 'Каталог', 'Главная <без HTML>', 'Помощь']
        )
        for c in self.edits():
            self.assertEqual((c.chat_id, c.message_id, c.parse_mode), (7, start.message_id, None))
        self.assertIsNone(self.session.calls[0].parse_mode)
        self.assertTrue(
            all(
                len(b.callback_data.encode()) <= 64
                for c in self.edits()
                for row in c.reply_markup.inline_keyboard
                for b in row
            )
        )

    async def test_foreign_actor_and_all_wrong_contexts_ack_without_edit(self):
        before = await self.nav.open(self.bot, 7, 7)
        data = self.data('catalog')
        self.assertEqual((await self.feed(data, actor=8)).status, 'denied')
        self.assertIsNone(self.results[-1].state)
        for kwargs in ({'chat': 8}, {'message': 99}, {'thread': 5}, {'bot': 101}):
            self.assertEqual((await self.feed(data, **kwargs)).status, 'stale')
        self.assertEqual(self.nav.get_state(100, 7, 7), before)
        self.assertFalse(self.edits())
        self.assertEqual(len([c for c in self.session.calls if isinstance(c, AnswerCallbackQuery)]), 5)

    async def test_payload_is_not_permission_for_an_unlisted_transition(self):
        before = await self.nav.open(self.bot, 7, 7)
        for target in ('item', '_back', 'not_declared'):
            self.assertEqual((await self.feed(self.data(target))).status, 'stale')
        for data in (
            self.data('catalog') + ':extra',
            self.data('catalog').replace(':0:', ':00:'),
            'nav:foreign:0:catalog',
            'nav:' + 'x' * 200,
        ):
            self.assertEqual((await self.feed(data)).status, 'stale')
        self.assertEqual(self.nav.get_state(100, 7, 7), before)
        self.assertFalse(self.edits())

    async def test_inline_inaccessible_business_and_wrong_bot_are_rejected(self):
        before = await self.nav.open(self.bot, 7, 7)
        base = self.query(self.data('catalog')).model_dump(mode='json', by_alias=True, exclude_none=True)
        payloads = []
        inline = dict(base)
        inline.pop('message')
        inline['inline_message_id'] = 'inline'
        payloads.append(inline)
        inaccessible = {**base, 'message': {**base['message'], 'date': 0}}
        payloads.append(inaccessible)
        business = {**base, 'message': {**base['message'], 'business_connection_id': 'business'}}
        payloads.append(business)
        for payload in payloads:
            self.assertEqual(
                (await self.nav.handle(CallbackQuery.model_validate(payload, context={'bot': self.bot}))).status,
                'stale',
            )
        other = Bot('101:OTHER_FIXTURE', session=self.session)
        try:
            self.assertEqual(
                (await self.nav.handle(CallbackQuery.model_validate(base, context={'bot': other}))).status, 'stale'
            )
        finally:
            await other.session.close()
        self.assertEqual(self.nav.get_state(100, 7, 7), before)
        self.assertFalse(self.edits())

    async def test_concurrent_same_revision_is_one_edit_and_ack_never_waits_on_edit(self):
        await self.nav.open(self.bot, 7, 7)
        data = self.data('catalog')
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow(method):
            entered.set()
            await release.wait()
            return self.message(method)

        self.session.respond(EditMessageText, slow)
        first = asyncio.create_task(self.nav.handle(self.query(data)))
        await entered.wait()
        second = asyncio.create_task(self.nav.handle(self.query(data)))
        await asyncio.sleep(0)
        self.assertEqual(len([c for c in self.session.calls if isinstance(c, AnswerCallbackQuery)]), 2)
        release.set()
        outcomes = await asyncio.gather(first, second)
        self.assertEqual([r.status for r in outcomes], ['accepted', 'stale'])
        self.assertEqual(len(self.edits()), 1)

    async def test_bad_request_keeps_confirmed_history_and_can_retry(self):
        before = await self.nav.open(self.bot, 7, 7)

        def reject(method):
            raise TelegramBadRequest(method=method, message='PRIVATE_SERVER_DETAIL')

        self.session.respond(EditMessageText, reject)
        data = self.data('catalog')
        failed = await self.feed(data)
        self.assertEqual(failed.status, 'unavailable')
        self.assertNotIn('PRIVATE', failed.text)
        self.assertEqual(failed.state, before)
        self.session.respond(EditMessageText, self.message)
        accepted = await self.feed(data)
        self.assertEqual((accepted.status, accepted.state.revision), ('accepted', 2))

    async def test_uncertain_edit_freezes_callbacks_and_explicit_reopen_recovers_same_message(self):
        before = await self.nav.open(self.bot, 7, 7)
        old = self.data('catalog')

        def lost(method):
            raise TimeoutError('PRIVATE_TOKEN')

        self.session.respond(EditMessageText, lost)
        failed = await self.feed(old)
        self.assertEqual(
            (failed.status, failed.state.phase, failed.state.screen, failed.state.history),
            ('unknown', 'unknown', 'home', ()),
        )
        self.assertNotIn('PRIVATE', failed.text)
        self.assertEqual((await self.feed(old)).status, 'unknown')
        self.assertEqual((await self.feed(self.data('item', revision=1))).status, 'stale')
        self.assertEqual(len(self.edits()), 1)
        self.session.respond(EditMessageText, self.message)
        recovered = await self.nav.open(self.bot, 7, 7)
        self.assertEqual((recovered.phase, recovered.message_id, recovered.revision), ('ready', before.message_id, 2))
        self.assertEqual((await self.feed(old)).status, 'stale')
        self.assertEqual((await self.feed(self.data('catalog'))).status, 'accepted')
        self.assertEqual(len([c for c in self.session.calls if isinstance(c, SendMessage)]), 1)

    async def test_cancellation_after_edit_started_preserves_unknown_and_releases_lock(self):
        await self.nav.open(self.bot, 7, 7)
        entered = asyncio.Event()

        async def pending(method):
            entered.set()
            await asyncio.Event().wait()

        self.session.respond(EditMessageText, pending)
        task = asyncio.create_task(self.nav.handle(self.query(self.data('catalog'))))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.nav.get_state(100, 7, 7).phase, 'unknown')
        self.session.respond(EditMessageText, self.message)
        state = await self.nav.open(self.bot, 7, 7)
        self.assertEqual((state.phase, state.revision), ('ready', 2))

    async def test_unknown_edit_recovery_after_ttl_uses_same_message(self):
        self.nav = MessageNavigation(screens(), ttl_seconds=0.01, max_sessions=1)
        initial = await self.nav.open(self.bot, 7, 7)

        def lost(method):
            raise TimeoutError('fixture')

        self.session.respond(EditMessageText, lost)
        self.assertEqual((await self.nav.handle(self.query(self.data('catalog')))).status, 'unknown')
        await asyncio.sleep(0.02)
        with self.assertRaises(ConflictFailure):
            await self.nav.open(self.bot, 8, 8)
        self.session.respond(EditMessageText, self.message)
        recovered = await self.nav.open(self.bot, 7, 7)
        self.assertEqual((recovered.session_id, recovered.message_id), (initial.session_id, initial.message_id))
        self.assertEqual((recovered.phase, recovered.revision), ('ready', 2))
        self.assertEqual(len([c for c in self.session.calls if isinstance(c, SendMessage)]), 1)

    async def test_initial_send_unknown_is_not_repeated_or_pruned(self):
        nav = MessageNavigation(screens(), ttl_seconds=0.001, max_sessions=1)

        def lost(method):
            raise TimeoutError('PRIVATE')

        self.session.respond(SendMessage, lost)
        with self.assertRaises(TimeoutError):
            await nav.open(self.bot, 7, 7)
        self.assertEqual(nav.get_state(100, 7, 7).phase, 'unknown')
        await asyncio.sleep(0.01)
        with self.assertRaises(UnknownOutcome):
            await nav.open(self.bot, 7, 7)
        with self.assertRaises(ConflictFailure):
            await nav.open(self.bot, 8, 8)
        self.assertEqual(len([c for c in self.session.calls if isinstance(c, SendMessage)]), 1)
        self.assertTrue(await nav.discard(100, 7, 7))
        self.assertFalse(await nav.discard(100, 7, 7))
        self.session.respond(SendMessage, self.message)
        self.assertEqual((await nav.open(self.bot, 7, 7)).phase, 'ready')

    async def test_initial_rejection_can_be_opened_again_and_bad_response_stays_unknown(self):
        def reject(method):
            raise TelegramBadRequest(method=method, message='rejected')

        self.session.respond(SendMessage, reject)
        with self.assertRaises(TelegramBadRequest):
            await self.nav.open(self.bot, 7, 7)
        self.assertIsNone(self.nav.get_state(100, 7, 7))

        def wrong(method):
            m = self.message(method)
            m['chat']['id'] = 999
            return m

        self.session.respond(SendMessage, wrong)
        with self.assertRaises(UnknownOutcome):
            await self.nav.open(self.bot, 7, 7)
        self.assertEqual(self.nav.get_state(100, 7, 7).phase, 'unknown')
        with self.assertRaises(UnknownOutcome):
            await self.nav.open(self.bot, 7, 7)

    async def test_edit_response_with_wrong_target_or_inline_boolean_is_unknown(self):
        for response in (True, lambda method: {**self.message(method), 'message_id': 987}):
            await self.nav.discard(100, 7, 7)
            self.session.respond(EditMessageText, response)
            await self.nav.open(self.bot, 7, 7)
            self.assertEqual((await self.feed(self.data('catalog'))).status, 'unknown')

    async def test_expiry_capacity_and_restart_leave_old_buttons_stale(self):
        self.nav = MessageNavigation(screens(), ttl_seconds=0.01, max_sessions=1)
        first = await self.nav.open(self.bot, 7, 7)
        old = self.data('catalog')
        with self.assertRaises(ConflictFailure):
            await self.nav.open(self.bot, 8, 8)
        await asyncio.sleep(0.02)
        self.assertEqual((await self.nav.handle(self.query(old))).status, 'stale')
        reopened = await self.nav.open(self.bot, 7, 7)
        self.assertNotEqual((first.session_id, first.message_id), (reopened.session_id, reopened.message_id))
        self.assertEqual((await self.nav.handle(self.query(old))).status, 'stale')
        fresh = MessageNavigation(screens())
        self.assertEqual((await fresh.handle(self.query(self.data('catalog')))).status, 'stale')

    async def test_group_topic_and_separate_owners_have_separate_scopes(self):
        self.chat_type, self.thread_id = 'supergroup', 9
        self.nav = MessageNavigation(screens(), capabilities=KeyboardCapabilities(chat_type='supergroup'))
        first = await self.nav.open(self.bot, 7, -70, message_thread_id=9)
        second = await self.nav.open(self.bot, 8, -70, message_thread_id=9)
        self.assertNotEqual(first.session_id, second.session_id)
        self.assertEqual((await self.nav.handle(self.query(self.data('catalog'), thread=10))).status, 'stale')
        self.assertEqual((await self.nav.handle(self.query(self.data('catalog')))).status, 'accepted')
        self.assertEqual(self.nav.get_state(100, 8, -70, message_thread_id=9), second)
        self.assertEqual(self.edits()[0].chat_id, -70)

    async def test_history_limit_is_explained_and_back_remains_available(self):
        self.nav = MessageNavigation(screens(), max_history=1)
        await self.nav.open(self.bot, 7, 7)
        self.assertEqual((await self.nav.handle(self.query(self.data('catalog')))).status, 'accepted')
        self.assertEqual((await self.nav.handle(self.query(self.data('item')))).status, 'unavailable')
        self.assertEqual(len(self.edits()), 1)
        self.assertEqual((await self.nav.handle(self.query(self.data('_back')))).state.screen, 'home')

    async def test_labels_layout_and_fallback_are_snapshots(self):
        buttons = [ActionButton('Товар', 'item', style='primary', custom_emoji_id='123')]
        screen = NavigationScreen('home', 'Главная', buttons, KeyboardLayout((3,)))
        nav = MessageNavigation([screen, NavigationScreen('item', 'Товар')])
        buttons.clear()
        await nav.open(self.bot, 7, 7)
        markup = self.session.calls[-1].reply_markup
        self.assertEqual([len(row) for row in markup.inline_keyboard], [1, 1])
        self.assertEqual(markup.inline_keyboard[0][0].text, 'Товар')
        self.assertIsNone(markup.inline_keyboard[0][0].style)
        self.assertIsNone(markup.inline_keyboard[0][0].icon_custom_emoji_id)


class NavigationValidationTests(unittest.TestCase):
    def test_graph_limits_prefix_and_native_presentation_are_checked_before_send(self):
        for items in (
            [],
            [NavigationScreen('a', 'A'), NavigationScreen('a', 'B')],
            [NavigationScreen('a', 'A', [ActionButton('Bad', 'missing')])],
        ):
            with self.assertRaises(ValidationFailure):
                MessageNavigation(items)
        for settings in (
            {'prefix': 'too_long_prefix:'},
            {'ttl_seconds': float('inf')},
            {'ttl_seconds': True},
            {'max_sessions': True},
            {'max_history': 0},
            {'back_text': ''},
            {'capabilities': KeyboardCapabilities(business=True)},
            {'capabilities': KeyboardCapabilities(chat_type='channel')},
        ):
            with self.assertRaises(ValidationFailure):
                MessageNavigation(screens(), **settings)
        for key in ('_back', '_refresh', 'a' * 25, 'сайт'):
            with self.assertRaises(ValidationFailure):
                NavigationScreen(key, 'A')
        with self.assertRaises(ValidationFailure):
            NavigationScreen('a', '🙂' * 2049)
        with self.assertRaises(ValidationFailure):
            MessageNavigation([NavigationScreen('a', 'A', [ActionButton('Bad', 'a', custom_emoji_id='bad')])])
        nav = MessageNavigation(screens())
        with self.assertRaises(ValidationFailure):
            nav.get_state(100, True, 7)
