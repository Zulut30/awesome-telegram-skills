"""Attach profile commands to the existing Dispatcher; host supplies current ACL."""
from __future__ import annotations
import base64
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from telegram_patterns import MessageBuilder, PermissionDenied, safe_error_report
from telegram_patterns.aiogram import (
    BotProfilePatch, MediaFile, ProfileAuthorizer, ProfileEditIncomplete,
    chat_profile, user_profile, read_profile_photos, read_bot_profile, update_bot_profile,
)

# Trusted 16x16 JPG fixture produced by Windows System.Drawing; not a user upload.
AVATAR = base64.b64decode('/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAAQABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDq6KKK/os/Kj//2Q==')


def profile_router(authorize: ProfileAuthorizer) -> Router:
    router = Router(name='profile-example')
    router.message.filter(F.chat.type == 'private', F.from_user.is_bot == False,
                          ~F.message_thread_id, ~F.is_topic_message, ~F.business_connection_id)

    @router.message(Command('profile'))
    async def own_profile(message: Message) -> None:
        if message.from_user is None or message.from_user.id != message.chat.id:
            return
        observed = user_profile(message.from_user)
        premium = 'неизвестно' if observed.is_premium is None else ('да' if observed.is_premium else 'нет')
        try:
            detail = chat_profile(await message.bot.get_chat(message.chat.id))
            photos = await read_profile_photos(message.bot, observed.id, limit=1)
        except Exception as error:
            await message.answer(safe_error_report(error, operation='read').message, parse_mode=None)
            return
        text = MessageBuilder().text('Имя: ').text(observed.first_name).text('\nPremium: ').text(premium)
        text = text.text('\nBio: ').text('неизвестно' if detail.bio is None else detail.bio)
        # An empty API page never proves absence of a private avatar.
        text = text.text('\nДоступных фото: ').text(str(photos.total_count))
        await message.answer(**text.build().as_kwargs())
        if photos.photos:
            await message.answer_photo(photo=photos.photos[0][-1].as_media().as_input(message.bot.id))

    @router.message(Command('bot_profile'))
    async def own_bot_profile(message: Message) -> None:
        if message.from_user is None:
            return
        if await authorize(message.from_user.id, message.bot.id, 'read') is not True:
            await message.answer('Недостаточно прав.', parse_mode=None)
            return
        observed = await read_bot_profile(message.bot, language_code='ru')
        text = MessageBuilder().text(observed.name).text('\n').text(observed.description)
        await message.answer(**text.build().as_kwargs())

    async def apply(message: Message, patch: BotProfilePatch) -> None:
        if message.from_user is None:
            return
        try:
            observed = await update_bot_profile(message.bot, patch, actor_id=message.from_user.id,
                                                authorize=authorize, language_code='ru')
        except (PermissionDenied, ProfileEditIncomplete) as error:
            await message.answer(safe_error_report(error, operation='write').message, parse_mode=None)
            return
        # Fresh readback is not an atomic/CAS receipt. Host updates its cache from this observation.
        await message.answer(**MessageBuilder().text('Текущее описание: ').text(observed.description).build().as_kwargs())

    @router.message(Command('configure_bot'))
    async def configure(message: Message) -> None:
        await apply(message, BotProfilePatch(name='Бот записи', description='Запись на консультацию',
                                            short_description='Выберите удобное время',
                                            photo=MediaFile('photo', AVATAR, filename='avatar.jpg')))

    @router.message(Command('clear_bot_description'))
    async def clear(message: Message) -> None:
        await apply(message, BotProfilePatch(description=''))

    @router.message(Command('remove_bot_photo'))
    async def remove(message: Message) -> None:
        await apply(message, BotProfilePatch(remove_photo=True))

    return router
