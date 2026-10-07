"""Actual python-telegram-bot Application with the SDK-free selection menu; HTTP is disabled."""
import asyncio
import json

from telegram import Update
from telegram.ext import CommandHandler
from telegram_patterns.ptb import offline_application
from ptb_selection_bot import attach_selection

ANNA = {'id': 7, 'is_bot': False, 'first_name': 'Анна'}
CHAT = {'id': 7, 'type': 'private'}


async def main():
    application, stub = offline_application()
    helped, menus = [], {}

    async def help_command(update, context):
        helped.append(update.effective_message.text)
    application.add_handler(CommandHandler('help', help_command))
    attach_selection(application, menus)
    sent = {'message_id': 60, 'date': 1, 'chat': CHAT, 'from': {'id': 1, 'is_bot': True, 'first_name': 'Fixture'}, 'text': 'x'}
    stub.respond('sendMessage', lambda p: {**sent, 'text': p['text']})
    stub.respond('editMessageText', lambda p: {**sent, 'text': p['text']})
    stub.respond('answerCallbackQuery', True)

    def command(index, text):
        return Update.de_json({'update_id': index, 'message': {'message_id': index, 'date': 1, 'chat': CHAT, 'from': ANNA, 'text': text,
                                                               'entities': [{'type': 'bot_command', 'offset': 0, 'length': len(text)}]}}, application.bot)

    def press(index, data, user=ANNA):
        return Update.de_json({'update_id': index, 'callback_query': {'id': f'q{index}', 'from': user, 'chat_instance': 'c', 'data': data,
                                                                       'message': sent}}, application.bot)

    def edits():
        return [p for m, p in stub.calls if m == 'editMessageText']
    await application.initialize()
    try:
        await application.process_update(command(1, '/choose'))
        menu = menus[7]
        first = edits()[-1]
        assert first['message_id'] == 60 and first['text'].startswith('Выберите варианты.')
        assert first['reply_markup']['inline_keyboard'][0][0] == {'text': '□ Пакет Alpha', 'callback_data': menu.state.callback('s:alpha')}
        await application.process_update(press(2, menu.state.callback('s:alpha')))
        assert 'Выбрано: Пакет Alpha' in edits()[-1]['text'] and edits()[-1]['reply_markup']['inline_keyboard'][0][0]['text'] == '✓ Пакет Alpha'
        stale = menu.state.callback('q:inc').replace(f':{menu.state.revision}:', f':{menu.state.revision - 1}:')
        await application.process_update(press(3, stale))
        assert stub.calls[-1][1].get('text') == 'Кнопка устарела. Откройте актуальный выбор.' and len(edits()) == 2
        await application.process_update(press(4, menu.state.callback('q:inc'), user={'id': 8, 'is_bot': False, 'first_name': 'Бен'}))
        assert stub.calls[-1][1] == {'callback_query_id': 'q4', 'text': 'Это выбор другого пользователя.', 'show_alert': True}
        await application.process_update(press(5, menu.state.callback('ask')))
        confirm = edits()[-1]['reply_markup']['inline_keyboard'][0][0]
        assert confirm['text'] == 'Да: Подтвердить выбор' and menu.state.phase == 'confirming'
        await application.process_update(press(6, confirm['callback_data']))
        assert menu.state.phase == 'confirmed' and 'reply_markup' not in edits()[-1], 'the keyboard is removed'
        await application.process_update(command(7, '/help'))
        assert helped == ['/help']
    finally:
        await application.shutdown()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': stub.closed, 'sdk': 'python-telegram-bot',
                      'core_selection_markup': True, 'stale_revision_refused': True, 'foreign_user_denied': True,
                      'confirmed_once': True, 'callback_acknowledged': True, 'existing_application_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
