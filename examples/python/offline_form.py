"""Run the real form composition, validation, editing and duplicate confirmation without network."""
from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile

from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from telegram_patterns.testing import StubSession
from form_bot import create_app


async def main() -> None:
    date = datetime(2026, 10, 3, tzinfo=timezone.utc)
    actor = User(id=42, is_bot=False, first_name='Fixture')
    replies = []
    def response(method):
        message = Message(message_id=1000 + len(replies), date=date, chat=Chat(id=method.chat_id, type='private'), text=method.text)
        replies.append((method, message))
        return message
    session = StubSession().respond(SendMessage, response).respond(AnswerCallbackQuery, True)
    with tempfile.TemporaryDirectory(prefix='telegram-form-example-') as folder:
        database = Path(folder) / 'applications.sqlite'
        dispatcher = create_app(database)
        async with Bot('100:OFFLINE_FIXTURE', session=session) as bot:
            try:
                for index, text in enumerate(('/apply', 'invalid', 'Python', 'Учебный бот', '/back', 'Бот с каталогом'), start=1):
                    await dispatcher.feed_update(bot, Update(update_id=index, message=Message(
                        message_id=index, date=date, chat=Chat(id=42, type='private'), from_user=actor, text=text)))
                method, message = replies[-1]
                data = method.reply_markup.inline_keyboard[0][0].callback_data
                for index in (7, 8):
                    await dispatcher.feed_update(bot, Update(update_id=index, callback_query=CallbackQuery(
                        id=f'fixture-{index}', from_user=actor, chat_instance='fixture', message=message, data=data)))
                with closing(sqlite3.connect(database)) as db:
                    rows = db.execute('SELECT actor_id,topic,brief FROM applications').fetchall()
                assert rows == [(42, 'python', 'Бот с каталогом')], rows
                assert len([call for call in session.calls if isinstance(call, AnswerCallbackQuery)]) == 2
                assert dispatcher.storage is not None
                context = dispatcher.fsm.get_context(bot=bot, chat_id=42, user_id=42)
                assert await context.get_state() is None
                assert await context.get_data() == {}
            finally:
                await dispatcher.fsm.close()
    print(json.dumps({'passed': True, 'network': False, 'applications': len(rows), 'session_closed': session.closed,
                      'scenario': 'invalid input -> edit -> review -> submit -> stale confirmation'}, ensure_ascii=False))


if __name__ == '__main__': asyncio.run(main())
