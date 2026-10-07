"""Bot-to-bot replies in a group with loop prevention: dedup, a pause per peer and a depth limit; no polling on import."""
import hashlib
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.methods import SendMessage
from aiogram.types import Message, ReplyParameters, TelegramObject

GROUPS = ('group', 'supergroup')
Respond = Callable[[str], Awaitable[str | None]]


class LoopGuard:
    """Counters of one process; several workers keep the same counters in shared storage."""

    def __init__(self, *, max_depth: int = 3, pause: float = 5.0, dedup_window: float = 300.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.max_depth, self.pause, self.dedup_window, self.clock = max_depth, pause, dedup_window, clock
        self.depth: dict[tuple[int, int], int] = {}
        self.last: dict[tuple[int, int], float] = {}
        self.seen: dict[tuple[int, int, str], float] = {}

    def allow(self, chat_id: int, peer_id: int, text: str) -> bool:
        """True if this bot may answer one more message of peer_id in chat_id now; the answer is then counted."""
        now, pair = self.clock(), (chat_id, peer_id)
        self.seen = {key: at for key, at in self.seen.items() if now - at < self.dedup_window}
        key = (chat_id, peer_id, hashlib.sha256(text.encode()).hexdigest())
        if key in self.seen or now - self.last.get(pair, float('-inf')) < self.pause or self.depth.get(pair, 0) >= self.max_depth:
            return False
        self.seen[key], self.last[pair], self.depth[pair] = now, now, self.depth.get(pair, 0) + 1
        return True

    def human(self, chat_id: int) -> None:
        """A person spoke in the chat: bot exchanges there may start again."""
        self.depth = {pair: depth for pair, depth in self.depth.items() if pair[0] != chat_id}


class _PersonResets(BaseMiddleware):
    """Sees every group message before routing, so a person resets the depth even when another handler answers."""

    def __init__(self, guard: LoopGuard) -> None:
        self.guard = guard

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        if isinstance(event, Message) and event.chat.type in GROUPS and event.from_user is not None and not event.from_user.is_bot:
            self.guard.human(event.chat.id)
        return await handler(event, data)


def attach_bot_relay(dispatcher: Dispatcher, *, respond: Respond, guard: LoopGuard) -> Router:
    """respond(text) -> answer or None; messages of other bots arrive only by mention, reply or the mode settings."""
    router = Router(name='bot-relay')

    @router.message(F.chat.type.in_(GROUPS), F.from_user.is_bot, F.text)
    async def from_bot(message: Message, bot: Bot) -> None:
        peer = message.from_user
        if peer is None or peer.id == bot.id or message.text is None:
            return
        if not guard.allow(message.chat.id, peer.id, message.text):
            return  # silence ends the loop; never answer a guard refusal with another message
        answer = await respond(message.text)
        if answer:
            await bot(SendMessage(chat_id=message.chat.id, text=answer, message_thread_id=message.message_thread_id,
                                  reply_parameters=ReplyParameters(message_id=message.message_id)))

    dispatcher.message.outer_middleware(_PersonResets(guard))
    dispatcher.include_router(router)
    return router
