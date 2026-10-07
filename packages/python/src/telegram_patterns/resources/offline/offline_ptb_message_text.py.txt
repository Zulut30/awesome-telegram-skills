"""Actual python-telegram-bot Application and wire parameters for a long literal report; HTTP is disabled."""
import asyncio
import json

from telegram import Update
from telegram.ext import CommandHandler, Defaults
from telegram_patterns.ptb import offline_application
from ptb_message_text_bot import attach_reports

USER = {'id': 7, 'is_bot': False, 'first_name': '<b>Анна</b>'}
CHAT = {'id': 7, 'type': 'private'}


def utf16(text):
    return len(text.encode('utf-16-le')) // 2


async def main():
    # A project-wide HTML default must not reinterpret the literal text.
    application, stub = offline_application(defaults=Defaults(parse_mode='HTML'))
    helped = []

    async def help_command(update, context):
        helped.append(update.effective_message.text)
    application.add_handler(CommandHandler('help', help_command))
    attach_reports(application)
    stub.respond('sendMessage', lambda p: {'message_id': 70 + len(stub.calls), 'date': 1, 'chat': CHAT, 'text': p['text']})

    def command(index, text):
        return Update.de_json({'update_id': index, 'message': {'message_id': index, 'date': 1, 'chat': CHAT, 'from': USER, 'text': text,
                                                               'entities': [{'type': 'bot_command', 'offset': 0, 'length': len(text)}]}}, application.bot)
    await application.initialize()
    try:
        await application.process_update(command(1, '/report'))
        parts = [p for m, p in stub.calls if m == 'sendMessage']
        assert len(parts) >= 2 and all(utf16(p['text']) <= 4096 for p in parts), [utf16(p['text']) for p in parts]
        assert all('parse_mode' not in p for p in parts), 'parse_mode=None reaches the wire as no parse mode'
        first = parts[0]
        assert first['text'].startswith('Отчет\nИмя: <b>Анна</b>\nЗаметки:\n<b>буквальный текст</b>')
        assert first['entities'][:2] == [{'type': 'bold', 'offset': 0, 'length': 6}, {'type': 'italic', 'offset': 11, 'length': 11}]
        last = parts[-1]
        assert last['entities'][-1]['type'] == 'text_link' and last['entities'][-1]['url'] == 'https://core.telegram.org/bots/api'
        await application.process_update(command(2, '/help'))
        assert helped == ['/help']
    finally:
        await application.shutdown()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': stub.closed, 'sdk': 'python-telegram-bot',
                      'parts': len(parts), 'literal_text_under_html_default': True, 'entities_on_wire': True,
                      'existing_application_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
