"""Owner-scoped booking and durable reminder intent using public SQLiteOnce."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import time
from collections.abc import Callable

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from telegram_patterns import PermissionDenied, SQLiteOnce, ValidationFailure
from telegram_patterns.aiogram import FormSubmission, TextField
from .storage import connection, io_call


class SlotUnavailable(ValidationFailure):
    pass


@dataclass(frozen=True)
class Actor:
    bot_id: int
    user_id: int
    chat_id: int


class Service:
    def __init__(self, database: Path, bot_id: int, *, now: Callable[[], float] = time.time):
        if type(bot_id) is not int or bot_id <= 0: raise ValueError('Invalid bot identity')
        self.database, self.bot_id, self.now = database, bot_id, now
        with connection(database, write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS service_schema(version INTEGER NOT NULL)')
            version = db.execute('SELECT version FROM service_schema').fetchall()
            if version and [r[0] for r in version] != [1]: raise ValueError('Service schema requires migration')
            if not version: db.execute('INSERT INTO service_schema VALUES (1)')
            for sql in (
                'CREATE TABLE IF NOT EXISTS service_fsm(key TEXT PRIMARY KEY,state TEXT,data TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS service_slots(bot_id INTEGER,id TEXT,label TEXT,starts_at INTEGER,PRIMARY KEY(bot_id,id))',
                'CREATE TABLE IF NOT EXISTS service_preferences(bot_id INTEGER,actor_id INTEGER,enabled INTEGER NOT NULL,PRIMARY KEY(bot_id,actor_id))',
                'CREATE TABLE IF NOT EXISTS service_bookings(id INTEGER PRIMARY KEY,bot_id INTEGER,actor_id INTEGER,slot_id TEXT,note TEXT,status TEXT NOT NULL,operation_id TEXT,UNIQUE(bot_id,actor_id,operation_id))',
                "CREATE UNIQUE INDEX IF NOT EXISTS service_one_slot ON service_bookings(bot_id,slot_id) WHERE status='booked'",
                'CREATE TABLE IF NOT EXISTS service_notifications(id INTEGER PRIMARY KEY,booking_id INTEGER UNIQUE,bot_id INTEGER,actor_id INTEGER,due_at INTEGER,status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,message_id INTEGER)',
            ): db.execute(sql)
            if not db.execute('SELECT 1 FROM service_slots WHERE bot_id=?', (bot_id,)).fetchone():
                # Seed once. Restart never reopens a consumed/past slot.
                start = int(now()) + 3600
                db.executemany('INSERT INTO service_slots VALUES (?,?,?,?)', [
                    (bot_id, f'slot-{i}', 'Консультация' if i < 3 else 'Разбор проекта', start + (i-1)*3600)
                    for i in range(1, 5)])
        self.once = SQLiteOnce(database)
        self.once.initialize()

    def authorize(self, actor: Actor) -> None:
        if (type(actor.bot_id) is not int or actor.bot_id != self.bot_id or type(actor.chat_id) is not int or type(actor.user_id) is not int or
                actor.user_id <= 0 or actor.user_id != actor.chat_id):
            raise PermissionDenied()

    def slots(self) -> list[dict]:
        with connection(self.database) as db:
            rows = db.execute("SELECT s.* FROM service_slots s WHERE s.bot_id=? AND s.starts_at>? "
                "AND NOT EXISTS(SELECT 1 FROM service_bookings b WHERE b.bot_id=s.bot_id AND b.slot_id=s.id AND b.status='booked') ORDER BY starts_at",
                (self.bot_id, int(self.now()))).fetchall()
            return [dict(r) for r in rows]

    def bookings(self, actor: Actor) -> list[dict]:
        self.authorize(actor)
        with connection(self.database) as db:
            return [dict(r) for r in db.execute('SELECT b.id,b.status,s.label,s.starts_at,n.status AS reminder_status FROM service_bookings b '
                'JOIN service_slots s ON s.bot_id=b.bot_id AND s.id=b.slot_id LEFT JOIN service_notifications n ON n.booking_id=b.id WHERE b.bot_id=? AND b.actor_id=? ORDER BY b.id',
                (self.bot_id, actor.user_id))]

    def booking(self, actor: Actor, booking_id: int) -> dict:
        self.authorize(actor)
        with connection(self.database) as db:
            row = db.execute('SELECT * FROM service_bookings WHERE bot_id=? AND actor_id=? AND id=?',
                             (self.bot_id, actor.user_id, booking_id)).fetchone()
            if row is None: raise PermissionDenied()
            return dict(row)

    def create(self, actor: Actor, operation_id: str, slot_id: str, note: str) -> dict:
        self.authorize(actor)  # Before a new effect AND saved-result replay.
        if not re.fullmatch(r'[a-f0-9]{16}', operation_id): raise ValidationFailure()
        if not re.fullmatch(r'slot-[1-4]', slot_id): raise SlotUnavailable()
        note = TextField('note', 'Комментарий', 'Краткий комментарий', max_length=256).read(note)
        def apply(db: sqlite3.Connection):
            available = db.execute('SELECT starts_at FROM service_slots WHERE bot_id=? AND id=?',
                                   (self.bot_id, slot_id)).fetchone()
            if not available or available[0] <= self.now() or db.execute(
                    "SELECT 1 FROM service_bookings WHERE bot_id=? AND slot_id=? AND status='booked'",
                    (self.bot_id, slot_id)).fetchone(): raise SlotUnavailable()
            booking_id = db.execute("INSERT INTO service_bookings(bot_id,actor_id,slot_id,note,status,operation_id) VALUES (?,?,?,?,'booked',?)",
                (self.bot_id, actor.user_id, slot_id, note, operation_id)).lastrowid
            db.execute("INSERT INTO service_notifications(booking_id,bot_id,actor_id,due_at,status) VALUES (?,?,?,?,'pending')",
                (booking_id, self.bot_id, actor.user_id, available[0]-900))
            return {'id': booking_id}
        result = self.once.run(f'service:{self.bot_id}:actor:{actor.user_id}', operation_id,
                               {'slot_id': slot_id, 'note': note}, apply)
        booking = self.booking(actor, result.value['id'])
        return {'id': booking['id'], 'status': booking['status'], 'replayed': result.replayed}

    async def submit(self, submission: FormSubmission) -> str:
        actor = Actor(submission.bot_id, submission.actor_id, submission.chat_id)
        if set(submission.values) != {'slot', 'note'}: raise ValidationFailure()
        try:
            result = await io_call(self.create, actor, submission.operation_id,
                                            submission.values['slot'], submission.values['note'])
        except SlotUnavailable:
            # Known local rejection, no effect. Do not freeze a definitively rejected form.
            return 'Слот уже недоступен. Запись не создана. Выберите другой в /slots и начните /book.'
        state = 'подтверждена' if result['status']=='booked' else 'отменена'
        return f"Запись №{result['id']} {state}. Проверить: /status. Напоминания: /reminders_on или /reminders_off."

    def cancel(self, actor: Actor, booking_id: int) -> None:
        self.booking(actor, booking_id)
        with connection(self.database, write=True) as db:
            db.execute("UPDATE service_bookings SET status='cancelled' WHERE id=? AND bot_id=? AND actor_id=?",
                       (booking_id, self.bot_id, actor.user_id))
            db.execute("UPDATE service_notifications SET status='skipped' WHERE booking_id=? AND status='pending'", (booking_id,))

    def reminders(self, actor: Actor, enabled: bool) -> None:
        self.authorize(actor)
        if type(enabled) is not bool: raise ValidationFailure()
        with connection(self.database, write=True) as db:
            db.execute('INSERT INTO service_preferences VALUES (?,?,?) ON CONFLICT(bot_id,actor_id) DO UPDATE SET enabled=excluded.enabled',
                       (self.bot_id, actor.user_id, int(enabled)))
            if not enabled:
                db.execute("UPDATE service_notifications SET status='skipped' WHERE bot_id=? AND actor_id=? AND status='pending'", (self.bot_id, actor.user_id))
            else:
                # Explicit consent may reactivate only a never-attempted future job.
                db.execute("UPDATE service_notifications SET status='pending' WHERE bot_id=? AND actor_id=? AND status='skipped' AND attempts=0 "
                    "AND booking_id IN(SELECT b.id FROM service_bookings b JOIN service_slots s ON s.bot_id=b.bot_id AND s.id=b.slot_id WHERE b.status='booked' AND s.starts_at>?)",
                    (self.bot_id, actor.user_id, int(self.now())))

    def recover(self) -> int:
        with connection(self.database, write=True) as db:
            return db.execute("UPDATE service_notifications SET status='unknown' WHERE bot_id=? AND status='sending'", (self.bot_id,)).rowcount

    def claim(self) -> dict | None:
        with connection(self.database, write=True) as db:
            db.execute("UPDATE service_notifications SET status='skipped' WHERE bot_id=? AND status='pending' AND booking_id IN("
                "SELECT b.id FROM service_bookings b JOIN service_slots s ON s.bot_id=b.bot_id AND s.id=b.slot_id WHERE b.status!='booked' OR s.starts_at<=?)",
                (self.bot_id, int(self.now())))
            row = db.execute("SELECT n.*,s.label,s.starts_at FROM service_notifications n JOIN service_bookings b ON b.id=n.booking_id AND b.bot_id=n.bot_id AND b.actor_id=n.actor_id "
                "JOIN service_slots s ON s.bot_id=b.bot_id AND s.id=b.slot_id JOIN service_preferences p ON p.bot_id=n.bot_id AND p.actor_id=n.actor_id "
                "WHERE n.bot_id=? AND n.status='pending' AND n.due_at<=? AND p.enabled=1 AND b.status='booked' ORDER BY n.due_at,n.id LIMIT 1",
                (self.bot_id, int(self.now()))).fetchone()
            if not row: return None
            db.execute("UPDATE service_notifications SET status='sending',attempts=attempts+1 WHERE id=?", (row['id'],))
            return {**dict(row), 'attempts': row['attempts']+1}

    def finish(self, job: dict, status: str, message_id: int | None = None, delay: int = 0) -> None:
        if status not in {'sent', 'unknown', 'blocked', 'pending', 'failed'}: raise ValueError('Invalid job state')
        with connection(self.database, write=True) as db:
            db.execute('UPDATE service_notifications SET status=?,message_id=?,due_at=? WHERE id=? AND bot_id=? AND actor_id=?',
                (status, message_id, int(self.now())+delay, job['id'], self.bot_id, job['actor_id']))
            if status == 'blocked':
                db.execute('UPDATE service_preferences SET enabled=0 WHERE bot_id=? AND actor_id=?', (self.bot_id, job['actor_id']))
                db.execute("UPDATE service_notifications SET status='skipped' WHERE bot_id=? AND actor_id=? AND status='pending'", (self.bot_id, job['actor_id']))

    async def deliver_one(self, bot: Bot) -> str:
        if bot.id != self.bot_id: raise PermissionDenied()
        job = await io_call(self.claim)
        if job is None: return 'idle'
        date = datetime.fromtimestamp(job['starts_at'], timezone.utc).strftime('%d.%m %H:%M UTC')
        try:
            message = await bot.send_message(job['actor_id'], f"Напоминание: запись №{job['booking_id']}, {job['label']}, {date}. /status", parse_mode=None)
        except TelegramForbiddenError:
            await io_call(self.finish, job, 'blocked'); return 'blocked'
        except TelegramRetryAfter as error:
            status = 'pending' if job['attempts'] < 3 else 'failed'
            await io_call(self.finish, job, status, None, max(1, error.retry_after)); return status
        except BaseException as error:
            await io_call(self.finish, job, 'unknown')
            if not isinstance(error, Exception): raise
            return 'unknown'
        await io_call(self.finish, job, 'sent', message.message_id)
        return 'sent'
