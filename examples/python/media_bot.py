"""Attach media examples to the existing Dispatcher; no polling on import."""
import base64
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from telegram_patterns import MessageBuilder, safe_error_report
from telegram_patterns.aiogram import MediaFile, MediaItem, media_request, media_album, media_edit, download_media

# Public synthetic fixtures. Real uploads need the host's content/codec checks.
PHOTO = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=')
DOCUMENT = b'Telegram media example.\n'


async def send_media_demo(bot: Bot, chat_id: int) -> None:
    caption = MessageBuilder().text('😀 ').style('Фото <буквально>_*', 'bold').build()
    photo = MediaItem(MediaFile('photo', PHOTO, filename='sample.png', width=1, height=1), caption)
    document = MediaItem(MediaFile('document', DOCUMENT, filename='sample.txt'),
                         MessageBuilder().text('Документ без потери исходных байтов').build())
    await bot(media_request(photo, bot_id=bot.id, chat_id=chat_id))
    await bot(media_request(document, bot_id=bot.id, chat_id=chat_id))
    messages = await bot(media_album([photo, photo], bot_id=bot.id, chat_id=chat_id))
    # These IDs come from this bot's own response, not a user callback.
    await bot(media_edit(photo, bot_id=bot.id, chat_id=chat_id,
                         message_id=messages[0].message_id, album_kind='photo-video'))
    # A network timeout propagates. Never retry the whole sequence blindly.


def attach_media(dispatcher: Dispatcher) -> Router:
    router = Router(name='media-examples')
    ordinary_private = ((F.chat.type == 'private') & (F.message_thread_id == None)
                        & (F.is_topic_message != True) & (F.business_connection_id == None))

    @router.message(Command('media'), ordinary_private)
    async def demo(message: Message, bot: Bot) -> None:
        if message.from_user is None or message.from_user.is_bot:
            return
        await send_media_demo(bot, message.chat.id)

    @router.message(F.document, ordinary_private)
    async def receive(message: Message, bot: Bot) -> None:
        if message.from_user is None or message.from_user.is_bot or message.document is None:
            return
        # Bounded explicit read, not arbitrary filesystem access or a URL fetch.
        # The user's filename/MIME is not a trusted storage path or content type.
        try:
            result = await download_media(bot, message.document.file_id, max_bytes=1_000_000)
        except Exception as error:
            report = safe_error_report(error, operation='read')
            await message.answer(report.message, parse_mode=None)
            return
        await message.answer(f'Получено {len(result.data)} байт.', parse_mode=None)
        # Do not execute or parse the downloaded content in this demonstration.

    dispatcher.include_router(router)
    return router
