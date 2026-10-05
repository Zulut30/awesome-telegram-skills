"""File-backed previews and outcomes; no exactly-once promise for Telegram writes."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import secrets
import time
from typing import Any

from .storage import connection


class Refused(Exception):
    """Only controlled application messages; never wrap raw SDK exception text."""


@dataclass(frozen=True)
class Context:
    bot_id: int
    chat_id: int
    thread_id: int
    actor_id: int
    forum: bool


class Store:
    def __init__(self, database: Path, bot_id: int, chats: set[int], *, now: Callable[[], float] = time.time):
        if type(bot_id) is not int or bot_id <= 0 or not chats or any(type(c) is not int or not -(2**63) < c < 0 for c in chats):
            raise ValueError('A bot and explicit negative group IDs are required')
        self.database, self.bot_id, self.chats, self.now = database, bot_id, frozenset(chats), now
        with connection(database, write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS group_meta (version INTEGER NOT NULL, bot INTEGER NOT NULL)')
            meta = db.execute('SELECT version,bot FROM group_meta').fetchall()
            if not meta: db.execute('INSERT INTO group_meta VALUES (1,?)', (bot_id,))
            elif len(meta) != 1 or tuple(meta[0]) != (1,bot_id): raise ValueError('Database belongs to another bot or schema')
            db.execute('''CREATE TABLE IF NOT EXISTS group_operations (
                key TEXT PRIMARY KEY, bot INTEGER NOT NULL, chat INTEGER NOT NULL, thread INTEGER NOT NULL,
                actor INTEGER NOT NULL, source_message INTEGER NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL,
                created REAL NOT NULL, prompt INTEGER, status TEXT NOT NULL, result TEXT,
                UNIQUE(bot,chat,source_message))''')
            db.execute('''CREATE TABLE IF NOT EXISTS group_joins (
                bot INTEGER NOT NULL, chat INTEGER NOT NULL, user INTEGER NOT NULL, stamp INTEGER NOT NULL,
                update_id INTEGER NOT NULL, state TEXT NOT NULL, query_mode INTEGER NOT NULL,
                PRIMARY KEY(bot,chat,user))''')
            db.execute('CREATE TABLE IF NOT EXISTS group_migrations (bot INTEGER, old_chat INTEGER, new_chat INTEGER, PRIMARY KEY(bot,old_chat))')

    def configured(self, chat_id: int) -> bool:
        with connection(self.database) as db:
            return chat_id in self.chats and db.execute('SELECT 1 FROM group_migrations WHERE bot=? AND old_chat=?', (self.bot_id,chat_id)).fetchone() is None

    def ensure(self, context: Context) -> None:
        if context.bot_id != self.bot_id or not self.configured(context.chat_id):
            raise Refused('Группа не включена в конфигурацию или её ID изменился. Проверьте --chat; старое подтверждение не переносится.')

    def recover(self) -> None:
        # Called only while owning ProcessLock. Never repeat external writes.
        with connection(self.database, write=True) as db:
            db.execute("UPDATE group_operations SET status='unknown' WHERE status='sending'")
            db.execute("UPDATE group_operations SET status='stale' WHERE status='draft'")
            db.execute("UPDATE group_joins SET state='unknown' WHERE state='queueing'")

    def migrate(self, old_chat: int, new_chat: int) -> None:
        if old_chat >= 0 or new_chat >= 0 or old_chat == new_chat: return
        if old_chat not in self.chats: return
        with connection(self.database, write=True) as db:
            known = db.execute('SELECT new_chat FROM group_migrations WHERE bot=? AND old_chat=?', (self.bot_id,old_chat)).fetchone()
            if known is not None and known[0] != new_chat: raise Refused('Конфликт миграции: требуется ручная сверка ID.')
            db.execute('INSERT OR IGNORE INTO group_migrations VALUES (?,?,?)', (self.bot_id,old_chat,new_chat))
            db.execute("UPDATE group_operations SET status=CASE WHEN status='sending' THEN 'unknown' ELSE 'stale' END WHERE chat=? AND status IN ('draft','ready','sending')", (old_chat,))
            db.execute("UPDATE group_joins SET state='resolved' WHERE chat=?", (old_chat,))

    def observe_join(self, chat: int, user: int, stamp: int, update_id: int, *, query: bool) -> bool:
        if not self.configured(chat): return False
        with connection(self.database, write=True) as db:
            old = db.execute('SELECT stamp,update_id FROM group_joins WHERE bot=? AND chat=? AND user=?', (self.bot_id,chat,user)).fetchone()
            if old is not None and (stamp,update_id) <= tuple(old): return False
            db.execute('''INSERT INTO group_joins VALUES (?,?,?,?,?,?,?) ON CONFLICT(bot,chat,user)
                DO UPDATE SET stamp=excluded.stamp,update_id=excluded.update_id,state=excluded.state,query_mode=excluded.query_mode''',
                (self.bot_id,chat,user,stamp,update_id,'queueing' if query else 'pending',int(query)))
            return True

    def finish_queue(self, chat: int, user: int, stamp: int, update_id: int, *, accepted: bool) -> None:
        with connection(self.database, write=True) as db:
            db.execute("UPDATE group_joins SET state=? WHERE bot=? AND chat=? AND user=? AND stamp=? AND update_id=? AND state='queueing'",
                       ('pending' if accepted else 'unknown',self.bot_id,chat,user,stamp,update_id))

    def membership(self, chat: int, user: int, stamp: int, update_id: int) -> None:
        if not self.configured(chat): return
        with connection(self.database, write=True) as db:
            old = db.execute('SELECT stamp,update_id FROM group_joins WHERE bot=? AND chat=? AND user=?', (self.bot_id,chat,user)).fetchone()
            if old is None or (stamp,update_id) > tuple(old):
                db.execute('''INSERT INTO group_joins VALUES (?,?,?,?,?,'resolved',0) ON CONFLICT(bot,chat,user)
                    DO UPDATE SET stamp=excluded.stamp,update_id=excluded.update_id,state='resolved',query_mode=0''',
                    (self.bot_id,chat,user,stamp,update_id))
            db.execute("UPDATE group_operations SET status='stale' WHERE chat=? AND actor=? AND status IN ('draft','ready')", (chat,user))

    def pending(self, context: Context) -> list[dict[str, Any]]:
        self.ensure(context)
        with connection(self.database) as db:
            return [dict(r) for r in db.execute("SELECT user,stamp,update_id FROM group_joins WHERE bot=? AND chat=? AND state='pending' AND stamp>? ORDER BY stamp,user LIMIT 30", (self.bot_id,context.chat_id,self.now()-7200))]

    def join(self, context: Context, user: int) -> dict[str, Any]:
        self.ensure(context)
        with connection(self.database) as db:
            row = db.execute("SELECT user,stamp,update_id FROM group_joins WHERE bot=? AND chat=? AND user=? AND state='pending' AND stamp>?", (self.bot_id,context.chat_id,user,self.now()-7200)).fetchone()
            if row is None: raise Refused('Нет свежей наблюдаемой заявки. Проверьте /joins; неизвестный результат требует ручной сверки.')
            return dict(row)

    def prepare(self, context: Context, source_message: int, action: str, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        self.ensure(context)
        with connection(self.database, write=True) as db:
            row = db.execute('SELECT * FROM group_operations WHERE bot=? AND chat=? AND source_message=?', (self.bot_id,context.chat_id,source_message)).fetchone()
            if row is not None:
                if row['thread'] != context.thread_id or row['actor'] != context.actor_id or row['action'] != action or json.loads(row['payload']) != payload:
                    raise Refused('Контекст повторного события изменился.')
                return dict(row), False
            key = secrets.token_hex(8)
            db.execute("INSERT INTO group_operations VALUES (?,?,?,?,?,?,?,?,?,NULL,'draft',NULL)",
                       (key,context.bot_id,context.chat_id,context.thread_id,context.actor_id,source_message,action,json.dumps(payload),self.now()))
            return dict(db.execute('SELECT * FROM group_operations WHERE key=?', (key,)).fetchone()), True

    def bind(self, key: str, prompt: int) -> None:
        with connection(self.database, write=True) as db:
            if db.execute("UPDATE group_operations SET prompt=?,status='ready' WHERE key=? AND status='draft'", (prompt,key)).rowcount != 1:
                raise Refused('Предпросмотр уже завершён. Проверьте состояние операции.')

    def owned(self, context: Context, key: str, prompt: int) -> dict[str, Any]:
        self.ensure(context)
        with connection(self.database) as db:
            row = db.execute('SELECT * FROM group_operations WHERE key=?', (key,)).fetchone()
            if row is None or (row['bot'],row['chat'],row['thread'],row['actor'],row['prompt']) != (context.bot_id,context.chat_id,context.thread_id,context.actor_id,prompt):
                raise Refused('Подтверждение принадлежит другому пользователю, группе, теме или сообщению.')
            return dict(row)

    def cancel(self, context: Context, key: str, prompt: int) -> str:
        self.owned(context,key,prompt)
        with connection(self.database, write=True) as db:
            db.execute("UPDATE group_operations SET status='cancelled' WHERE key=? AND status='ready'", (key,))
            return str(db.execute('SELECT status FROM group_operations WHERE key=?', (key,)).fetchone()[0])

    def claim(self, context: Context, key: str, prompt: int) -> str:
        self.owned(context,key,prompt)
        with connection(self.database, write=True) as db:
            row = db.execute('SELECT * FROM group_operations WHERE key=?', (key,)).fetchone()
            if row['status'] != 'ready': return str(row['status'])
            if row['created'] + 300 < self.now():
                db.execute("UPDATE group_operations SET status='stale' WHERE key=?", (key,)); return 'stale'
            payload = json.loads(row['payload'])
            if row['action'] in {'approve','decline'}:
                join = db.execute("SELECT stamp,update_id,state FROM group_joins WHERE bot=? AND chat=? AND user=?", (context.bot_id,context.chat_id,payload['user'])).fetchone()
                if join is None or tuple(join) != (payload['stamp'],payload['update_id'],'pending') or join['stamp'] <= self.now()-7200:
                    db.execute("UPDATE group_operations SET status='stale' WHERE key=?", (key,)); return 'stale'
            db.execute("UPDATE group_operations SET status='sending' WHERE key=?", (key,))
            return 'claimed'

    def finish(self, key: str, status: str, result: dict[str, Any] | None = None) -> None:
        if status not in {'done','rejected','unknown'}: raise ValueError('Invalid finish status')
        with connection(self.database, write=True) as db:
            row = db.execute('SELECT * FROM group_operations WHERE key=?', (key,)).fetchone()
            if row is None or row['status'] != 'sending': raise Refused('Операция уже завершена или требует сверки.')
            db.execute('UPDATE group_operations SET status=?,result=? WHERE key=?', (status,json.dumps(result or {}),key))
            if row['action'] in {'approve','decline'}:
                payload = json.loads(row['payload'])
                db.execute('UPDATE group_joins SET state=? WHERE bot=? AND chat=? AND user=? AND stamp=? AND update_id=?',
                           ('resolved' if status in {'done','rejected'} else 'unknown',row['bot'],row['chat'],payload['user'],payload['stamp'],payload['update_id']))
