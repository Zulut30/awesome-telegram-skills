"""python-telegram-bot: community service messages (Bot API 10.2-10.3) from Message.api_kwargs; no polling on import."""
from collections.abc import Awaitable, Callable
from typing import Any

from telegram import Message, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

Save = Callable[[int, dict[str, Any] | None], Awaitable[None]]  # (chat_id, {'id', 'name'} or None)
Joined = Callable[[int, int, dict[str, Any]], Awaitable[None]]


def attach_community_events(application: Application, *, save: Save, joined: Joined) -> None:  # type: ignore[type-arg]
    """Fields unknown to python-telegram-bot 22.8 keep their Bot API JSON in api_kwargs."""

    async def service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message: Message | None = update.effective_message  # message or channel_post
        if message is None:
            return
        extra = message.api_kwargs
        if isinstance(extra.get('community_chat_added'), dict):
            await save(message.chat.id, extra['community_chat_added']['community'])
        elif 'community_chat_removed' in extra:
            await save(message.chat.id, None)  # the event names no community: the stored link says which
        elif isinstance(extra.get('community_chat_joined'), dict) and message.from_user is not None and not message.from_user.is_bot:
            await joined(message.chat.id, message.from_user.id, extra['community_chat_joined']['community'])

    async def show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        chat = await context.bot.get_chat(message.chat.id)
        community = chat.api_kwargs.get('community')  # ChatFullInfo.community, also unknown to this release
        await save(message.chat.id, community if isinstance(community, dict) else None)
        await message.reply_text(f'Группа входит в сообщество «{community["name"]}».' if isinstance(community, dict)
                                 else 'Группа не входит в сообщество.')

    application.add_handler(CommandHandler('community', show, filters=filters.ChatType.GROUPS))
    # Service messages arrive regardless of privacy mode; in a channel only to an administrator bot.
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, service), group=1)
