"""Live photos: keep what users send, resend it by file_id alone or in an album; no polling on import."""
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.methods import SendLivePhoto, SendMediaGroup, SendMessage
from aiogram.types import FSInputFile, InputMediaAudio, InputMediaDocument, InputMediaLivePhoto, InputMediaPhoto, InputMediaVideo, Message
from telegram_patterns import ValidationFailure

MAX_UPLOAD = 10 * 1024 * 1024  # the video of a live photo: at most 10 MB and 10 seconds
Remember = Callable[[int, str, str], Awaitable[None]]  # (chat_id, video file_id, photo file_id)
Recall = Callable[[int], Awaitable[list[tuple[str, str]]]]


def live_photo_source(value: str | Path) -> str | FSInputFile:
    """A file_id to reuse or a local file to upload; Telegram does not take live photos by URL."""
    if isinstance(value, Path):
        if not value.is_file() or value.stat().st_size > MAX_UPLOAD:
            raise ValidationFailure('Upload a local live photo file of at most 10 MB')
        return FSInputFile(value)
    if not isinstance(value, str) or not value or value.lower().startswith(('http://', 'https://', 'attach://')):
        raise ValidationFailure('Live photos are sent by file_id or upload, not by URL')
    return value


def attach_live_photos(dispatcher: Dispatcher, *, remember: Remember, recall: Recall) -> Router:
    router = Router(name='live-photos')

    @router.message(F.live_photo)
    async def received(message: Message, bot: Bot) -> None:
        live = message.live_photo
        if live is None or not live.photo:
            # Without the static photo the pair cannot be resent as a live photo.
            await bot(SendMessage(chat_id=message.chat.id, text='Не удалось сохранить: нет статичного кадра.'))
            return
        await remember(message.chat.id, live.file_id, live.photo[-1].file_id)
        await bot(SendMessage(chat_id=message.chat.id, text=f'Сохранено: {live.duration} с, {live.width}×{live.height}.'))

    @router.message(Command('last'))
    async def last(message: Message, bot: Bot) -> None:
        saved = await recall(message.chat.id)
        if not saved:
            await bot(SendMessage(chat_id=message.chat.id, text='Пришлите live photo.'))
            return
        video, photo = saved[-1]
        await bot(SendLivePhoto(chat_id=message.chat.id, live_photo=live_photo_source(video), photo=live_photo_source(photo),
                                caption='Последнее live photo'))

    @router.message(Command('album'))
    async def album(message: Message, bot: Bot) -> None:
        saved = (await recall(message.chat.id))[-10:]  # an album holds 2-10 items
        if len(saved) < 2:
            await bot(SendMessage(chat_id=message.chat.id, text='Для альбома нужно хотя бы два live photo.'))
            return
        media: list[InputMediaAudio | InputMediaDocument | InputMediaLivePhoto | InputMediaPhoto | InputMediaVideo] = [
            InputMediaLivePhoto(media=video, photo=photo) for video, photo in saved]
        await bot(SendMediaGroup(chat_id=message.chat.id, media=media))

    dispatcher.include_router(router)
    return router
