"""Actual host Dispatcher and SDK serialization of polls with media in options, description and quiz explanation; HTTP is disabled."""
import asyncio
from datetime import datetime, timezone
import json

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.methods import SendPoll
from aiogram.types import Chat, InputMediaLink, InputMediaPhoto, Message, Update, User
from pydantic import ValidationError
from telegram_patterns import ValidationFailure
from telegram_patterns.aiogram import PollSpec, poll_request
from telegram_patterns.testing import StubSession
from poll_media_bot import attach_poll_media

CHAT = Chat(id=-1006, type='supergroup', title='Клуб')
ANNA = User(id=7, is_bot=False, first_name='Анна')
WHEN = datetime(2026, 10, 7, tzinfo=timezone.utc)
FILES = {'cafe': 'photo-cafe', 'map': 'photo-map', 'river': 'photo-river', 'answer': 'photo-answer'}


async def main():
    session = StubSession()
    bot = Bot('100:POLL_MEDIA_FIXTURE', session=session)
    dispatcher = Dispatcher()
    help_router, helped = Router(name='existing-help'), []

    @help_router.message(Command('help'))
    async def help_handler(message: Message): helped.append(message.text)
    dispatcher.include_router(help_router)
    observed = []

    async def photos():
        return FILES

    async def seen(chat_id, kinds):
        observed.append((chat_id, kinds))

    attach_poll_media(dispatcher, photos=photos, seen=seen)
    polls = []

    def sent(method):
        polls.append(json.loads(session.prepare_value(method.model_dump(exclude_none=True, exclude={'chat_id'}), bot=bot, files={})))
        return {'message_id': 900, 'date': 1, 'chat': {'id': method.chat_id, 'type': 'supergroup'},
                'poll': {'id': 'p', 'question': method.question, 'options': [], 'total_voter_count': 0, 'is_closed': False,
                         'is_anonymous': True, 'type': 'regular', 'allows_multiple_answers': False, 'allows_revoting': True, 'members_only': False}}
    session.respond(SendPoll, sent)

    def command(index, text):
        return Update(update_id=index, message=Message(message_id=index, date=WHEN, chat=CHAT, from_user=ANNA, text=text))
    try:
        await dispatcher.feed_update(bot, command(1, '/place'))
        place = polls[0]
        assert [option.get('media') for option in place['options']] == [
            {'type': 'photo', 'media': 'photo-cafe'}, {'type': 'link', 'url': 'https://example.com/coworking'},
            {'type': 'venue', 'latitude': 55.75, 'longitude': 37.62, 'title': 'Набережная', 'address': 'Причал 1'}], place['options']
        assert place['media'] == {'type': 'photo', 'media': 'photo-map'} and place['description'] == 'Голосование до пятницы'

        await dispatcher.feed_update(bot, command(2, '/quiz'))
        quiz = polls[1]
        assert quiz['type'] == 'quiz' and quiz['explanation_media'] == {'type': 'photo', 'media': 'photo-answer'}
        assert quiz['media'] == {'type': 'photo', 'media': 'photo-river'} and quiz['correct_option_ids'] == [0]

        spec = PollSpec(question='?', options=['a', 'b'])
        try:
            poll_request(spec, chat_id=-1006, chat_type='supergroup', media=InputMediaLink(url='https://example.com'))  # type: ignore[arg-type]
        except ValidationError:
            pass  # a link is option media only
        else:
            raise AssertionError('Link accepted as description media')
        try:
            poll_request(spec, chat_id=-1006, chat_type='supergroup', explanation_media=InputMediaPhoto(media='x'))
        except ValidationFailure:
            pass  # explanation media needs a quiz
        else:
            raise AssertionError('Explanation media accepted for a regular poll')

        incoming = Message.model_validate({'message_id': 3, 'date': WHEN, 'chat': CHAT, 'from_user': ANNA, 'poll': {
            'id': 'p2', 'question': 'Куда?', 'total_voter_count': 0, 'is_closed': False, 'is_anonymous': False, 'type': 'regular',
            'allows_multiple_answers': False, 'allows_revoting': True, 'members_only': False, 'options': [
                {'persistent_id': 'o1', 'text': 'Сайт', 'voter_count': 0, 'media': {'link': {'url': 'https://example.com'}}},
                {'persistent_id': 'o2', 'text': 'Фото', 'voter_count': 0, 'media': {'photo': [{'file_id': 'f', 'file_unique_id': 'u', 'width': 1, 'height': 1}]}},
                {'persistent_id': 'o3', 'text': 'Без медиа', 'voter_count': 0}]}})
        await dispatcher.feed_update(bot, Update(update_id=3, message=incoming))
        assert observed == [(-1006, ['link', 'photo', None])]
        await dispatcher.feed_update(bot, command(4, '/help'))
        assert helped == ['/help']
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': session.closed, 'option_media': 3,
                      'description_media': True, 'explanation_media': True, 'link_only_in_options': True,
                      'explanation_needs_quiz': True, 'incoming_media_kinds': True, 'existing_dispatcher_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
