from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from _support import integration
from aiogram import Bot, Dispatcher
from aiogram.methods import GetMe
from aiogram.types import (
    CallbackGame,
    CallbackQuery,
    Chat,
    CopyTextButton,
    DisabledButton,
    KeyboardButtonRequestChat,
    KeyboardButtonRequestUsers,
    Message,
    Update,
    User,
    WebAppInfo,
)
from aiogram.types import (
    InlineKeyboardButton as Inline,
)
from aiogram.types import (
    KeyboardButton as Reply,
)

from telegram_patterns.aiogram import (
    InvalidAPIRequest,
    UpdateObserver,
    build_request,
    event_router,
    inline_keyboard,
    input_prompt,
    method_catalog,
    remove_keyboard,
    reply_keyboard,
    update_kinds,
)
from telegram_patterns.testing import StubSession

ROOT = Path(__file__).resolve().parents[3]
DATE = datetime(2026, 10, 4, tzinfo=timezone.utc)


class KeyboardTests(unittest.TestCase):
    def test_two_three_mixed_rows_and_snapshot(self):
        buttons = [Inline(text=str(n), callback_data=str(n)) for n in range(6)]
        for rows, expected in (
            ([buttons[:2], buttons[2:4]], [2, 2]),
            ([buttons[:3], buttons[3:]], [3, 3]),
            ([buttons[:1], buttons[1:3], buttons[3:]], [1, 2, 3]),
        ):
            markup = inline_keyboard(rows)
            self.assertEqual(list(map(len, markup.inline_keyboard)), expected)
        saved = inline_keyboard([buttons[:2]])
        buttons[0].text = 'changed'
        self.assertEqual(saved.inline_keyboard[0][0].text, '0')
        self.assertEqual(reply_keyboard([['A', 'B', 'C']]).keyboard[0][2].text, 'C')

    def test_styles_emoji_fallback_without_mutation(self):
        source = Inline(text='A', callback_data='a', style='success', icon_custom_emoji_id='12345')
        self.assertIsNone(inline_keyboard([[source]]).inline_keyboard[0][0].icon_custom_emoji_id)
        self.assertEqual(source.icon_custom_emoji_id, '12345')
        self.assertEqual(
            inline_keyboard([[source]], emoji_entitlement_verified=True).inline_keyboard[0][0].icon_custom_emoji_id,
            '12345',
        )
        self.assertEqual(reply_keyboard([[Reply(text='A', style='primary')]]).keyboard[0][0].style, 'primary')
        for field in (
            {'style': '#ff0000'},
            {'style': 'blue'},
            {'icon_custom_emoji_id': 'invalid'},
            {'colour': 'green'},
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                inline_keyboard([[Inline(text='A', callback_data='a', **field)]])

    def test_exact_action_utf8_and_copy_limits(self):
        for button in (
            Inline(text='A'),
            Inline(text='A', callback_data='a', url='https://example.invalid'),
            Inline(text='A', callback_data='😀' * 17),
            Inline(text='A', callback_data=''),
            Inline(text='A', copy_text=CopyTextButton(text='x' * 257)),
            Inline(text='A', pay=False),
        ):
            with self.subTest(button=button), self.assertRaises(ValueError):
                inline_keyboard([[button]])
        self.assertEqual(
            inline_keyboard([[Inline(text='A', callback_data='😀' * 16)]]).inline_keyboard[0][0].callback_data,
            '😀' * 16,
        )
        markup = inline_keyboard(
            [
                [Inline(text='Copy', copy_text=CopyTextButton(text='safe'))],
                [Inline(text='Disabled', disabled=DisabledButton())],
            ]
        )
        self.assertIsNotNone(markup.inline_keyboard[1][0].disabled)

    def test_context_invoice_game_and_webapp(self):
        pay = Inline(text='Pay', pay=True)
        with self.assertRaises(ValueError):
            inline_keyboard([[pay]])
        self.assertTrue(inline_keyboard([[pay]], invoice=True).inline_keyboard[0][0].pay)
        for button in (pay, Inline(text='Game', callback_game=CallbackGame())):
            with self.assertRaises(ValueError):
                inline_keyboard([[Inline(text='A', callback_data='a'), button]], invoice=True)
        app = Inline(text='App', web_app=WebAppInfo(url='https://example.invalid'))
        self.assertIsNotNone(inline_keyboard([[app]]).inline_keyboard[0][0].web_app)
        for context in ({'chat_type': 'group'}, {'business': True}):
            with self.assertRaises(ValueError):
                inline_keyboard([[app]], **context)
        with self.assertRaises(ValueError):
            inline_keyboard([[Inline(text='App', web_app=WebAppInfo(url='http://example.invalid'))]])
        with self.assertRaises(ValueError):
            inline_keyboard([[Inline(text='Inline', switch_inline_query='')]], business=True)
        self.assertTrue(inline_keyboard([[Inline(text='A', callback_data='a')]], force_reply=True).force_reply)

    def test_reply_requests_context_ids_and_flags(self):
        users = Reply(text='Users', request_users=KeyboardButtonRequestUsers(request_id=1))
        chat = Reply(text='Chat', request_chat=KeyboardButtonRequestChat(request_id=2, chat_is_channel=False))
        markup = reply_keyboard([[users, chat]], placeholder='Choose', one_time=True, persistent=True)
        self.assertTrue(markup.one_time_keyboard)
        self.assertTrue(markup.is_persistent)
        self.assertEqual(markup.input_field_placeholder, 'Choose')
        self.assertEqual(reply_keyboard([['A']], chat_type='group').keyboard[0][0].text, 'A')
        for rows, kwargs in (
            ([[users]], {'chat_type': 'group'}),
            ([[users]], {'chat_type': 'channel'}),
            ([['A']], {'business': True}),
            ([[users, users]], {}),
            ([[Reply(text='Bad', request_contact=True, request_location=True)]], {}),
            ([[Reply(text='Overflow', request_users=KeyboardButtonRequestUsers(request_id=2**31))]], {}),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                reply_keyboard(rows, **kwargs)
        self.assertTrue(input_prompt('Name').force_reply)
        self.assertTrue(remove_keyboard().remove_keyboard)
        for placeholder in ('', 'x' * 65, '\ud800'):
            with self.assertRaises(ValueError):
                input_prompt(placeholder)

    def test_rows_and_native_serialization(self):
        for rows in ([], [[]], ['A'], [[Inline(text='A', callback_data='a')] * 9]):
            with self.assertRaises((TypeError, ValueError)):
                inline_keyboard(rows)
        self.assertRaises(ValueError, reply_keyboard, [['A']], resize='yes')
        bot = Bot('100:OFFLINE_FIXTURE')
        request = build_request(
            'sendMessage',
            {
                'chat_id': 42,
                'text': 'Fixture',
                'reply_markup': inline_keyboard([[Inline(text='A', callback_data='a', style='primary')]]),
            },
        )
        wire = bot.session.prepare_value(request.reply_markup, bot, {})
        self.assertEqual(json.loads(wire)['inline_keyboard'][0][0]['style'], 'primary')


class CatalogTests(unittest.TestCase):
    def builder(self):
        spec = importlib.util.spec_from_file_location('catalog_builder', ROOT / 'scripts/build_telegram_catalog.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @integration
    def test_generator_real_operations_in_temporary_repository_and_drift(self):
        module = self.builder()
        with tempfile.TemporaryDirectory(prefix='telegram-catalog-fixture-') as directory:
            root = Path(directory)
            for relative in (
                '.agents/skills/telegram-bot-api/references/api-index.json',
                'catalog/mini-app-index.json',
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            module.ROOT = root
            with patch('sys.argv', ['builder']), redirect_stdout(io.StringIO()):
                module.main()
            self.assertEqual(len(list((root / 'recipes/bot-api/methods').glob('*.md'))), 185)
            with patch('sys.argv', ['builder', '--check']), redirect_stdout(io.StringIO()):
                module.main()
            (root / 'recipes/bot-api/methods/getMe.md').write_text('drift', encoding='utf-8')
            with (
                patch('sys.argv', ['builder', '--check']),
                self.assertRaisesRegex(ValueError, 'Generated output drift'),
            ):
                module.main()
            self.assertEqual((root / 'recipes/bot-api/methods/getMe.md').read_text(), 'drift')

    def test_mini_parser_skips_table_header_and_rejects_unmapped_module(self):
        module = self.builder()
        html = '<h3><a name="initializing-mini-apps"></a>Initializing Mini Apps</h3><table>'
        for name in ('ready()', 'showPopup(params[, callback])'):
            html += f'<tr><td>{name}</td><td>Function</td><td>Bot API 6.2+</td></tr>'
        for section, name in (('BackButton', 'show()'), ('LocationManager', 'getLocation(callback)')):
            html += f'</table><h4>{section}</h4><table><tr><td>{name}</td><td>Function</td></tr>'
        html += '</table><h3>Events Available for Mini Apps</h3><table><tr><th>eventType</th><th>Description</th></tr>'
        for name in ('themeChanged', 'viewportChanged'):
            html += f'<tr><td>{name}</td><td>Occurs</td></tr>'
        html += '</table>'
        result = module.mini_index(html)
        self.assertEqual([item['name'] for item in result['events']], ['themeChanged', 'viewportChanged'])
        self.assertEqual(result['methods'][-1]['path'], 'showPopup')
        html += '<h4>FutureModule</h4><table><tr><td>show()</td><td>Function</td></tr></table>'
        self.assertRaisesRegex(ValueError, 'Unmapped', module.mini_index, html)

    def test_all_generated_requests_and_recipes_validate_and_serialize(self):
        module = self.builder()
        fixtures = json.loads((ROOT / 'catalog/bot-api-request-fixtures.json').read_text(encoding='utf-8'))['methods']
        official = json.loads((ROOT / 'catalog/telegram-capabilities.json').read_text(encoding='utf-8'))
        self.assertEqual(set(fixtures), {item.name for item in method_catalog()})
        self.assertEqual(len(fixtures), 185)
        self.assertEqual(len(official['bot_api']['types']), 400)
        bot = Bot('100:OFFLINE_FIXTURE')
        for name, data in fixtures.items():
            with self.subTest(method=name):
                request = build_request(name, module.materialize(data))
                self.assertEqual(request.__api_method__, name)
                files = {}
                for value in request.model_dump(warnings=False).values():
                    bot.session.prepare_value(value, bot, files)
                namespace = {}
                code = (
                    (ROOT / f'recipes/bot-api/methods/{name}.md')
                    .read_text(encoding='utf-8')
                    .split('```python\n', 1)[1]
                    .split('```', 1)[0]
                )
                exec(compile(code, name + '.md', 'exec'), namespace)
                self.assertEqual(namespace['request'].__api_method__, name)

    def test_invalid_request_is_controlled_without_values(self):
        for name, data in (
            ('NONEXISTENT', {}),
            ('sendMessage', {'chat_id': 1, 'text': 'SECRET', 'typo': 'SECRET'}),
            ('sendMessage', {'chat_id': 'SECRET'}),
            ('sendMessage', []),
            ('sendMessage', {1: 'SECRET'}),
        ):
            with self.subTest(name=name), self.assertRaises(InvalidAPIRequest) as failure:
                build_request(name, data)
            self.assertNotIn('SECRET', str(failure.exception))


class EventTests(unittest.IsolatedAsyncioTestCase):
    def update(self):
        return Update(
            update_id=7,
            message=Message(
                message_id=1,
                date=DATE,
                chat=Chat(id=42, type='private'),
                from_user=User(id=42, first_name='Fixture', is_bot=False),
                text='SECRET_TEXT',
            ),
        )

    async def test_dispatcher_records_metadata_and_registered_types(self):
        records = []

        async def record(value):
            records.append(value)

        handled = []

        async def message(event):
            handled.append(event.message_id)

        dispatcher = Dispatcher()
        dispatcher.update.outer_middleware(UpdateObserver(record))
        dispatcher.include_router(event_router({'message': message}))
        self.assertEqual(dispatcher.resolve_used_update_types(), ['message'])
        session = StubSession()
        async with Bot('100:OFFLINE_FIXTURE', session=session) as bot:
            await dispatcher.feed_update(bot, self.update())
            await dispatcher.feed_update(
                bot,
                Update(
                    update_id=8,
                    callback_query=CallbackQuery(
                        id='fixture',
                        from_user=User(id=42, first_name='Fixture', is_bot=False),
                        chat_instance='fixture',
                        data='SECRET_CALLBACK',
                    ),
                ),
            )
        self.assertEqual(handled, [1])
        self.assertEqual([item.phase for item in records], ['received', 'handled', 'received', 'unhandled'])
        self.assertNotIn('SECRET', repr(records))
        self.assertTrue(all(item.actor_id is None and item.chat_id is None for item in records))

    async def test_failure_cancel_and_recorder_failure_preserve_handler(self):
        records = []

        async def record(value):
            records.append(value)

        observer = UpdateObserver(record, include_ids=True)
        for exception, phase in ((RuntimeError('SECRET'), 'failed'), (asyncio.CancelledError(), 'cancelled')):

            async def fail(event, data):
                raise exception

            with self.assertRaises(type(exception)):
                await observer(fail, self.update(), {})
            self.assertEqual(records[-1].phase, phase)
            self.assertEqual(records[-1].actor_id, 42)

        async def broken_record(trace):
            raise RuntimeError('SECRET')

        async def good(event, data):
            return 42

        with self.assertLogs('telegram_patterns.events', level='WARNING') as logs:
            self.assertEqual(await UpdateObserver(broken_record)(good, self.update(), {}), 42)
        self.assertNotIn('SECRET', str(logs.output))

    async def test_all_sdk_kinds_register_without_implicit_subscription(self):
        async def handler(event):
            pass

        kinds = {name: handler for name in Update.model_fields if name != 'update_id'}
        dispatcher = Dispatcher()
        dispatcher.include_router(event_router(kinds))
        self.assertEqual(set(dispatcher.resolve_used_update_types()), set(kinds))
        self.assertIn('message_reaction', kinds)
        self.assertEqual(update_kinds(self.update()), ('message',))
        for invalid in ({}, {'typing': handler}, {'update_id': handler}, {'message': None}):
            self.assertRaises(ValueError, event_router, invalid)

    async def test_generic_builder_uses_existing_bot_transport(self):
        session = StubSession().respond(GetMe, User(id=100, first_name='Fixture', is_bot=True))
        async with Bot('100:OFFLINE_FIXTURE', session=session) as bot:
            result = await bot(build_request('getMe'))
        self.assertEqual(result.id, 100)
        self.assertTrue(session.closed)
