"""Track which community a group or channel belongs to from service messages; no polling on import."""
from typing import Awaitable, Callable

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.methods import GetChat, SendMessage
from aiogram.types import Community, Message

GROUPS = ('group', 'supergroup')
# save(chat_id, community or None) stores the link; joined(chat_id, user_id, community) counts arrivals.
Save = Callable[[int, Community | None], Awaitable[None]]
Joined = Callable[[int, int, Community], Awaitable[None]]


def attach_community_events(dispatcher: Dispatcher, *, save: Save, joined: Joined) -> Router:
    """Service messages arrive regardless of privacy mode; in a channel only to an administrator bot."""
    router = Router(name='community-events')

    @router.message(F.community_chat_added)
    @router.channel_post(F.community_chat_added)
    async def added(message: Message) -> None:
        # The chat (or a bot) now belongs to this community; the id may exceed 32 bits.
        if message.community_chat_added is not None:
            await save(message.chat.id, message.community_chat_added.community)

    @router.message(F.community_chat_removed)
    @router.channel_post(F.community_chat_removed)
    async def removed(message: Message) -> None:
        # CommunityChatRemoved holds no fields: which community is known only from the stored link.
        await save(message.chat.id, None)

    @router.message(F.community_chat_joined)
    async def arrived(message: Message) -> None:
        # A community member joined without an invite link; the service message names the community.
        event = message.community_chat_joined
        if event is not None and message.from_user is not None and not message.from_user.is_bot:
            await joined(message.chat.id, message.from_user.id, event.community)

    @router.message(Command('community'), F.chat.type.in_(GROUPS))
    async def show(message: Message, bot: Bot) -> None:
        # A missed service message is reconciled from getChat; nothing else about the community is readable.
        chat = await bot(GetChat(chat_id=message.chat.id))
        await save(message.chat.id, chat.community)
        text = (f'Группа входит в сообщество «{chat.community.name}».' if chat.community
                else 'Группа не входит в сообщество.')
        await bot(SendMessage(chat_id=message.chat.id, text=text, message_thread_id=message.message_thread_id))

    dispatcher.include_router(router)
    return router
