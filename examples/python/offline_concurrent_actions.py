"""Offline server-owned button intents: two workers, one local business effect.

Install the local Python package, then run this file. No Telegram token or SDK
is needed. In a real adapter build Origin from the verified incoming update;
the button carries only the opaque operation ID returned by issue().
"""

from __future__ import annotations

import json
import multiprocessing
import re
import secrets
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path

from telegram_patterns import ConflictFailure, OnceResult, PermissionDenied, SQLiteOnce


@dataclass(frozen=True)
class Origin:
    bot_id: int
    chat_id: int
    actor_id: int
    message_id: int
    topic_id: int | None = None

    def scope(self) -> str:
        values = (self.bot_id, self.chat_id, self.actor_id, self.message_id, self.topic_id)
        if any(type(value) is not int for value in values[:4]):
            raise ValueError('Use verified integer Telegram identifiers')
        if self.bot_id <= 0 or self.chat_id == 0 or self.actor_id <= 0 or self.message_id <= 0:
            raise ValueError('Invalid Telegram origin')
        if self.topic_id is not None and (type(self.topic_id) is not int or self.topic_id <= 0):
            raise ValueError('Invalid topic identifier')
        return json.dumps(values, separators=(',', ':'))


class CounterService:
    """Project-specific domain rules; SQLiteOnce does not infer these rules."""

    def __init__(self, database: str | Path):
        self.database = str(database)
        self.once = SQLiteOnce(database)

    def initialize_demo(self, origin: Origin) -> None:
        """Only for this temporary demo; production owns its schema migrations."""
        self.once.initialize()
        origin.scope()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.executescript('''
                CREATE TABLE counter (
                    id INTEGER PRIMARY KEY, bot_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
                    topic_id INTEGER, revision INTEGER NOT NULL, value INTEGER NOT NULL
                );
                CREATE TABLE access (
                    counter_id INTEGER NOT NULL, actor_id INTEGER NOT NULL,
                    allowed INTEGER NOT NULL CHECK(allowed IN (0,1)),
                    PRIMARY KEY(counter_id,actor_id)
                );
                CREATE TABLE intents (
                    operation_id TEXT PRIMARY KEY, scope TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE changes (
                    id INTEGER PRIMARY KEY, counter_id INTEGER NOT NULL, value INTEGER NOT NULL
                );
            ''')
            connection.execute(
                'INSERT INTO counter VALUES(1,?,?,?,1,0)',
                (origin.bot_id, origin.chat_id, origin.topic_id),
            )
            connection.execute('INSERT INTO access VALUES(1,?,1)', (origin.actor_id,))

    @staticmethod
    def _current(connection: sqlite3.Connection, origin: Origin) -> tuple[int, int]:
        row = connection.execute(
            '''SELECT c.revision,c.value FROM counter c JOIN access a ON a.counter_id=c.id
               WHERE c.id=1 AND c.bot_id=? AND c.chat_id=? AND c.topic_id IS ?
                 AND a.actor_id=? AND a.allowed=1''',
            (origin.bot_id, origin.chat_id, origin.topic_id, origin.actor_id),
        ).fetchone()
        if row is None:
            raise PermissionDenied('Current operation access denied')
        return int(row[0]), int(row[1])

    def issue(self, origin: Origin, target: int) -> str:
        """Create once when rendering the action, then reuse this ID on retries."""
        scope = origin.scope()
        if type(target) is not int or not 0 <= target <= 100:
            raise ValueError('Counter target must be an integer between 0 and 100')
        with closing(sqlite3.connect(self.database, isolation_level=None)) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                revision, _value = self._current(connection, origin)
                payload = json.dumps({'counter_id': 1, 'revision': revision, 'target': target}, sort_keys=True)
                operation_id = secrets.token_hex(16)
                connection.execute('INSERT INTO intents VALUES(?,?,?)', (operation_id, scope, payload))
                connection.commit()
                return operation_id
            except BaseException:
                connection.rollback()
                raise

    def execute(self, origin: Origin, operation_id: str) -> OnceResult:
        scope = origin.scope()
        if not isinstance(operation_id, str) or re.fullmatch(r'[0-9a-f]{32}', operation_id) is None:
            raise PermissionDenied('Current operation access denied')
        # Read the server's intent, never revision/target/user_id from callback data.
        with closing(sqlite3.connect(self.database)) as connection:
            intent = connection.execute(
                'SELECT scope,payload FROM intents WHERE operation_id=?', (operation_id,)
            ).fetchone()
        if intent is None or intent[0] != scope:
            raise PermissionDenied('Current operation access denied')
        serialized = str(intent[1])
        payload = json.loads(serialized)

        def check(connection: sqlite3.Connection, replayed: bool) -> bool:
            # Recheck the durable intent and CURRENT permissions under the writer
            # lock, even if the ledger already has a successful receipt.
            current = connection.execute(
                'SELECT scope,payload FROM intents WHERE operation_id=?', (operation_id,)
            ).fetchone()
            if current is None or tuple(current) != (scope, serialized):
                return False
            revision, _value = self._current(connection, origin)
            # The original effect itself advanced revision: replay may return
            # its old receipt, but a different new intent must use current state.
            if not replayed and revision != payload['revision']:
                raise ConflictFailure('Refresh the counter before creating another action')
            return True

        def apply(connection: sqlite3.Connection) -> dict[str, int]:
            cursor = connection.execute('INSERT INTO changes(counter_id,value) VALUES(1,?)', (payload['target'],))
            connection.execute('UPDATE counter SET value=?,revision=revision+1 WHERE id=1', (payload['target'],))
            assert cursor.lastrowid is not None
            return {'change_id': cursor.lastrowid, 'value': payload['target'], 'revision': payload['revision'] + 1}

        return self.once.run_guarded(scope, operation_id, payload, apply, check=check)


def _worker(database: str, origin: Origin, operation_id: str, barrier, results) -> None:
    barrier.wait(timeout=10)
    result = CounterService(database).execute(origin, operation_id)
    results.put({'replayed': result.replayed, 'value': result.value})


def main() -> None:
    origin = Origin(bot_id=100, chat_id=-42, actor_id=42, message_id=900, topic_id=7)
    with tempfile.TemporaryDirectory(prefix='guarded action demo ') as directory:
        database = str(Path(directory) / 'project.sqlite')
        service = CounterService(database)
        service.initialize_demo(origin)
        operation_id = service.issue(origin, 5)
        stale_id = service.issue(origin, 8)
        context = multiprocessing.get_context('spawn')
        barrier, results = context.Barrier(2), context.Queue()
        workers = [
            context.Process(target=_worker, args=(database, origin, operation_id, barrier, results)) for _ in range(2)
        ]
        try:
            for worker in workers:
                worker.start()
            receipts = [results.get(timeout=15) for _ in workers]
            for worker in workers:
                worker.join(timeout=10)
                assert worker.exitcode == 0
            assert sorted(receipt['replayed'] for receipt in receipts) == [False, True]
            assert receipts[0]['value'] == receipts[1]['value']
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                worker.join(timeout=5)
                worker.close()
            results.close()
            results.join_thread()

        restarted = CounterService(database)
        assert restarted.execute(origin, operation_id).replayed
        for denied_origin in (
            replace(origin, bot_id=101),
            replace(origin, chat_id=-43),
            replace(origin, actor_id=43),
            replace(origin, message_id=901),
            replace(origin, topic_id=8),
        ):
            try:
                restarted.execute(denied_origin, operation_id)
            except PermissionDenied:
                pass
            else:
                raise AssertionError('Foreign origin received a receipt')
        try:
            restarted.execute(origin, stale_id)
        except ConflictFailure:
            pass
        else:
            raise AssertionError('Stale intent performed a second effect')
        with closing(sqlite3.connect(database)) as connection, connection:
            assert connection.execute('SELECT count(*) FROM changes').fetchone()[0] == 1
            connection.execute('UPDATE access SET allowed=0 WHERE actor_id=?', (origin.actor_id,))
        try:
            restarted.execute(origin, operation_id)
        except PermissionDenied:
            pass
        else:
            raise AssertionError('Revoked actor received a receipt')
        print(
            json.dumps(
                {
                    'workers': receipts,
                    'business_writes': 1,
                    'restart_replay': True,
                    'foreign_origin_denied': True,
                    'stale_intent_denied': True,
                    'revoked_replay_denied': True,
                },
                sort_keys=True,
            )
        )


if __name__ == '__main__':
    main()
