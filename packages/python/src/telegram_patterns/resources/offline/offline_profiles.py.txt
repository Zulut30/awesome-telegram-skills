"""Actual Dispatcher, scoped profile observations, locale state and unknown edit."""
import asyncio
import json
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.methods import (GetChat, GetMe, GetMyName, GetMyDescription, GetMyShortDescription,
                             GetUserProfilePhotos, SetMyName, SetMyDescription,
                             SetMyShortDescription, SetMyProfilePhoto, RemoveMyProfilePhoto,
                             SendMessage, SendPhoto)
from aiogram.types import InputProfilePhotoStatic, Update
from telegram_patterns.aiogram import read_bot_profile
from telegram_patterns.testing import StubSession
from profiles_bot import AVATAR, profile_router


async def main():
    session = StubSession()
    bot = Bot('100:PROFILES_FIXTURE', session=session, default=DefaultBotProperties(parse_mode='HTML'))
    dispatcher = Dispatcher()
    checked = []; uploaded = []; helped = []; replies = []; avatar_visible = {'value': False}; state = {'': {'name': 'Base', 'description': 'Default bio', 'short_description': 'Default short'}}
    async def authorize(actor_id, bot_id, method):
        checked.append((actor_id, bot_id, method))
        return actor_id == 42 and bot_id == 100
    dispatcher.include_router(profile_router(authorize))
    host = Router()
    @host.message(Command('help'))
    async def help_handler(message): helped.append(message.text)
    dispatcher.include_router(host)
    session.respond(GetMe, {'id': 100, 'is_bot': True, 'first_name': 'Base', 'can_join_groups': True})
    session.respond(GetChat, {'id': 42, 'type': 'private', 'first_name': '<b>Actor</b>', 'accent_color_id': 0,
                             'max_reaction_count': 11, 'accepted_gift_types': {k: False for k in ('unlimited_gifts', 'limited_gifts', 'unique_gifts', 'premium_subscription', 'gifts_from_channels')}})
    def photo_page(request):
        visible = request.user_id == 42 or avatar_visible['value']
        return {'total_count': int(visible), 'photos': [[{'file_id': 'opaque', 'file_unique_id': 'unique', 'width': 100, 'height': 100}]] if visible else []}
    session.respond(GetUserProfilePhotos, photo_page)
    for method, key in ((GetMyName, 'name'), (GetMyDescription, 'description'), (GetMyShortDescription, 'short_description')):
        session.respond(method, lambda request, key=key: {key: state.get(request.language_code, {}).get(key, state[''][key])})
    for method, key in ((SetMyName, 'name'), (SetMyDescription, 'description'), (SetMyShortDescription, 'short_description')):
        def write(request, key=key):
            locale = request.language_code
            value = getattr(request, key)
            if value == '' and locale:
                state.setdefault(locale, {}).pop(key, None)
            else: state.setdefault(locale, {})[key] = value
            return True
        session.respond(method, write)
    async def upload(request):
        assert isinstance(request.photo, InputProfilePhotoStatic)
        files = {}; prepared = session.prepare_value(request.photo, bot=bot, files=files)
        assert 'attach://' in json.dumps(prepared) and len(files) == 1
        for file in files.values(): uploaded.append(b''.join([part async for part in file.read(bot)]))
        assert uploaded[-1] == AVATAR and AVATAR.startswith(b'\xff\xd8\xff') and AVATAR.endswith(b'\xff\xd9')
        avatar_visible['value'] = True
        return True
    def remove(request): avatar_visible['value'] = False; return True
    session.respond(SetMyProfilePhoto, upload).respond(RemoveMyProfilePhoto, remove)
    def reply(request):
        if isinstance(request, SendMessage):
            assert request.parse_mode is None
            replies.append(request.text)
        return {'message_id': 500, 'date': 1, 'chat': {'id': request.chat_id, 'type': 'private'}, 'text': getattr(request, 'text', None)}
    session.respond(SendMessage, reply).respond(SendPhoto, reply)
    def incoming(index, command, *, actor=42, premium=None, **changes):
        return Update.model_validate({'update_id': index, 'message': {'message_id': index, 'date': 1,
            'chat': {'id': actor, 'type': 'private'}, 'from': {'id': actor, 'is_bot': False, 'first_name': '<b>Actor</b>', 'is_premium': premium},
            'text': command, **changes}})
    try:
        await dispatcher.feed_update(bot, incoming(1, '/profile'))
        assert 'Premium: неизвестно' in replies[-1] and 'Bio: неизвестно' in replies[-1] and '<b>Actor</b>' in replies[-1]
        assert isinstance(session.calls[-1], SendPhoto) and session.calls[-1].photo == 'opaque'
        count = len(session.calls)
        for changes in ({'chat': {'id': -42, 'type': 'group'}}, {'is_topic_message': True}, {'message_thread_id': 7}, {'business_connection_id': 'business'}):
            await dispatcher.feed_update(bot, incoming(2, '/profile', **changes))
            await dispatcher.feed_update(bot, incoming(3, '/configure_bot', **changes))
        assert len(session.calls) == count
        count = len(session.calls)
        await dispatcher.feed_update(bot, incoming(4, '/configure_bot', actor=99, premium=True))
        assert len(session.calls) == count+1 and isinstance(session.calls[-1], SendMessage)
        await dispatcher.feed_update(bot, incoming(5, '/configure_bot'))
        assert uploaded == [AVATAR]
        assert state['ru'] == {'name': 'Бот записи', 'description': 'Запись на консультацию', 'short_description': 'Выберите удобное время'}
        assert state['']['description'] == 'Default bio'
        assert checked[-6:] == [(42, 100, method) for method in ('read', 'setMyName', 'setMyDescription', 'setMyShortDescription', 'setMyProfilePhoto', 'read')]
        await dispatcher.feed_update(bot, incoming(6, '/clear_bot_description'))
        assert 'description' not in state['ru'] and state['ru']['name'] == 'Бот записи'
        assert replies[-1].endswith('Default bio')
        await dispatcher.feed_update(bot, incoming(7, '/remove_bot_photo'))
        assert sum(isinstance(c, RemoveMyProfilePhoto) for c in session.calls) == 1
        assert sum(isinstance(c, GetUserProfilePhotos) and c.user_id == 100 for c in session.calls) == 2
        assert avatar_visible['value'] is False
        await dispatcher.feed_update(bot, incoming(8, '/bot_profile'))
        assert replies[-1] == 'Бот записи\nDefault bio'
        def lost_receipt(request):
            state['ru']['description'] = request.description
            raise TimeoutError('DO_NOT_LOG_PRIVATE_PAYLOAD')
        session.respond(SetMyDescription, lost_receipt)
        count = sum(isinstance(c, SetMyDescription) for c in session.calls)
        await dispatcher.feed_update(bot, incoming(9, '/configure_bot'))
        assert sum(isinstance(c, SetMyDescription) for c in session.calls) == count+1 and uploaded == [AVATAR]
        assert 'Результат операции' in replies[-1] and 'DO_NOT_LOG_PRIVATE_PAYLOAD' not in replies[-1]
        reconciled = await read_bot_profile(bot, language_code='ru')
        assert reconciled.description == 'Запись на консультацию'
        await dispatcher.feed_update(bot, incoming(10, '/help'))
        assert helped == ['/help']
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': session.closed,
        'unknown_fields_preserved': True, 'profile_photos': True, 'localized_omission_clear': True,
        'fresh_method_acl': True, 'new_avatar_upload_removal': True, 'unknown_edit_reconciliation': True,
        'private_context_guards': True, 'existing_dispatcher_preserved': bool(helped), 'photo_upload_bytes': len(AVATAR)}))


if __name__ == '__main__': asyncio.run(main())
