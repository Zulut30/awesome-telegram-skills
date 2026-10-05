"""Attach typed forms to an existing Dispatcher; business effect uses file SQLite."""
from __future__ import annotations

import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from telegram_patterns import BotSettings, SQLiteOnce
from telegram_patterns.aiogram import (ContactField, DateField, DialogSubmission, EmailField, FileField,
    LocationField, NumberField, PhoneField, dialog_form_router, run_bot)


def fields():
    return [NumberField('amount','Количество','Введите количество от 1 до 100.',minimum=1,maximum=100,decimal_places=0),
        EmailField('email','Email','Укажите email.'),
        PhoneField('phone','Телефон','Укажите номер с + и кодом страны.'),
        DateField('date','Дата','Введите дату в формате ГГГГ-ММ-ДД.',minimum='2026-10-05'),
        FileField('file','Документ','Пришлите один PDF ответом на этот вопрос.',max_bytes=1024*1024,mime_types=('application/pdf',)),
        ContactField('contact','Контакт','Поделитесь своим контактом через кнопку.'),
        LocationField('location','Место','Поделитесь статичной геопозицией через кнопку.')]


class Requests:
    """Example policy: authenticated private actors create only their own request.

    No entitlement or external action. File metadata isn't content validation.
    Production supplies persistent FSM/isolation and retention for personal data.
    """
    def __init__(self,database:Path):
        self.once=SQLiteOnce(database);self.once.initialize()
        with closing(sqlite3.connect(database)) as connection,connection:
            connection.execute('CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, actor INTEGER NOT NULL, body TEXT NOT NULL)')

    async def submit(self,submission:DialogSubmission)->str:
        if submission.actor_id != submission.chat_id or set(submission.values) != {f.name for f in fields()}:
            raise ValueError('Invalid private request scope')
        values={f.name:f.restore(submission.values[f.name]) for f in fields()}
        if values['contact']['user_id']!=submission.actor_id: raise ValueError('Contact owner mismatch')
        def persist():
            # Current authorization policy checked before effect AND cached replay.
            if submission.actor_id <= 0: raise PermissionError('Actor is not allowed')
            return self.once.run(f'bot:{submission.bot_id}:actor:{submission.actor_id}:dialog',submission.operation_id,values,
                lambda db:{'id':db.execute('INSERT INTO requests(actor,body) VALUES (?,?)',
                    (submission.actor_id,json.dumps(values,ensure_ascii=False))).lastrowid})
        result=await asyncio.to_thread(persist)
        return f"Заявка №{result.value['id']} сохранена."


def attach_dialog(dispatcher:Dispatcher,service:Requests):
    # Preserve existing handlers, commands, storage and middleware.
    dispatcher.include_router(dialog_form_router(fields(),service.submit,name='request',command='collect'))


async def main():
    database=Path(sys.argv[1]) if len(sys.argv)>1 else Path('requests.sqlite')
    dispatcher=Dispatcher(events_isolation=SimpleEventIsolation())
    attach_dialog(dispatcher,Requests(database))
    await run_bot(dispatcher,BotSettings.from_env())


if __name__=='__main__':asyncio.run(main())
