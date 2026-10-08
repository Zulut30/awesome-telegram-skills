"""Actual host Dispatcher and SDK models for a guest bot summoned in a foreign group; HTTP is disabled."""
import asyncio
from datetime import datetime, timezone
import json

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.methods import AnswerGuestQuery
from aiogram.types import Chat, Message, Update, User
from telegram_patterns.testing import StubSession
from guest_bot import attach_guest_replies

GROUP = Chat(id=-1003, type='supergroup', title='Чужая группа')
WHEN = datetime(2026, 10, 7, tzinfo=timezone.utc)
ANNA = User(id=7, is_bot=False, first_name='Анна')


async def main():
    session = StubSession()  # only answerGuestQuery is registered: sendMessage into the foreign chat would fail
    bot = Bot('100:GUEST_FIXTURE', session=session)
    dispatcher = Dispatcher()
    help_router, helped = Router(name='existing-help'), []

    @help_router.message(Command('help'))
    async def help_handler(message: Message): helped.append(message.text)
    dispatcher.include_router(help_router)
    claimed, asked = set(), []

    async def claim(query_id):
        if query_id in claimed:
            return False
        claimed.add(query_id)
        return True

    async def reply(text, context):
        asked.append((text, context))
        return f'Перевод: {context}' if context else 'Ответьте на сообщение, которое нужно перевести.'

    attach_guest_replies(dispatcher, reply=reply, claim=claim)
    answers = []
    def answer(method):
        # The wire JSON as aiogram sends it, with the bot's default parse_mode resolved.
        answers.append({'guest_query_id': method.guest_query_id, 'result': json.loads(session.prepare_value(method.result, bot=bot, files={}))})
        return {'inline_message_id': f'im{len(answers)}'}
    session.respond(AnswerGuestQuery, answer)
    original = Message(message_id=10, date=WHEN, chat=GROUP, from_user=User(id=8, is_bot=False, first_name='Бен'), text='Hello')

    def summon(index, text, query_id='g1', replied=original):
        return Update(update_id=index, guest_message=Message(message_id=20 + index, date=WHEN, chat=GROUP, from_user=ANNA, text=text,
                                                             guest_query_id=query_id, reply_to_message=replied))
    try:
        await dispatcher.feed_update(bot, summon(1, '@helper_bot переведи'))
        assert asked == [('@helper_bot переведи', 'Hello')]
        assert answers == [{'guest_query_id': 'g1', 'result': {'type': 'article', 'id': 'answer', 'title': 'Ответ',
                                                               'input_message_content': {'message_text': 'Перевод: Hello'}}}]
        await dispatcher.feed_update(bot, summon(2, '@helper_bot переведи'))  # the same query delivered again
        assert len(answers) == 1, 'one reply per guest_query_id'
        await dispatcher.feed_update(bot, summon(3, '/help@helper_bot', query_id='g2', replied=None))
        assert helped == [] and answers[-1]['result']['input_message_content']['message_text'].startswith('Ответьте'), \
            'a guest message never reaches ordinary message handlers'
        await dispatcher.feed_update(bot, Update(update_id=4, guest_message=Message(message_id=40, date=WHEN, chat=GROUP, from_user=ANNA, text='x')))
        assert len(answers) == 2, 'no guest_query_id, no reply'
        await dispatcher.feed_update(bot, Update(update_id=5, message=Message(message_id=50, date=WHEN, chat=Chat(id=7, type='private'), from_user=ANNA, text='/help')))
        assert helped == ['/help']
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': session.closed, 'guest_answers': len(answers),
                      'reply_context_used': True, 'one_reply_per_query': True, 'separate_update_type': True,
                      'no_send_message_to_foreign_chat': True, 'existing_dispatcher_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
