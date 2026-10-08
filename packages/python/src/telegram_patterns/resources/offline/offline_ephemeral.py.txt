"""Actual host Dispatcher and SDK serialization of ephemeral answers in a supergroup; HTTP is disabled."""
import asyncio
from datetime import datetime, timezone
import json

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.methods import AnswerCallbackQuery, DeleteEphemeralMessage, EditEphemeralMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from telegram_patterns.testing import StubSession
from ephemeral_bot import attach_ephemeral_status

GROUP = Chat(id=-1001, type='supergroup', title='Клуб')
WHEN = datetime(2026, 10, 7, tzinfo=timezone.utc)


async def main():
    session = StubSession()
    bot = Bot('100:EPHEMERAL_FIXTURE', session=session)
    dispatcher = Dispatcher()
    help_router, helped = Router(name='existing-help'), []

    @help_router.message(Command('help'))
    async def help_handler(message: Message): helped.append(message.text)
    dispatcher.include_router(help_router)
    now = [100.0]
    delays = {}

    async def status(chat_id, user_id):
        now[0] += delays.pop(user_id, 0.5)  # the service call takes time on the host clock
        return f'Пользователь {user_id}: 3 задачи'

    attach_ephemeral_status(dispatcher, status=status, clock=lambda: now[0])
    sent, answers, edits, deletes = [], [], [], []

    def send(method):
        payload = json.loads(session.prepare_value(method.ephemeral_message_parameters, bot=bot, files={})) \
            if method.ephemeral_message_parameters else None
        sent.append({'text': method.text, 'ephemeral': payload})
        ephemeral = {'ephemeral_message_id': 5, 'message_id': 0} if payload else {'message_id': 300 + len(sent)}
        return {**ephemeral, 'date': 1, 'chat': {'id': method.chat_id, 'type': 'supergroup', 'title': 'Клуб'}, 'text': method.text}

    session.respond(SendMessage, send)
    session.respond(AnswerCallbackQuery, lambda method: answers.append((method.text, method.show_alert)) or True)
    session.respond(EditEphemeralMessageText, lambda method: edits.append(json.loads(method.model_dump_json(include={'chat_id', 'receiver_user_id', 'ephemeral_message_id', 'text'}))) or True)
    session.respond(DeleteEphemeralMessage, lambda method: deletes.append(json.loads(method.model_dump_json())) or True)
    anna = User(id=7, is_bot=False, first_name='Анна')

    def press(index, data, message):
        return Update(update_id=index, callback_query=CallbackQuery(id=f'q{index}', from_user=anna, chat_instance='ci', data=data, message=message))
    panel = Message(message_id=301, date=WHEN, chat=GROUP, text='Нажмите')
    own = Message(message_id=0, ephemeral_message_id=5, date=WHEN, chat=GROUP, text='Пользователь 7: 3 задачи')
    try:
        await dispatcher.feed_update(bot, Update(update_id=1, message=Message(message_id=1, date=WHEN, chat=GROUP, from_user=anna, text='/panel')))
        assert sent[0]['ephemeral'] is None, 'the panel itself is an ordinary group message'

        await dispatcher.feed_update(bot, press(2, 'me:status', panel))
        assert sent[1]['ephemeral'] == {'receiver_user_id': 7, 'callback_query_id': 'q2'} and answers[-1] == (None, None)
        await dispatcher.feed_update(bot, press(3, 'me:replace', panel))
        assert sent[2]['ephemeral'] == {'receiver_user_id': 7, 'callback_query_id': 'q3', 'replace_callback_query_message': True}

        await dispatcher.feed_update(bot, press(4, 'me:refresh', own))
        assert edits == [{'chat_id': -1001, 'receiver_user_id': 7, 'ephemeral_message_id': 5, 'text': 'Пользователь 7: 3 задачи'}]
        await dispatcher.feed_update(bot, press(5, 'me:hide', own))
        assert deletes == [{'chat_id': -1001, 'receiver_user_id': 7, 'ephemeral_message_id': 5}]
        assert len(sent) == 3, 'buttons on an ephemeral message never send a new one'

        delays[7] = 20.0  # a slow service: the 15-second window is over before the answer
        await dispatcher.feed_update(bot, press(6, 'me:status', panel))
        assert len(sent) == 3 and answers[-1] == ('Пользователь 7: 3 задачи', True)

        private = Message(message_id=9, date=WHEN, chat=Chat(id=7, type='private'), text='x')
        await dispatcher.feed_update(bot, press(7, 'me:status', private))
        assert len(sent) == 3 and answers[-1] == ('Эта кнопка работает в группе', True)
        await dispatcher.feed_update(bot, Update(update_id=8, message=Message(message_id=2, date=WHEN, chat=GROUP, from_user=anna, text='/help')))
        assert helped == ['/help']
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': session.closed, 'ephemeral_answers': 2,
                      'callback_query_named': True, 'replace_original': True, 'edit_by_reference': True, 'delete_by_reference': True,
                      'window_expired_alert': True, 'groups_only': True, 'callback_acknowledged': True,
                      'existing_dispatcher_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
