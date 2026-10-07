"""The standalone aiogram example in telegram-ai-bot streams drafts, stops on request and persists the answer."""

import asyncio
import re
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage, SendMessageDraft
from aiogram.types import Chat, Message, MessageGenerationStopped, Update, User

from telegram_patterns.testing import StubSession

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / '.agents/skills/telegram-ai-bot/references/streaming.md'


def load_example() -> types.ModuleType:
    code = re.search(r'<!-- ai-stream:run -->\n```python\n(.*?)\n```', PAGE.read_text(encoding='utf-8'), re.S).group(1)
    module = types.ModuleType('ai_stream_reference')
    exec(compile(code, str(PAGE), 'exec'), module.__dict__)
    return module


def ask(chat: int, text: str, message_id: int) -> Update:
    return Update(
        update_id=message_id,
        message=Message(
            message_id=message_id,
            date=datetime(2026, 10, 7, tzinfo=timezone.utc),
            chat=Chat(id=chat, type='private'),
            from_user=User(id=chat, is_bot=False, first_name='U'),
            text=text,
        ),
    )


def stopped(chat: int, draft_id: int) -> Update:
    return Update(
        update_id=500 + draft_id,
        stopped_message_generation=MessageGenerationStopped(chat=Chat(id=chat, type='private'), draft_id=draft_id),
    )


async def settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


class AiStreamReferenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.example = load_example()
        self.gate, self.closed, self.drafts, self.sent, self.throttle = asyncio.Event(), [], [], [], [True]

        async def generate(prompt):
            try:
                for index, piece in enumerate(prompt.split('|')):
                    if prompt.startswith('wait') and index == 1:
                        await self.gate.wait()
                    if prompt == 'fail|x' and index == 1:
                        raise RuntimeError('model fixture failure')
                    yield piece
            finally:
                self.closed.append(prompt)

        def on_draft(method):
            if self.throttle[0] and method.text == 'slow':
                self.throttle[0] = False
                raise TelegramRetryAfter(method=method, message='Too Many Requests', retry_after=60)
            self.drafts.append((method.chat_id, method.draft_id, method.text, method.can_stop, method.parse_mode))
            return True

        def on_message(method):
            self.sent.append((method.chat_id, method.text, method.parse_mode))
            return {
                'message_id': 900 + len(self.sent),
                'date': 1,
                'chat': {'id': method.chat_id, 'type': 'private'},
                'text': method.text,
            }

        self.session = StubSession().respond(SendMessageDraft, on_draft).respond(SendMessage, on_message)
        self.bot = Bot('100:AI_REFERENCE_FIXTURE', session=self.session)
        self.dispatcher = Dispatcher()
        self.denied = {46}

        async def allow(user_id, prompt):
            return user_id not in self.denied and len(prompt) <= 4000

        self.dispatcher.include_router(self.example.ai_router(generate, allow, interval=0, max_active=1, max_waiting=1))

    async def asyncTearDown(self):
        await self.bot.session.close()

    async def finish(self):
        await settle()
        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def test_drafts_grow_then_send_message_persists_literal_answer(self):
        await self.dispatcher.feed_update(self.bot, ask(42, 'При|вет <b>', 7))
        await self.finish()
        self.assertEqual([d[2] for d in self.drafts], ['При', 'Привет <b>'])
        self.assertTrue(all(d[:2] == (42, 7) and d[3] is True and d[4] is None for d in self.drafts))
        self.assertEqual(self.sent, [(42, 'Привет <b>', None)])

    async def test_stop_closes_model_stream_and_ignores_foreign_drafts(self):
        await self.dispatcher.feed_update(self.bot, ask(42, 'wait|rest', 8))
        await settle()
        await self.dispatcher.feed_update(self.bot, ask(42, 'second', 9))
        self.assertTrue(self.sent[-1][1].startswith('Я еще отвечаю'))
        await self.dispatcher.feed_update(self.bot, stopped(42, 1))
        await self.dispatcher.feed_update(self.bot, stopped(77, 8))
        await settle()
        self.assertEqual(self.closed, [])
        await self.dispatcher.feed_update(self.bot, stopped(42, 8))
        await self.finish()
        self.assertEqual(self.closed, ['wait|rest'])
        self.assertEqual(self.sent[-1], (42, 'wait\n\n(генерация остановлена)', None))
        self.assertEqual([d[2] for d in self.drafts], ['wait'])

    async def test_model_failure_429_and_long_answers(self):
        await self.dispatcher.feed_update(self.bot, ask(43, 'fail|x', 10))
        await self.finish()
        self.assertEqual(self.sent[-1][1], 'Не удалось получить ответ. Попробуйте еще раз.')
        await self.dispatcher.feed_update(self.bot, ask(44, 'slow|' + '😀' * 3000, 11))
        await self.finish()
        self.assertFalse(self.throttle[0])
        self.assertEqual([d for d in self.drafts if d[0] == 44], [], 'previews pause for retry_after')
        lengths = [len(text.encode('utf-16-le')) // 2 for chat, text, mode in self.sent[-2:]]
        self.assertEqual(lengths, [4096, 2 * 3000 + 4 - 4096])

    async def test_bounded_queue_and_budget_refusals(self):
        await self.dispatcher.feed_update(self.bot, ask(42, 'wait|one', 13))
        await self.dispatcher.feed_update(self.bot, ask(43, 'two', 14))
        await settle()
        self.assertEqual(self.closed, [], 'the second request waits for a model slot')
        await self.dispatcher.feed_update(self.bot, ask(44, 'three', 15))
        self.assertEqual(self.sent[-1][:2], (44, 'Сейчас много запросов. Попробуйте через минуту.'))
        self.gate.set()
        await self.finish()
        self.assertEqual(self.closed, ['wait|one', 'two'])
        await self.dispatcher.feed_update(self.bot, ask(46, 'дорого', 16))
        self.assertEqual(self.sent[-1][:2], (46, 'Лимит запросов исчерпан.'))
        self.assertEqual(self.closed, ['wait|one', 'two'], 'refused before the model is called')

    async def test_shutdown_cancellation_sends_nothing(self):
        await self.dispatcher.feed_update(self.bot, ask(45, 'wait|never', 12))
        await settle()
        for task in [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]:
            task.cancel()
        await self.finish()
        self.assertEqual(self.sent, [])
        self.assertEqual(self.closed, ['wait|never'])


if __name__ == '__main__':
    unittest.main()
