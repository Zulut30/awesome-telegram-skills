"""One business+intent commit, lost external response, explicit reconciliation.

No Telegram calls: a second SQLite file models an observable remote service.
It deliberately has no operation-key uniqueness: retrying would create a duplicate.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from telegram_patterns import SQLiteOnce
from telegram_patterns.outbox import SQLiteOutbox

SCOPE = 'bot:100:orders'
KEY = 'order-7:accepted'


def place_order(database: str):
    once, outbox = SQLiteOnce(database), SQLiteOutbox(database)

    def check(connection: sqlite3.Connection, replayed: bool) -> bool:
        # actor=42 is supplied by the verified adapter, never by request JSON.
        # Production also checks object/origin/revision, as in concurrent-actions.
        row = connection.execute('SELECT enabled FROM access WHERE actor=42').fetchone()
        return row is not None and row[0] == 1

    def apply(connection: sqlite3.Connection) -> dict[str, str]:
        connection.execute("INSERT INTO orders VALUES('order-7',42,'accepted')")
        outbox.enqueue(
            connection, SCOPE, KEY, {'method': 'sendMessage', 'chat_id': 42, 'text': 'Order accepted'}, now=100
        )
        return {'order_id': 'order-7', 'status': 'accepted'}

    return once.run_guarded('actor:42:place-order', 'order-7', {'product_id': 7}, apply, check=check)


def sender_loses_response(database: str, provider: str) -> None:
    outbox = SQLiteOutbox(database)
    claim = outbox.claim(SCOPE, 'sender-1', lease_seconds=10, now=100)
    assert claim is not None
    # Claim is committed before this external effect. In a real adapter, use a
    # bounded timeout. Check current sending permissions before the call.
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute('SELECT enabled FROM access WHERE actor=42').fetchone() == (1,)
    with closing(sqlite3.connect(provider)) as connection, connection:
        connection.execute(
            'INSERT INTO messages(intent,text) VALUES(?,?)', (claim.operation_key, claim.payload['text'])
        )
    os._exit(84)  # provider committed, response/confirm never reached this worker


def main() -> None:
    with tempfile.TemporaryDirectory(prefix='outbox demo ') as directory:
        database = str(Path(directory) / 'project.sqlite')
        provider = str(Path(directory) / 'fake-provider.sqlite')
        once, outbox = SQLiteOnce(database), SQLiteOutbox(database)
        once.initialize()
        outbox.initialize()
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.executescript('''
                CREATE TABLE orders(id TEXT PRIMARY KEY, actor INTEGER, state TEXT);
                CREATE TABLE access(actor INTEGER PRIMARY KEY, enabled INTEGER);
                INSERT INTO access VALUES(42,1);
            ''')
        with closing(sqlite3.connect(provider)) as connection, connection:
            connection.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY,intent TEXT,text TEXT)')

        first = place_order(database)
        replay = place_order(database)
        assert not first.replayed and replay.replayed and first.value == replay.value
        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute('SELECT count(*) FROM orders').fetchone()[0] == 1
            assert connection.execute('SELECT count(*) FROM telegram_pattern_outbox').fetchone()[0] == 1

        worker = multiprocessing.get_context('spawn').Process(target=sender_loses_response, args=(database, provider))
        worker.start()
        try:
            worker.join(timeout=15)
            assert worker.exitcode == 84
        finally:
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=5)
            worker.close()

        restarted = SQLiteOutbox(database)
        assert restarted.recover_expired(SCOPE, now=111) == 1
        record = restarted.get(SCOPE, KEY)
        assert record is not None and record.state == 'unknown'
        assert restarted.claim(SCOPE, 'sender-2', now=112) is None
        # This fake provider offers a complete authoritative lookup by intent.
        # Telegram sendMessage has no equivalent generic operation-key lookup;
        # if real evidence is unavailable, leave the intent unknown for review.
        with closing(sqlite3.connect(provider)) as connection:
            rows = connection.execute('SELECT id FROM messages WHERE intent=?', (KEY,)).fetchall()
        assert len(rows) == 1
        result = restarted.reconcile(
            SCOPE,
            KEY,
            expected_revision=record.revision,
            outcome='sent',
            evidence_ref=f'fake-provider:message:{rows[0][0]}',
            result={'message_id': rows[0][0]},
            now=113,
        )
        assert result.state == 'sent' and result.attempts == 1
        assert restarted.claim(SCOPE, 'sender-2', now=1000) is None
        print(
            json.dumps(
                {
                    'business_writes': 1,
                    'intents': 1,
                    'external_messages': len(rows),
                    'business_replay': True,
                    'lost_response_became_unknown': True,
                    'unknown_auto_retry': False,
                    'reconciled_state': result.state,
                },
                sort_keys=True,
            )
        )


if __name__ == '__main__':
    main()
