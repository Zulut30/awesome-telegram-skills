"""Actual Dispatcher, SDK serialization and a scripted model stream; HTTP fallback is disabled."""
import asyncio
from datetime import datetime, timezone
import json
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage, SendMessageDraft
from aiogram.types import Chat, Message, MessageGenerationStopped, Update, User
from telegram_patterns.testing import StubSession
from ai_stream_bot import STOPPED, attach_ai_stream


class Model:
    """Scripted stand-in for an LLM client: pieces, optional gate, failure and close tracking."""
    def __init__(self):
        self.gates, self.closed, self.histories, self.fail = {}, [], [], set()
        self.scripts = {'длинный ответ': ['x' * 3000, 'y' * 3000]}

    async def generate(self, user_id, history, prompt):
        self.histories.append((user_id, history))
        try:
            for index, piece in enumerate(self.scripts.get(prompt) or prompt.split('|')):
                gate = self.gates.get((user_id, index))
                if gate is not None:
                    await gate.wait()
                if prompt in self.fail and index == 1:
                    raise RuntimeError('model fixture failure')
                yield piece
        finally:
            self.closed.append(prompt)  # the host closes its HTTP stream here, stopping token spend


async def settle():
    for _ in range(20):
        await asyncio.sleep(0)


async def main():
    session = StubSession()
    bot = Bot('100:AI_STREAM_FIXTURE', session=session)
    dispatcher = Dispatcher()
    model = Model()
    allowed = {42: True, 43: True, 44: True, 45: False}
    async def allow(user_id): return allowed.get(user_id, False)
    logs = []
    class Collect(logging.Handler):
        def emit(self, record): logs.append(record.getMessage())
    log = logging.getLogger('ai_stream_bot'); log.addHandler(Collect()); log.propagate = False
    stream = attach_ai_stream(dispatcher, model.generate, allow, max_active=1, max_waiting=1, draft_interval=0)
    drafts, sent, retry_once = [], [], [True]
    def on_draft(method):
        if method.text == 'throttle' and retry_once[0]:
            retry_once[0] = False
            raise TelegramRetryAfter(method=method, message='Too Many Requests', retry_after=0)
        drafts.append((method.chat_id, method.draft_id, method.text, method.can_stop, method.parse_mode))
        return True
    def on_message(method):
        assert method.parse_mode is None and len(method.text) <= 4096
        sent.append((method.chat_id, method.text))
        return {'message_id': 1000 + len(sent), 'date': 1, 'chat': {'id': method.chat_id, 'type': 'private'}, 'text': method.text}
    session.respond(SendMessageDraft, on_draft).respond(SendMessage, on_message)
    def incoming(user, text, message_id, *, chat_type='private'):
        return Update(update_id=message_id, message=Message(message_id=message_id, date=datetime(2026, 10, 7, tzinfo=timezone.utc),
            chat=Chat(id=user, type=chat_type), from_user=User(id=user, is_bot=False, first_name='U'), text=text))
    def stopped(chat, draft_id):
        return Update(update_id=900 + draft_id, stopped_message_generation=MessageGenerationStopped(
            chat=Chat(id=chat, type='private'), draft_id=draft_id))
    try:
        # 1. Streaming: «Thinking…» placeholder, growing drafts with a stop button, then sendMessage persists.
        await dispatcher.feed_update(bot, incoming(42, 'При|вет|!', 1))
        await stream.drain()
        assert [d[2] for d in drafts] == ['', 'При', 'Привет', 'Привет!']
        assert all(d[:2] == (42, 1) and d[3] is True and d[4] is None for d in drafts)
        assert sent == [(42, 'Привет!')]
        # 2. One generation per chat; 3. the user stops it mid-stream.
        model.gates[(42, 1)] = asyncio.Event()
        await dispatcher.feed_update(bot, incoming(42, 'Длинный| ответ', 2))
        await settle()
        await dispatcher.feed_update(bot, incoming(42, 'Еще вопрос', 3))
        assert sent[-1][1].startswith('Я еще отвечаю')
        drafts_before_stop = len(drafts)
        await dispatcher.feed_update(bot, stopped(42, 999))  # stale draft id: ignored
        await dispatcher.feed_update(bot, stopped(77, 2))  # another chat: ignored
        await settle()
        assert 42 in stream._active and not stream._active[42].stopped
        await dispatcher.feed_update(bot, stopped(42, 2))
        await stream.drain()
        assert 'Длинный| ответ' in model.closed and sent[-1] == (42, 'Длинный' + STOPPED)
        assert len(drafts) == drafts_before_stop  # no preview after the stop
        # 4. Model failure: a clear message, nothing stored as an answer.
        model.fail.add('a|b')
        await dispatcher.feed_update(bot, incoming(43, 'a|b', 4))
        await stream.drain()
        assert sent[-1] == (43, 'Не удалось получить ответ. Попробуйте еще раз.') and 43 not in stream._history
        assert logs == ['generation failed: RuntimeError']  # the prompt never reaches the log
        # 5. Budget refusal before any draft or model call.
        calls = len(model.histories)
        await dispatcher.feed_update(bot, incoming(45, 'дорого', 5))
        assert sent[-1][1].startswith('Лимит запросов') and len(model.histories) == calls
        # 6. Bounded queue: one active, one waiting with a placeholder, the third is refused.
        model.gates[(42, 0)] = asyncio.Event()
        await dispatcher.feed_update(bot, incoming(42, 'первый', 6))
        await settle()
        await dispatcher.feed_update(bot, incoming(43, 'второй', 7))
        await settle()
        assert stream._waiting == 1 and drafts[-1][:3] == (43, 7, '')
        await dispatcher.feed_update(bot, incoming(44, 'третий', 8))
        assert sent[-1] == (44, 'Сейчас много запросов. Попробуйте через минуту.')
        model.gates[(42, 0)].set()
        await stream.drain()
        await stream.drain()
        assert (42, 'первый') in sent and (43, 'второй') in sent
        # 7. A 429 on a preview pauses previews; the answer still arrives.
        await dispatcher.feed_update(bot, incoming(44, 'throttle', 9))
        await stream.drain()
        assert retry_once == [False] and sent[-1] == (44, 'throttle')
        # 8. History is bounded and /forget removes it before the next prompt.
        assert model.histories[-1] == (44, ())
        await dispatcher.feed_update(bot, incoming(42, 'снова', 10))
        await stream.drain()
        assert model.histories[-1][1][-1] == ('первый', 'первый')
        await dispatcher.feed_update(bot, incoming(42, '/forget', 11))
        await dispatcher.feed_update(bot, incoming(42, 'с чистого листа', 12))
        await stream.drain()
        assert model.histories[-1] == (42, ())
        # 9. Long answers are split for sendMessage; every draft stays within 4096; long prompts are refused.
        await dispatcher.feed_update(bot, incoming(43, 'длинный ответ', 13))
        await stream.drain()
        assert [len(text) for chat, text in sent[-2:]] == [4096, 1904] and max(len(d[2]) for d in drafts) <= 4096
        await dispatcher.feed_update(bot, incoming(43, 'z' * 4001, 16))
        assert sent[-1][1].startswith('Слишком длинный вопрос')
        # 10. Groups get no drafts; shutdown cancels without sending on the bot's behalf.
        count = len(sent)
        await dispatcher.feed_update(bot, incoming(-100, 'в группе', 14, chat_type='supergroup'))
        model.gates[(42, 0)] = asyncio.Event()
        await dispatcher.feed_update(bot, incoming(42, 'до остановки', 15))
        await settle()
        await dispatcher.emit_shutdown()
        assert len(sent) == count and not stream._active and 'до остановки' in model.closed
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': session.closed, 'drafts': len(drafts),
                      'messages': len(sent), 'stop_closes_model_stream': True, 'stale_stop_ignored': True,
                      'one_generation_per_chat': True, 'bounded_queue': True, 'budget_checked_first': True,
                      'preview_429_paused': True, 'history_forget': True, 'prompt_not_logged': True, 'long_answer_split': True,
                      'shutdown_cancels': True}))


if __name__ == '__main__': asyncio.run(main())
