"""python-telegram-bot: an order is created once; a lost response is reconciled with the same key; no polling on import."""
import asyncio
import sqlite3
from typing import Any

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram_patterns import SQLiteOnce


def attach_orders(application: Application, once: SQLiteOnce) -> None:  # type: ignore[type-arg]
    """once owns the orders table; the operation key comes from the chat and message, never from the text."""

    async def order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message, user = update.effective_message, update.effective_user
        if message is None or user is None:
            return
        scope, key = f'user:{user.id}', f'order:{message.chat.id}:{message.message_id}'  # a redelivered update has the same key

        def create(db: sqlite3.Connection) -> dict[str, Any]:
            cursor = db.execute('INSERT INTO orders(user_id, product) VALUES (?, ?)', (user.id, 'book'))
            return {'id': cursor.lastrowid}
        result = await asyncio.to_thread(once.run, scope, key, {'product': 'book'}, create)  # SQLite off the event loop
        text = f'Заказ №{result.value["id"]} уже создан.' if result.replayed else f'Заказ №{result.value["id"]} создан.'
        await message.reply_text(text)

    application.add_handler(CommandHandler('order', order))
