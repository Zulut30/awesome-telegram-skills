"""Attach a literal report handler to the host Dispatcher; no polling on import."""
from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.methods import SendMessage
from telegram_patterns import FormattedText, MessageBuilder


def compose_report(name: str, notes: str, *, emoji_id: str | None = None) -> tuple[FormattedText, ...]:
    # Both values are literal, even when they contain Telegram markup.
    builder = MessageBuilder().style('Отчет\n', 'bold').text('Имя: ').style(name, 'italic')
    builder = builder.text('\nЗаметки:\n').text(notes).text('\n').style('Документация', 'text_link', url='https://core.telegram.org/bots/api')
    if emoji_id is not None:
        # Host inspects sticker metadata to choose its valid regular emoji fallback.
        builder = builder.text(' ').custom_emoji('👍', emoji_id)
    return builder.build().split()


def attach_reports(dispatcher: Dispatcher) -> Router:
    router = Router(name='message-report')

    private = (F.chat.type == 'private') & (F.message_thread_id == None) & (F.is_topic_message != True) & (F.business_connection_id == None)
    @router.message(Command('report'), private)
    async def report(message: Message):
        if message.from_user is None or message.from_user.is_bot:
            return
        # Example policy: only a public synthetic report, no private records/ACL claim.
        chunks = compose_report(message.from_user.full_name, '<b>буквальный текст</b> *_ [] & 😀\n' * 160)
        for chunk in chunks:
            # Explicit None overrides host HTML/MarkdownV2 defaults. SDK validates JSON.
            # Delivery may stop after a partial prefix. Never retry the whole sequence blindly.
            await message.bot(SendMessage.model_validate({'chat_id': message.chat.id, **chunk.as_kwargs()}))

    dispatcher.include_router(router)
    return router
