"""Private application form. Set BOT_TOKEN for a test bot; uses local SQLite."""
from __future__ import annotations

import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import sys

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import BotCommand

from telegram_patterns import BotSettings, SQLiteOnce
from telegram_patterns.aiogram import (CommandReply, FormSubmission, InvalidField, TextField,
                                      command_router, run_bot, text_form_router)


def topic(value: str) -> str:
    value = value.casefold()
    if value not in {'python', 'typescript'}:
        raise InvalidField('Введите Python для бота или TypeScript для Mini App.')
    return value


class Applications:
    """Public create-only example; durable business data is separate from FSM."""
    def __init__(self, database: Path) -> None:
        self.once = SQLiteOnce(database)
        self.once.initialize()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS applications '
                       '(id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL, topic TEXT NOT NULL, brief TEXT NOT NULL)')

    async def submit(self, submission: FormSubmission) -> str:
        # Recheck the service contract before both effect and replay. Anyone may
        # create their OWN example application; there is no private-object read.
        if submission.actor_id != submission.chat_id or set(submission.values) != {'topic', 'brief'}:
            raise ValueError('Invalid application scope')
        values = {'topic': topic(submission.values['topic']),
                  'brief': TextField('brief', 'Задача', 'Опишите задачу.', max_length=256).read(submission.values['brief'])}
        def persist():
            return self.once.run(f'bot:{submission.bot_id}:actor:{submission.actor_id}:application',
                                 submission.operation_id, values,
                                 lambda db: {'id': db.execute(
                                     'INSERT INTO applications(actor_id,topic,brief) VALUES (?,?,?)',
                                     (submission.actor_id, values['topic'], values['brief'])).lastrowid})
        result = await asyncio.to_thread(persist)
        return f"Заявка №{result.value['id']} сохранена."


def create_app(database: Path) -> Dispatcher:
    service = Applications(database)
    # MemoryStorage is transient; configure the HOST storage/isolation if forms
    # must survive a restart or run on multiple workers. Keep pending identity
    # until reconciliation; do not expire unknown submissions as ordinary drafts.
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    dispatcher.include_router(text_form_router([
        TextField('topic', 'Стек', 'Python для бота или TypeScript для Mini App?', validate=topic),
        TextField('brief', 'Задача', 'Кратко опишите задачу. Не присылайте пароли и token.', max_length=256),
    ], service.submit))
    dispatcher.include_router(command_router([
        CommandReply('start', 'Начать', 'Это пример формы заявки. Заполнить: /apply. Помощь: /help.'),
        CommandReply('help', 'Помощь', '/apply — новая форма · /back — исправить · /cancel — отменить.\n'
                     'После проверки нажмите «Отправить». При ошибке повторяется та же заявка.'),
    ]))
    return dispatcher


async def main() -> None:
    try:
        settings = BotSettings.from_env()
    except ValueError as error:
        raise SystemExit(str(error)) from None
    database = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('applications.sqlite')
    dispatcher = create_app(database)
    # Explicit menu replacement only for the test bot.
    await run_bot(dispatcher, settings, commands=[BotCommand(command=command, description=description)
        for command, description in [('start', 'Начать'), ('apply', 'Заполнить заявку'), ('help', 'Помощь'),
                                     ('back', 'Предыдущий шаг'), ('cancel', 'Отменить форму')]])


if __name__ == '__main__': asyncio.run(main())
