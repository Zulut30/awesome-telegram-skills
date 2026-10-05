"""Every public profile symbol, native reads and one explicitly authorized write."""
import asyncio
import json
from aiogram import Bot
from aiogram.methods import GetMe, GetMyName, GetMyDescription, GetMyShortDescription, GetUserProfilePhotos, SetMyDescription
from aiogram.types import User, ChatFullInfo
from telegram_patterns import safe_error_report
from telegram_patterns.aiogram import (
    ProfileSource, ProfileAuthorizer, UserProfile, ChatProfile, ProfilePhotoSize, ProfilePhotos,
    BotProfile, BotProfilePatch, ProfileEditIncomplete, user_profile, chat_profile,
    read_profile_photos, read_bot_profile, update_bot_profile,
)
from telegram_patterns.testing import StubSession


async def main():
    session = StubSession()
    bot = Bot('100:PROFILE_REFERENCE', session=session)
    source: ProfileSource = 'update'
    user: UserProfile = user_profile(User(id=42, is_bot=False, first_name='Example'), source=source)
    assert user.is_premium is None and user.username is None
    chat: ChatProfile = chat_profile(ChatFullInfo.model_validate({'id': 42, 'type': 'private', 'accent_color_id': 0,
        'max_reaction_count': 11, 'accepted_gift_types': {k: False for k in ('unlimited_gifts', 'limited_gifts', 'unique_gifts', 'premium_subscription', 'gifts_from_channels')}}))
    assert chat.bio is None and chat.permissions is None
    size = ProfilePhotoSize(bot.id, user.id, 'opaque', 'unique', 100, 100)
    assert size.as_media().as_input(bot.id) == 'opaque'
    session.respond(GetMe, {'id': 100, 'is_bot': True, 'first_name': 'Bot'})
    state = {'description': 'Original'}
    session.respond(GetMyName, {'name': 'Localized name'}).respond(GetMyShortDescription, {'short_description': 'Short'})
    session.respond(GetMyDescription, lambda request: {'description': state['description']})
    session.respond(GetUserProfilePhotos, {'total_count': 0, 'photos': []})
    def update(request): state['description'] = request.description; return True
    session.respond(SetMyDescription, update)
    async def authorize(actor_id: int, bot_id: int, method: str) -> bool:
        return actor_id == user.id and bot_id == bot.id and method in ('read', 'setMyDescription')
    acl: ProfileAuthorizer = authorize
    try:
        photos: ProfilePhotos = await read_profile_photos(bot, user.id)
        assert photos.total_count == 0 and photos.photos == ()
        profile: BotProfile = await read_bot_profile(bot, language_code='ru')
        assert profile.user.source == 'getMe' and profile.user.is_premium is None
        assert profile.photos is None
        with_photos = await read_bot_profile(bot, language_code='ru', include_photos=True)
        assert with_photos.photos is not None and with_photos.photos.total_count == 0 and with_photos.photos.user_id == bot.id
        updated = await update_bot_profile(bot, BotProfilePatch(description='New'), actor_id=user.id, authorize=acl, language_code='ru')
        assert updated.description == 'New' and updated.name == profile.name
        incomplete = ProfileEditIncomplete(('setMyName',), 'setMyDescription')
        assert safe_error_report(incomplete, operation='write').recovery == 'reconcile'
    finally:
        await bot.session.close()
    print(json.dumps({'case': 'bot_profiles', 'passed': True, 'network': False, 'session_closed': session.closed}))


if __name__ == '__main__': asyncio.run(main())
