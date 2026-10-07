"""Polls with media: photos, links and places in options, media in the description and quiz explanation; no polling on import."""
from collections.abc import Awaitable, Callable
from typing import cast

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import InputMediaLink, InputMediaPhoto, InputMediaVenue, Message, PollMedia
from telegram_patterns.aiogram import ChatType, PollChoice, PollSpec, poll_request

Photos = Callable[[], Awaitable[dict[str, str]]]  # name -> photo file_id uploaded earlier by the bot
Seen = Callable[[int, list[str | None]], Awaitable[None]]  # (chat_id, media kind per option)


def media_kind(media: PollMedia | None) -> str | None:
    """What a received option or description holds: one of photo, link, venue, location, video, ..."""
    if media is None:
        return None
    return next((name for name, value in media if value), None)


def attach_poll_media(dispatcher: Dispatcher, *, photos: Photos, seen: Seen) -> Router:
    router = Router(name='poll-media')

    @router.message(Command('place'))
    async def place(message: Message, bot: Bot) -> None:
        files = await photos()
        # Option media: photo, link, venue, location, sticker, animation, video or live photo (InputPollOptionMedia).
        spec = PollSpec(question='Где встречаемся в субботу?', is_anonymous=False, description='Голосование до пятницы',
                        options=[PollChoice('Кафе у парка', media=InputMediaPhoto(media=files['cafe'])),
                                 PollChoice('Коворкинг', media=InputMediaLink(url='https://example.com/coworking')),
                                 PollChoice('Набережная', media=InputMediaVenue(latitude=55.75, longitude=37.62,
                                                                               title='Набережная', address='Причал 1'))])
        # Description media takes InputPollMedia: no links or stickers there.
        await bot(poll_request(spec, chat_id=message.chat.id, chat_type=cast(ChatType, message.chat.type),
                               media=InputMediaPhoto(media=files['map'])))

    @router.message(Command('quiz'))
    async def quiz(message: Message, bot: Bot) -> None:
        files = await photos()
        spec = PollSpec(question='Какая река на фото?', kind='quiz', options=['Нева', 'Волга', 'Ока'],
                        correct_option_ids=[0], explanation='Это Нева у Дворцовой набережной')
        await bot(poll_request(spec, chat_id=message.chat.id, chat_type=cast(ChatType, message.chat.type),
                               media=InputMediaPhoto(media=files['river']), explanation_media=InputMediaPhoto(media=files['answer'])))

    @router.message(F.poll)
    async def received(message: Message) -> None:
        # Incoming polls carry PollMedia; audio and documents are never received in options.
        if message.poll is not None:
            await seen(message.chat.id, [media_kind(option.media) for option in message.poll.options])  # nothing is downloaded

    dispatcher.include_router(router)
    return router
