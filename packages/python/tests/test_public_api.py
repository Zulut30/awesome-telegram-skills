from __future__ import annotations

import unittest
from datetime import datetime, timezone

from aiogram.types import Chat, Message

import telegram_patterns
import telegram_patterns.aiogram as adapters
from telegram_patterns.aiogram import ActionButton, UpdateObserver, action_menu


class PublicImportsTests(unittest.TestCase):
    def test_wildcard_adapters_are_usable_without_incidental_sdk_exports(self):
        imported: dict = {}
        exec('from telegram_patterns.aiogram import *', imported)
        markup = imported['action_menu']([imported['ActionButton']('Open', 'open')])
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, 'act:open')
        self.assertNotIn('asyncio', imported)
        self.assertNotIn('Bot', imported)
        self.assertIn('ChatType', imported)
        self.assertIn('UpdatePhase', imported)

    def test_all_intentional_exports_resolve_and_legacy_explicit_imports_survive(self):
        for module in (telegram_patterns, adapters):
            self.assertEqual(len(module.__all__), len(set(module.__all__)))
            for name in module.__all__:
                with self.subTest(name=name):
                    self.assertIsNotNone(getattr(module, name))
        # An accidental old explicit SDK import is still accessible; new wildcard
        # consumers are instructed to import SDK symbols directly from aiogram.
        from aiogram import Bot as NativeBot

        from telegram_patterns.aiogram import Bot

        self.assertIs(Bot, NativeBot)
        self.assertEqual(action_menu([ActionButton('Open', 'open')]).inline_keyboard[0][0].text, 'Open')


class MiddlewareRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_level_registration_fails_before_recording_or_effect(self):
        records, effects = [], []

        async def record(value):
            records.append(value)

        async def handle(event, data):
            effects.append(event)

        message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=1, type='private'))
        with self.assertRaisesRegex(TypeError, 'dispatcher.update'):
            await UpdateObserver(record)(handle, message, {})
        self.assertEqual(records, [])
        self.assertEqual(effects, [])


if __name__ == '__main__':
    unittest.main()
