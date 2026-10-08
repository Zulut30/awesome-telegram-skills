import importlib.util
import json
import unittest
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.methods import SendMessage
from aiogram.types import Update

from telegram_patterns import MessageBuilder
from telegram_patterns.testing import StubSession


class MessageSDKTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session = StubSession()
        self.bot = Bot('100:MESSAGE_SDK_FIXTURE', session=self.session, default=DefaultBotProperties(parse_mode='HTML'))

    async def asyncTearDown(self):
        await self.bot.session.close()

    def response(self, request):
        return {'message_id': 100, 'date': 1, 'chat': {'id': 42, 'type': 'private'}, 'text': request.text}

    async def test_sdk_wire_entities_and_explicit_default_override(self):
        value = MessageBuilder().text('😀 ').style('<b>literal</b>_*', 'bold').build()
        self.session.respond(SendMessage, self.response)
        request = SendMessage.model_validate({'chat_id': 42, **value.as_kwargs()})
        await self.bot(request)
        self.assertIsNone(self.session.prepare_value(request.parse_mode, bot=self.bot, files={}))
        wire = json.loads(self.session.prepare_value(request.entities, bot=self.bot, files={}))
        self.assertEqual(wire, [{'type': 'bold', 'offset': 3, 'length': 16}])
        self.assertEqual(request.text, '😀 <b>literal</b>_*')

    async def test_sdk_custom_emoji_default_fallback_and_opt_in(self):
        value = MessageBuilder().custom_emoji('👍', '123456789').build()
        fallback = SendMessage.model_validate({'chat_id': 42, **value.as_kwargs()})
        native = SendMessage.model_validate({'chat_id': 42, **value.as_kwargs(custom_emoji_entitlement_verified=True)})
        self.assertEqual(fallback.entities, [])
        self.assertEqual(native.entities[0].custom_emoji_id, '123456789')
        self.assertEqual(native.entities[0].length, 2)

    async def test_partial_dispatcher_delivery_stops_at_unknown_chunk(self):
        path = Path(__file__).resolve().parents[3] / 'examples/python/message_text_bot.py'
        spec = importlib.util.spec_from_file_location('message_example', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        dp = Dispatcher()
        module.attach_reports(dp)

        def responder(request):
            if len(self.session.calls) == 2:
                raise TimeoutError('unknown receipt')
            return self.response(request)

        self.session.respond(SendMessage, responder)
        update = Update.model_validate(
            {
                'update_id': 1,
                'message': {
                    'message_id': 1,
                    'date': 1,
                    'chat': {'id': 42, 'type': 'private'},
                    'from': {'id': 42, 'is_bot': False, 'first_name': '<b>literal</b>'},
                    'text': '/report',
                },
            }
        )
        try:
            for changes in (
                {'chat': {'id': -42, 'type': 'group'}},
                {'message_thread_id': 10, 'is_topic_message': True},
                {'is_topic_message': True},
                {'business_connection_id': 'unsupported-business'},
            ):
                raw = update.model_dump(mode='json')
                raw['message'].update(changes)
                await dp.feed_update(self.bot, Update.model_validate(raw))
            self.assertEqual(self.session.calls, [])
            with self.assertRaises(TimeoutError):
                await dp.feed_update(self.bot, update)
            self.assertEqual(len(self.session.calls), 2)
        finally:
            await dp.fsm.close()

    async def test_sdk_split_each_entity_selects_exact_utf16_slice(self):
        value = MessageBuilder().style('😀abc' * 1600, 'italic').build()
        self.session.respond(SendMessage, self.response)
        rebuilt = []
        for chunk in value.split():
            request = SendMessage.model_validate({'chat_id': 42, **chunk.as_kwargs()})
            await self.bot(request)
            raw = request.text.encode('utf-16-le')
            entity = request.entities[0]
            self.assertEqual(
                raw[entity.offset * 2 : (entity.offset + entity.length) * 2].decode('utf-16-le'), request.text
            )
            rebuilt.append(request.text)
        self.assertEqual(''.join(rebuilt), value.text)


if __name__ == '__main__':
    unittest.main()
