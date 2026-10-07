"""Actual python-telegram-bot Application: ephemeral answer, edit and delete through api_kwargs/do_api_request; HTTP is disabled."""
import asyncio
import json

from telegram import Update
from telegram.ext import CommandHandler
from telegram_patterns.ptb import offline_application
from ptb_ephemeral_bot import attach_ephemeral_status

GROUP = {'id': -1001, 'type': 'supergroup', 'title': 'Клуб'}
ANNA = {'id': 7, 'is_bot': False, 'first_name': 'Анна'}


async def main():
    application, stub = offline_application()
    helped, now, delays = [], [100.0], {}

    async def help_command(update, context):
        helped.append(update.effective_message.text)
    application.add_handler(CommandHandler('help', help_command))

    async def status(chat_id, user_id):
        now[0] += delays.pop(user_id, 0.5)
        return f'Пользователь {user_id}: 3 задачи'
    attach_ephemeral_status(application, status=status, clock=lambda: now[0])
    stub.respond('sendMessage', lambda p: {'message_id': 0 if 'ephemeral_message_parameters' in p else 301, 'date': 1, 'chat': GROUP, 'text': p['text'],
                                           **({'ephemeral_message_id': 5} if 'ephemeral_message_parameters' in p else {})})
    stub.respond('answerCallbackQuery', True)
    stub.respond('editEphemeralMessageText', True)
    stub.respond('deleteEphemeralMessage', True)
    panel = {'message_id': 301, 'date': 1, 'chat': GROUP, 'text': 'Нажмите'}
    own = {'message_id': 0, 'ephemeral_message_id': 5, 'date': 1, 'chat': GROUP, 'text': 'Пользователь 7: 3 задачи'}

    def press(index, data, message, chat=GROUP):
        return Update.de_json({'update_id': index, 'callback_query': {'id': f'q{index}', 'from': ANNA, 'chat_instance': 'c', 'data': data,
                                                                       'message': {**message, 'chat': chat}}}, application.bot)
    await application.initialize()
    try:
        await application.process_update(Update.de_json({'update_id': 1, 'message': {
            'message_id': 1, 'date': 1, 'chat': GROUP, 'from': ANNA, 'text': '/panel', 'entities': [{'type': 'bot_command', 'offset': 0, 'length': 6}]}}, application.bot))
        assert 'ephemeral_message_parameters' not in stub.calls[-1][1], 'the panel is an ordinary group message'
        await application.process_update(press(2, 'me:status', panel))
        method, sent = stub.calls[-2]
        assert method == 'sendMessage' and sent['ephemeral_message_parameters'] == {'receiver_user_id': 7, 'callback_query_id': 'q2'}
        assert stub.calls[-1] == ('answerCallbackQuery', {'callback_query_id': 'q2'})
        await application.process_update(press(3, 'me:refresh', own))
        assert stub.calls[-2] == ('editEphemeralMessageText', {'chat_id': -1001, 'receiver_user_id': 7, 'ephemeral_message_id': 5,
            'text': 'Пользователь 7: 3 задачи', 'reply_markup': {'inline_keyboard': [[{'text': 'Обновить', 'callback_data': 'me:refresh'},
                                                                                     {'text': 'Скрыть', 'callback_data': 'me:hide'}]]}})
        await application.process_update(press(4, 'me:hide', own))
        assert stub.calls[-2] == ('deleteEphemeralMessage', {'chat_id': -1001, 'receiver_user_id': 7, 'ephemeral_message_id': 5})
        delays[7] = 20.0
        await application.process_update(press(5, 'me:status', panel))
        assert stub.calls[-1] == ('answerCallbackQuery', {'callback_query_id': 'q5', 'text': 'Пользователь 7: 3 задачи', 'show_alert': True})
        sends = [m for m, _ in stub.calls if m == 'sendMessage']
        await application.process_update(press(6, 'me:status', panel, chat={'id': 7, 'type': 'private', 'first_name': 'Анна'}))
        assert [m for m, _ in stub.calls if m == 'sendMessage'] == sends and stub.calls[-1][1]['show_alert'] is True, 'groups only'
        await application.process_update(Update.de_json({'update_id': 7, 'message': {
            'message_id': 7, 'date': 1, 'chat': GROUP, 'from': ANNA, 'text': '/help', 'entities': [{'type': 'bot_command', 'offset': 0, 'length': 5}]}}, application.bot))
        assert helped == ['/help']
    finally:
        await application.shutdown()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': stub.closed, 'sdk': 'python-telegram-bot',
                      'new_fields_via_api_kwargs': True, 'new_methods_via_do_api_request': True, 'window_expired_alert': True,
                      'groups_only': True, 'callback_acknowledged': True, 'existing_application_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
