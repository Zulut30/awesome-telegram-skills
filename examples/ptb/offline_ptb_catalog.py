"""Actual python-telegram-bot Application and wire parameters for the paged catalog; HTTP is disabled."""
import asyncio
import json

from telegram import Update
from telegram.ext import CommandHandler
from telegram_patterns.ptb import offline_application
from ptb_catalog_bot import attach_catalog

USER = {'id': 7, 'is_bot': False, 'first_name': 'Анна'}
CHAT = {'id': 7, 'type': 'private'}


async def main():
    application, stub = offline_application()
    helped = []

    async def help_command(update, context):
        helped.append(update.effective_message.text)
    application.add_handler(CommandHandler('help', help_command))  # an existing handler of the project
    attach_catalog(application)
    message = {'message_id': 50, 'date': 1, 'chat': CHAT, 'text': 'x'}
    stub.respond('sendMessage', lambda p: {**message, 'text': p['text']})
    stub.respond('editMessageText', lambda p: {**message, 'text': p['text']})
    stub.respond('answerCallbackQuery', True)

    def command(index, text):
        return Update.de_json({'update_id': index, 'message': {'message_id': index, 'date': 1, 'chat': CHAT, 'from': USER, 'text': text,
                                                               'entities': [{'type': 'bot_command', 'offset': 0, 'length': len(text)}]}}, application.bot)

    def press(index, data):
        return Update.de_json({'update_id': index, 'callback_query': {'id': f'q{index}', 'from': USER, 'chat_instance': 'c', 'data': data,
                                                                       'message': message}}, application.bot)
    await application.initialize()
    try:
        await application.process_update(command(1, '/start'))
        method, sent = stub.calls[-1]
        rows = sent['reply_markup']['inline_keyboard']
        assert method == 'sendMessage' and sent['text'].startswith('Пример каталога · страница 1/3')
        assert rows[0] == [{'text': 'Компонент 1', 'callback_data': 'act:item-1', 'style': 'primary'},
                           {'text': 'Компонент 2', 'callback_data': 'act:item-2', 'style': 'primary'}]
        assert rows[-1] == [{'text': 'Далее →', 'callback_data': 'catalog-page:1'}]
        await application.process_update(press(2, 'catalog-page:2'))
        edited = [p for m, p in stub.calls if m == 'editMessageText'][-1]
        assert edited['text'].startswith('Пример каталога · страница 3/3') and edited['reply_markup']['inline_keyboard'][-1] == [
            {'text': '← Назад', 'callback_data': 'catalog-page:1'}]
        await application.process_update(press(3, 'catalog-page:99x'))
        assert stub.calls[-1] == ('answerCallbackQuery', {'callback_query_id': 'q3', 'text': 'Откройте актуальное меню командой /start.'})
        await application.process_update(press(4, 'act:item-7'))
        assert stub.calls[-1] == ('sendMessage', {'chat_id': 7, 'text': 'Вы выбрали: Компонент 7.'})
        await application.process_update(command(5, '/help'))
        assert helped == ['/help']
    finally:
        await application.shutdown()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': stub.closed, 'sdk': 'python-telegram-bot',
                      'core_markup_on_wire': True, 'page_navigation': True, 'stale_callback_refused': True,
                      'callback_acknowledged': True, 'existing_application_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
