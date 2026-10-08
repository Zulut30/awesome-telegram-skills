"""Stream a generated answer with sendMessageDraft and a stop button; no polling on import.

The host supplies `generate(user_id, history, prompt)` — an async iterator of text pieces from
its model client — and `allow(user_id)` for its budget policy. A draft is a 30-second ephemeral
preview in a private chat; only sendMessage persists the answer.
"""
from __future__ import annotations

import asyncio
from collections import deque
from contextlib import aclosing
from dataclasses import dataclass
import logging
import time
from typing import AsyncIterator, Awaitable, Callable

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.methods import SendMessage, SendMessageDraft
from aiogram.types import Message, MessageGenerationStopped
from telegram_patterns import MessageBuilder

History = tuple[tuple[str, str], ...]
Generate = Callable[[int, History, str], AsyncIterator[str]]
Allow = Callable[[int], Awaitable[bool]]
STOPPED = '\n\n(генерация остановлена)'
logger = logging.getLogger(__name__)


@dataclass
class _Generation:
    chat_id: int
    draft_id: int
    task: asyncio.Task | None = None
    text: str = ''
    stopped: bool = False


def _chunks(text: str):
    # LLM output is untrusted: literal text, parse_mode=None, at most 4096 UTF-16 units per part.
    return MessageBuilder().text(text).build().split()


class AiStream:
    def __init__(self, generate: Generate, allow: Allow, *, max_active: int = 4, max_waiting: int = 8,
                 max_turns: int = 6, max_prompt: int = 4000, draft_interval: float = 0.5,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._generate, self._allow, self._clock = generate, allow, clock
        self._slots = asyncio.Semaphore(max_active)
        self._capacity, self._waiting = max_active + max_waiting, 0
        self._max_turns, self._max_prompt, self._interval = max_turns, max_prompt, draft_interval
        self._active: dict[int, _Generation] = {}  # one generation per private chat
        self._history: dict[int, deque[tuple[str, str]]] = {}  # memory only; host may persist with consent
        self._previews_paused_until = 0.0

    def router(self) -> Router:
        router = Router(name='ai-stream')
        private = (F.chat.type == 'private') & (F.business_connection_id == None) & (F.from_user.is_bot == False)

        @router.message(Command('forget'), private)
        async def forget(message: Message) -> None:
            self._history.pop(message.from_user.id, None)
            await message.answer('История диалога удалена.', parse_mode=None)

        @router.message(private, F.text, ~F.text.startswith('/'))
        async def ask(message: Message) -> None:
            user_id, prompt = message.from_user.id, message.text
            if message.chat.id in self._active:
                await message.answer('Я еще отвечаю на прошлый вопрос: дождитесь ответа или нажмите «Остановить».', parse_mode=None)
                return
            if len(prompt) > self._max_prompt:
                await message.answer(f'Слишком длинный вопрос: не больше {self._max_prompt} символов.', parse_mode=None)
                return
            if not await self._allow(user_id):
                await message.answer('Лимит запросов на сегодня исчерпан.', parse_mode=None)
                return
            if len(self._active) >= self._capacity:
                await message.answer('Сейчас много запросов. Попробуйте через минуту.', parse_mode=None)
                return
            generation = _Generation(message.chat.id, message.message_id)  # message_id is non-zero
            self._active[message.chat.id] = generation
            # Managed task: the handler returns at once, so the stop update can arrive meanwhile.
            generation.task = asyncio.create_task(self._run(message.bot, generation, user_id, prompt))

        @router.stopped_message_generation()
        async def stop(event: MessageGenerationStopped) -> None:
            generation = self._active.get(event.chat.id)
            if generation is None or generation.draft_id != event.draft_id or generation.task is None:
                return  # a stale or foreign draft changes nothing
            generation.stopped = True
            generation.task.cancel()

        return router

    async def _draft(self, bot: Bot, generation: _Generation) -> None:
        if self._clock() < self._previews_paused_until:
            return
        parts = _chunks(generation.text)
        fields = parts[-1].as_kwargs() if parts else {'text': '', 'parse_mode': None}  # empty text shows «Thinking…»
        try:
            await bot(SendMessageDraft(chat_id=generation.chat_id, draft_id=generation.draft_id, can_stop=True, **fields))
        except TelegramRetryAfter as error:
            self._previews_paused_until = self._clock() + error.retry_after
        except TelegramAPIError:
            pass  # previews are best effort; the final message carries the answer

    async def _run(self, bot: Bot, generation: _Generation, user_id: int, prompt: str) -> None:
        history = tuple(self._history.get(user_id, ()))
        try:
            await self._draft(bot, generation)
            self._waiting += 1
            try:
                await self._slots.acquire()
            finally:
                self._waiting -= 1
            try:
                last = float('-inf')
                async with aclosing(self._generate(user_id, history, prompt)) as pieces:
                    async for piece in pieces:
                        generation.text += piece
                        if self._clock() - last >= self._interval:
                            await self._draft(bot, generation)
                            last = self._clock()
            finally:
                self._slots.release()
            answer = generation.text
        except asyncio.CancelledError:
            if not generation.stopped:
                raise  # shutdown: nothing is sent on the bot's behalf
            answer = generation.text + STOPPED  # aclosing() has already closed the model stream
        except Exception as error:
            logger.warning('generation failed: %s', type(error).__name__)  # category only, never the prompt
            await self._send(bot, generation.chat_id, 'Не удалось получить ответ. Попробуйте еще раз.')
            return
        finally:
            if self._active.get(generation.chat_id) is generation:
                del self._active[generation.chat_id]
        self._history.setdefault(user_id, deque(maxlen=self._max_turns)).append((prompt, answer))
        await self._send(bot, generation.chat_id, answer.strip() or 'Пустой ответ.')

    async def _send(self, bot: Bot, chat_id: int, text: str) -> None:
        for part in _chunks(text):
            try:
                await bot(SendMessage(chat_id=chat_id, **part.as_kwargs()))
            except TelegramAPIError:
                return  # the outcome may be unknown: no blind resend of an answer the user may have

    async def drain(self) -> None:
        """Wait for the current generations; tests and graceful restarts use it."""
        tasks = [item.task for item in self._active.values() if item.task is not None]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self) -> None:
        for item in list(self._active.values()):
            if item.task is not None:
                item.task.cancel()
        await self.drain()


def attach_ai_stream(dispatcher: Dispatcher, generate: Generate, allow: Allow, **options) -> AiStream:
    stream = AiStream(generate, allow, **options)
    dispatcher.include_router(stream.router())
    dispatcher.shutdown.register(stream.close)
    return stream
