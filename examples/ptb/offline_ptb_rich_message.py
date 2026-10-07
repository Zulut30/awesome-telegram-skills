"""Actual python-telegram-bot Application: sendRichMessage through do_api_request and the text fallback; HTTP is disabled."""
import asyncio
import json

from telegram import Update
from telegram.ext import CommandHandler
from telegram_patterns.ptb import offline_application
from ptb_rich_message_bot import attach_order_cards, order_card

USER = {'id': 7, 'is_bot': False, 'first_name': 'Анна'}
CHAT = {'id': 7, 'type': 'private'}


async def main():
    rich = {'value': True}
    application, stub = offline_application()
    helped = []

    async def help_command(update, context):
        helped.append(update.effective_message.text)
    application.add_handler(CommandHandler('help', help_command))
    attach_order_cards(application, rich_supported=lambda update: rich['value'])
    message = {'message_id': 80, 'date': 1, 'chat': CHAT}
    stub.respond('sendRichMessage', lambda p: {**message, 'text': ''})
    stub.respond('sendMessage', lambda p: {**message, 'text': p['text']})
    stub.respond('answerCallbackQuery', True)

    def command(index, text):
        return Update.de_json({'update_id': index, 'message': {'message_id': index, 'date': 1, 'chat': CHAT, 'from': USER, 'text': text,
                                                               'entities': [{'type': 'bot_command', 'offset': 0, 'length': len(text)}]}}, application.bot)
    await application.initialize()
    try:
        await application.process_update(command(1, '/order'))
        method, sent = stub.calls[-1]
        assert method == 'sendRichMessage' and sent == {'chat_id': 7, 'rich_message': order_card(42).as_input()}, 'the builder JSON is on the wire'
        rich['value'] = False
        await application.process_update(command(2, '/order'))
        fallback = [p for m, p in stub.calls if m == 'sendMessage']
        assert fallback[-1]['text'].startswith('Заказ №42') and fallback[-1]['reply_markup'] == {
            'inline_keyboard': [[{'text': 'Подтвердить', 'callback_data': 'order:confirm:42', 'style': 'success'}]]}
        assert 'Книга | 1 | 500 ₽' in fallback[-1]['text'] and fallback[-1]['entities'][0]['type'] == 'bold'
        await application.process_update(Update.de_json({'update_id': 3, 'callback_query': {
            'id': 'q3', 'from': USER, 'chat_instance': 'c', 'data': 'order:confirm:42', 'message': {**message, 'text': 'x'}}}, application.bot))
        assert stub.calls[-1] == ('answerCallbackQuery', {'callback_query_id': 'q3', 'text': 'Запрос принят'})
        await application.process_update(command(4, '/help'))
        assert helped == ['/help']
    finally:
        await application.shutdown()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': stub.closed, 'sdk': 'python-telegram-bot',
                      'newer_method_via_do_api_request': True, 'builder_json_on_wire': True, 'text_fallback_with_keyboard': True,
                      'callback_acknowledged': True, 'existing_application_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
