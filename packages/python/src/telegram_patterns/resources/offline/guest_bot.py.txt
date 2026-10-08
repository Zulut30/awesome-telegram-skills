"""Guest mode: answer once when summoned in a chat the bot is not a member of; no polling on import."""
from typing import Awaitable, Callable

from aiogram import Bot, Dispatcher, Router
from aiogram.methods import AnswerGuestQuery
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, Message

# reply(summoning text, text of the replied-to message or None) -> answer; claim(guest_query_id) -> first time?
Reply = Callable[[str, str | None], Awaitable[str]]
Claim = Callable[[str], Awaitable[bool]]


def attach_guest_replies(dispatcher: Dispatcher, *, reply: Reply, claim: Claim) -> Router:
    """guest_message is its own update type: ordinary message handlers never see it, and it sees nothing else."""
    router = Router(name='guest-replies')

    @router.guest_message()
    async def guest(message: Message, bot: Bot) -> None:
        query_id = message.guest_query_id
        if not query_id:
            return
        # The update carries the summoning message and, if present, the message it replies to; no history.
        replied = message.reply_to_message
        context = (replied.text or replied.caption) if replied is not None else None
        answer = await reply(message.text or message.caption or '', context)
        # One reply per summon: claim durably before the call, so a redelivery or a lost response sends nothing twice.
        if not await claim(query_id):
            return
        result = InlineQueryResultArticle(id='answer', title='Ответ',
                                          input_message_content=InputTextMessageContent(message_text=answer[:4096]))
        await bot(AnswerGuestQuery(guest_query_id=query_id, result=result))

    dispatcher.include_router(router)
    return router
