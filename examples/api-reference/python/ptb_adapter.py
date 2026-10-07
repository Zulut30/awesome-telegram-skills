"""python-telegram-bot adapter: markup objects from JSON, literal text and an offline Application; no network."""
import asyncio
import json
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler
from telegram_patterns import MessageBuilder, inline_button, inline_markup
from telegram_patterns.ptb import StubRequest, offline_application, ptb_inline_markup, ptb_markup, ptb_text

markup = ptb_markup(inline_markup([[inline_button('Копировать', copy_text='CODE'), inline_button('Недоступно', disabled=True)]]))
assert markup.to_dict()['inline_keyboard'][0][1] == {'text': 'Недоступно', 'disabled': {}}  # Bot API 10.3 field kept in api_kwargs
assert isinstance(ptb_inline_markup(inline_markup([[inline_button('OK', callback_data='ok')]])), InlineKeyboardMarkup)
text = ptb_text(MessageBuilder().style('<b>буквально</b>', 'bold').build())
assert text['text'] == '<b>буквально</b>' and text['parse_mode'] is None and text['entities'][0].type == 'bold'


async def main() -> list[tuple[str, dict]]:
    stub = StubRequest()
    application, _ = offline_application(request=stub)
    stub.respond('sendMessage', lambda p: {'message_id': 2, 'date': 1, 'chat': {'id': p['chat_id'], 'type': 'private'}, 'text': p['text']})

    async def start(update, context):
        await update.effective_message.reply_text('Меню', reply_markup=markup)
    application.add_handler(CommandHandler('start', start))
    await application.initialize()
    try:
        await application.process_update(Update.de_json({'update_id': 1, 'message': {
            'message_id': 1, 'date': 1, 'chat': {'id': 7, 'type': 'private'}, 'from': {'id': 7, 'is_bot': False, 'first_name': 'A'},
            'text': '/start', 'entities': [{'type': 'bot_command', 'offset': 0, 'length': 6}]}}, application.bot))
    finally:
        await application.shutdown()
    return stub.calls

calls = asyncio.run(main())
assert calls[0][0] == 'sendMessage' and calls[0][1]['reply_markup'] == markup.to_dict()
print(json.dumps({'case': 'ptb_adapter', 'passed': True, 'network': False}))
