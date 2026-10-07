import asyncio
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.methods import AnswerCallbackQuery, GetMe, GetUpdates, SendMessage, SetMyCommands
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from pydantic import ValidationError

from telegram_patterns import BotSettings
from telegram_patterns.errors import AuthenticationRequired, TransportFailure
from telegram_patterns.aiogram import (ActionButton, CommandReply, action_menu, command_menu,
                                      command_router, page_number, paginated_menu, run_bot)
from telegram_patterns.testing import StubSession

TOKEN = '100:TEST'
DATE = datetime(2026, 10, 3, tzinfo=timezone.utc)
BOT_USER = User(id=100, is_bot=True, first_name='Fixture', username='component_bot')


def message(text=None):
    return Message(message_id=1, date=DATE, chat=Chat(id=42, type='private'),
                   from_user=User(id=42, is_bot=False, first_name='Fixture'), text=text)


def send_reply(method):
    return {'message_id': 2, 'date': int(DATE.timestamp()),
            'chat': {'id': method.chat_id, 'type': 'private'}, 'text': method.text}


class SettingsTests(unittest.TestCase):
    def test_env_custom_name_and_redacted_repr(self):
        settings = BotSettings.from_env('TEST_BOT_TOKEN', environ={'TEST_BOT_TOKEN': TOKEN})
        self.assertEqual(settings.token, TOKEN)
        self.assertNotIn(TOKEN, repr(settings))
        self.assertNotIn('TEST', str(settings))

    def test_missing_and_invalid_configuration_never_echoes_token(self):
        with self.assertRaisesRegex(ValueError, 'Set BOT_TOKEN'):
            BotSettings.from_env(environ={})
        for token in ('secret-value', '100:secret value', '', None):
            with self.subTest(token=token), self.assertRaises(ValueError) as raised:
                BotSettings(token)
            if token:
                self.assertNotIn(token, str(raised.exception))
        with self.assertRaises(ValueError):
            BotSettings.from_env('bad:name', environ={})

    def test_env_file_fills_missing_values_and_environment_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / '.env'
            env.write_text('# comment\nexport OTHER=x\nBOT_TOKEN="100:FROM_FILE"  \n', encoding='utf-8')
            self.assertEqual(BotSettings.from_env(environ={}, env_file=env).token, '100:FROM_FILE')
            self.assertEqual(BotSettings.from_env(environ={'BOT_TOKEN': TOKEN}, env_file=env).token, TOKEN)
            env.write_text("BOT_TOKEN=100:PLAIN # inline comment\n", encoding='utf-8')
            self.assertEqual(BotSettings.from_env(environ={}, env_file=env).token, '100:PLAIN')
            self.assertEqual(BotSettings.from_env(environ={'BOT_TOKEN': TOKEN}, env_file=Path(folder) / 'missing').token, TOKEN)
            with self.assertRaisesRegex(ValueError, 'or in .env'):
                BotSettings.from_env(environ={}, env_file=Path(folder) / '.env.absent')
            env.write_text('BOT_TOKEN=123456789:REPLACE_WITH_YOUR_TEST_BOT_TOKEN\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'placeholder'):
                BotSettings.from_env(environ={}, env_file=env)
            env.write_text('BOT_TOKEN 100:SECRET_LINE\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'line 1') as raised:
                BotSettings.from_env(environ={}, env_file=env)
            self.assertNotIn('SECRET_LINE', str(raised.exception))


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.buttons = [ActionButton(f'Пункт {index}', f'key-{index}', style='primary', custom_emoji_id='123')
                        for index in range(8)]

    def test_layout_unique_actions_and_context_emoji_fallback(self):
        menu = action_menu(self.buttons[:5], columns=2)
        self.assertEqual([len(row) for row in menu.inline_keyboard], [2, 2, 1])
        self.assertEqual([item.callback_data for row in menu.inline_keyboard for item in row],
                         [f'act:key-{index}' for index in range(5)])
        self.assertTrue(all(item.icon_custom_emoji_id is None for row in menu.inline_keyboard for item in row))
        enabled = action_menu(self.buttons[:1], emoji_entitlement_verified=True)
        self.assertEqual(enabled.inline_keyboard[0][0].icon_custom_emoji_id, '123')

    def test_empty_duplicate_keys_and_layout_limits(self):
        self.assertEqual(action_menu([]).inline_keyboard, [])
        for columns in (0, 9, True):
            with self.assertRaises(ValueError): action_menu(self.buttons, columns=columns)
        with self.assertRaises(ValueError): action_menu([self.buttons[0], self.buttons[0]])
        with self.assertRaises(ValueError):
            action_menu([ActionButton(str(index), str(index)) for index in range(101)])
        with self.assertRaises(TypeError): action_menu(['not a button'])

    def test_pagination_round_trip_and_list_shrink(self):
        first = paginated_menu(self.buttons, page_size=3)
        self.assertEqual((first.page, first.page_count, first.total_items), (0, 3, 8))
        self.assertEqual(first.markup.inline_keyboard[-1][0].callback_data, 'page:1')
        second = paginated_menu(self.buttons, page=page_number('page:1'), page_size=3)
        self.assertEqual([button.callback_data for row in second.markup.inline_keyboard[:-1] for button in row],
                         ['act:key-3', 'act:key-4', 'act:key-5'])
        self.assertEqual([button.callback_data for button in second.markup.inline_keyboard[-1]], ['page:0', 'page:2'])
        shrunk = paginated_menu(self.buttons[:2], page=999, page_size=3)
        self.assertEqual(shrunk.page, 0)
        self.assertEqual([button.callback_data for row in shrunk.markup.inline_keyboard for button in row],
                         ['act:key-0', 'act:key-1'])
        self.assertEqual(paginated_menu([]).markup.inline_keyboard, [])

    def test_page_input_is_not_authority_and_invalid_configuration_rejected(self):
        for data in (None, 'act:1', 'page:-1', 'page:01', 'page:1x', 'page:١', 'page:' + '1' * 60):
            self.assertIsNone(page_number(data))
        self.assertEqual(page_number('catalog:0', prefix='catalog:'), 0)
        for kwargs in ({'page': True}, {'page': -1}, {'page_size': 99}, {'page_size': 0}, {'page_prefix': 'act:'}):
            with self.assertRaises(ValueError): paginated_menu(self.buttons, **kwargs)
        with self.assertRaises(ValueError): paginated_menu(self.buttons, action_prefix='x' * 60 + ':')


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_reply_and_existing_router_preserved_plain_text(self):
        session = StubSession().respond(SendMessage, send_reply)
        bot = Bot(TOKEN, session=session, default=DefaultBotProperties(parse_mode='HTML'))
        dp = Dispatcher()
        existing = Router()
        @existing.message(F.text == '/ping')
        async def ping(event: Message): await event.answer('pong', parse_mode=None)
        dp.include_router(existing)
        dp.include_router(command_router([
            CommandReply('start', 'Старт', 'Первый <plain>'),
            CommandReply('help', 'Помощь', 'Второй <plain>')]))
        async with bot:
            for index, text in enumerate(('/start', '/help', '/ping')):
                await dp.feed_update(bot, Update(update_id=index, message=message(text)))
            await dp.feed_update(bot, Update(update_id=4, message=message()))
        self.assertEqual([method.text for method in session.calls], ['Первый <plain>', 'Второй <plain>', 'pong'])
        self.assertTrue(all(method.parse_mode is None for method in session.calls))

    async def test_mentions_reject_other_bot_and_keyboard_snapshot(self):
        session = StubSession().respond(GetMe, BOT_USER).respond(SendMessage, send_reply)
        bot = Bot(TOKEN, session=session)
        keyboard = action_menu([ActionButton('Исходная', 'old')])
        dp = Dispatcher()
        dp.include_router(command_router([CommandReply('help', 'Помощь', 'Ответ', keyboard)]))
        keyboard.inline_keyboard[0][0].text = 'Измененная'
        async with bot:
            await dp.feed_update(bot, Update(update_id=1, message=message('/help@other_bot')))
            await dp.feed_update(bot, Update(update_id=2, message=message('/help@component_bot')))
        sends = [method for method in session.calls if isinstance(method, SendMessage)]
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0].reply_markup.inline_keyboard[0][0].text, 'Исходная')

    def test_menu_matches_router_definitions_and_preflight_limits(self):
        specs = [CommandReply('start', 'Начать', 'Добро пожаловать'), CommandReply('help', 'Помощь', 'Помощь')]
        self.assertEqual([(item.command, item.description) for item in command_menu(specs)],
                         [('start', 'Начать'), ('help', 'Помощь')])
        for values in ([], [specs[0], specs[0]]):
            with self.assertRaises(ValueError): command_router(values)
        for command in ('/start', 'Start', 'команда', 'x' * 33):
            with self.assertRaises(ValueError): CommandReply(command, 'Описание', 'Ответ')
        with self.assertRaises(ValueError): CommandReply('help', ' ', 'Ответ')
        with self.assertRaises(ValueError): CommandReply('help', 'Помощь', '😀' * 2049)
        with self.assertRaises(ValueError): CommandReply('help', 'Помощь', '\ud800')


class StubTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_models_from_dict_and_unexpected_method_failure(self):
        session = StubSession().respond(SendMessage, send_reply)
        async with Bot(TOKEN, session=session) as bot:
            response = await bot.send_message(42, 'Ответ')
            self.assertIsInstance(response, Message)
            self.assertEqual(response.chat.id, 42)
            self.assertEqual(response.date, DATE)
            with self.assertRaisesRegex(AssertionError, 'Unexpected Telegram method: GetMe'): await bot.get_me()
        self.assertEqual([type(method) for method in session.calls], [SendMessage, GetMe])

    async def test_async_response_and_invalid_return_type(self):
        async def respond(method):
            await asyncio.sleep(0)
            return True
        session = StubSession().respond(AnswerCallbackQuery, respond).respond(SendMessage, 'wrong-type')
        async with Bot(TOKEN, session=session) as bot:
            self.assertTrue(await bot.answer_callback_query('fixture'))
            with self.assertRaises(ValidationError): await bot.send_message(42, 'Fixture')

    async def test_no_file_http_fallback_and_no_calls_after_close(self):
        session = StubSession()
        with self.assertRaisesRegex(AssertionError, 'File streaming'):
            async for _ in session.stream_content('https://example.invalid/file'): pass
        await session.close()
        with self.assertRaisesRegex(RuntimeError, 'closed'): await Bot(TOKEN, session=session).get_me()
        self.assertEqual(session.calls, [])


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_task_cancellation_stops_sdk_polling_children(self):
        entered = asyncio.Event()
        cancelled = asyncio.Event()
        async def updates(method):
            entered.set()
            try:
                await asyncio.sleep(3600)
            finally:
                cancelled.set()
        session = StubSession().respond(GetMe, BOT_USER).respond(GetUpdates, updates)
        task = asyncio.create_task(run_bot(Dispatcher(), BotSettings(TOKEN), session=session, handle_signals=False))
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
        self.assertTrue(session.closed)
        self.assertTrue(cancelled.is_set(), 'SDK child polling task survived run_bot cancellation')

    async def test_cancellation_during_blocked_startup_is_bounded(self):
        entered = asyncio.Event()
        cancelled = asyncio.Event()
        async def startup():
            entered.set()
            try:
                await asyncio.sleep(3600)
            finally:
                cancelled.set()
        session = StubSession().respond(GetMe, BOT_USER)
        dp = Dispatcher()
        dp.startup.register(startup)
        task = asyncio.create_task(run_bot(dp, BotSettings(TOKEN), session=session,
                                          handle_signals=False, shutdown_timeout=0.05))
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        self.assertTrue(session.closed)
        self.assertTrue(cancelled.is_set())

    async def test_real_polling_with_synthetic_transport_and_command_registration(self):
        handled = asyncio.Event()
        delivered = False
        async def updates(method):
            nonlocal delivered
            if not delivered:
                delivered = True
                return [Update(update_id=1, message=message('/help'))]
            await asyncio.sleep(3600)  # Cancelled by the real Dispatcher shutdown.
        session = (StubSession().respond(GetMe, BOT_USER).respond(GetUpdates, updates)
                   .respond(SetMyCommands, True).respond(SendMessage, send_reply))
        dp = Dispatcher()
        router = Router()
        service = object()
        @router.message(F.text == '/help')
        async def handle(event: Message, application_service):
            self.assertIs(application_service, service)
            await event.answer('Обработано', parse_mode=None)
            handled.set()
        dp.include_router(router)
        commands = command_menu([CommandReply('help', 'Помощь', 'Ответ')])
        task = asyncio.create_task(run_bot(dp, BotSettings(TOKEN), session=session, commands=commands,
                                          workflow_data={'application_service': service}, handle_signals=False))
        try:
            await asyncio.wait_for(handled.wait(), timeout=5)
            await dp.stop_polling()
            await asyncio.wait_for(task, timeout=5)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(session.closed)
        self.assertEqual([type(call) for call in session.calls[:2]], [GetMe, SetMyCommands], 'one cached getMe')
        self.assertEqual(sum(isinstance(call, GetMe) for call in session.calls), 1)
        self.assertEqual([call.text for call in session.calls if isinstance(call, SendMessage)], ['Обработано'])
        self.assertFalse(any(type(call).__name__ == 'DeleteWebhook' for call in session.calls))

    async def test_no_menu_change_without_opt_in_and_close_on_failure_or_cancel(self):
        for error in (RuntimeError('polling failure'), asyncio.CancelledError()):
            session = StubSession().respond(GetMe, BOT_USER)
            dp = Dispatcher()
            with patch.object(dp, 'start_polling', new=AsyncMock(side_effect=error)) as polling:
                with self.assertRaises(type(error)):
                    await run_bot(dp, BotSettings(TOKEN), session=session, handle_as_tasks=False)
                self.assertFalse(polling.call_args.kwargs['close_bot_session'])
                self.assertFalse(polling.call_args.kwargs['handle_as_tasks'])
            self.assertTrue(session.closed)
            self.assertEqual([type(call) for call in session.calls], [GetMe])

    async def test_menu_failure_closes_session_before_polling(self):
        session = StubSession().respond(GetMe, BOT_USER)  # Intentionally no SetMyCommands response.
        dp = Dispatcher()
        with patch.object(dp, 'start_polling', new=AsyncMock()) as polling:
            with self.assertRaises(AssertionError):
                await run_bot(dp, BotSettings(TOKEN), session=session, commands=[])
            polling.assert_not_called()
        self.assertTrue(session.closed)
        self.assertEqual([type(call) for call in session.calls], [GetMe, SetMyCommands])

    async def test_rejected_token_or_unreachable_api_stops_before_menu_and_polling(self):
        secret = '100:SECRET_TOKEN_VALUE'
        for raised, expected in ((TelegramUnauthorizedError(GetMe(), 'Unauthorized'), AuthenticationRequired),
                                 (TelegramNetworkError(GetMe(), f'ConnectionTimeoutError: https://api.telegram.org/bot{secret}/getMe'), TransportFailure)):
            def fail(method, error=raised): raise error
            session = StubSession().respond(GetMe, fail)
            dp = Dispatcher()
            with patch.object(dp, 'start_polling', new=AsyncMock()) as polling:
                with self.assertRaises(expected) as caught:
                    await run_bot(dp, BotSettings(secret), session=session, commands=[])
                polling.assert_not_called()
            self.assertTrue(session.closed)
            self.assertEqual([type(call) for call in session.calls], [GetMe])
            self.assertIsNone(caught.exception.__context__)
            self.assertNotIn('SECRET_TOKEN_VALUE', ''.join(traceback.format_exception(caught.exception)))

    async def test_token_check_can_be_skipped_explicitly(self):
        session = StubSession()
        dp = Dispatcher()
        with patch.object(dp, 'start_polling', new=AsyncMock()):
            await run_bot(dp, BotSettings(TOKEN), session=session, verify_token=False)
        self.assertEqual(session.calls, [])
        with self.assertRaises(ValueError):
            await run_bot(Dispatcher(), BotSettings(TOKEN), session=StubSession(), verify_token=1)

    async def test_bad_workflow_or_concurrency_rejected_before_ownership(self):
        session = StubSession()
        for kwargs in ({'workflow_data': {'close_bot_session': True}}, {'tasks_concurrency_limit': True},
                       {'tasks_concurrency_limit': 0}, {'polling_timeout': 0}):
            with self.assertRaises(ValueError):
                await run_bot(Dispatcher(), BotSettings(TOKEN), session=session, **kwargs)
        self.assertFalse(session.closed)
        self.assertEqual(session.calls, [])


if __name__ == '__main__': unittest.main(verbosity=2)
