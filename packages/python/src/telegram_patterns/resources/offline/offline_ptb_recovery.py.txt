"""Actual python-telegram-bot Application: the reply is lost after the order is stored, the redelivered update replays it; HTTP is disabled."""
import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from telegram import Update
from telegram.ext import CommandHandler
from telegram_patterns import SQLiteOnce
from telegram_patterns.ptb import offline_application
from ptb_recovery_bot import attach_orders

USER = {'id': 7, 'is_bot': False, 'first_name': 'Анна'}
CHAT = {'id': 7, 'type': 'private'}


async def main():
    with TemporaryDirectory(prefix='ptb-recovery-') as folder:
        database = Path(folder) / 'orders.sqlite'
        once = SQLiteOnce(database)
        once.initialize()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('CREATE TABLE orders(id INTEGER PRIMARY KEY, user_id INTEGER, product TEXT)')
        application, stub = offline_application()
        helped, errors = [], []

        async def help_command(update, context):
            helped.append(update.effective_message.text)

        async def on_error(update, context):
            errors.append(type(context.error).__name__)
        application.add_handler(CommandHandler('help', help_command))
        application.add_error_handler(on_error)
        attach_orders(application, once)
        lost = [True]

        def send(parameters):
            if lost:
                lost.clear()
                raise TimeoutError('fixture: the reply was lost after the order was stored')
            return {'message_id': 90, 'date': 1, 'chat': CHAT, 'text': parameters['text']}
        stub.respond('sendMessage', send)

        def command(index, message_id, text):
            return Update.de_json({'update_id': index, 'message': {'message_id': message_id, 'date': 1, 'chat': CHAT, 'from': USER, 'text': text,
                                                                   'entities': [{'type': 'bot_command', 'offset': 0, 'length': len(text)}]}}, application.bot)
        await application.initialize()
        try:
            await application.process_update(command(1, 10, '/order'))
            assert errors == ['NetworkError'], errors
            await application.process_update(command(1, 10, '/order'))  # Telegram delivers the same update again
            assert stub.calls[-1] == ('sendMessage', {'chat_id': 7, 'text': 'Заказ №1 уже создан.'}), stub.calls[-1]
            await application.process_update(command(2, 11, '/order'))  # a new message is a new order
            assert stub.calls[-1][1]['text'] == 'Заказ №2 создан.'
            await application.process_update(command(3, 12, '/help'))
            assert helped == ['/help']
        finally:
            await application.shutdown()
        with closing(sqlite3.connect(database)) as db:
            count = db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
        assert count == 2
    print(json.dumps({'passed': True, 'network': False, 'session_closed': stub.closed, 'sdk': 'python-telegram-bot',
                      'lost_reply_replayed': True, 'effects': count, 'new_message_new_operation': True,
                      'existing_application_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
