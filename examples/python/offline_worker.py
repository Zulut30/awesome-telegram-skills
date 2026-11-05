"""SDK-free durable worker, stop/drain/resource close and safe local telemetry."""

from __future__ import annotations

import asyncio
import json
import secrets
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

from telegram_patterns import SQLiteOnce, UnsupportedCapability
from telegram_patterns.inbox import InboxClaim, SQLiteInbox
from telegram_patterns.outbox import SQLiteOutbox
from telegram_patterns.telemetry import Telemetry
from telegram_patterns.webhook import WebhookReceiver
from telegram_patterns.worker import InboxWorker, settled_to_thread

CANARY = 'PRIVATE_MESSAGE_CANARY'


class LocalSession:
    """Local resource stand-in, no network; observes the durable state at close."""

    def __init__(self, inbox: SQLiteInbox):
        self.inbox = inbox
        self.closed = False
        self.states_at_close: dict[str, int] = {}

    async def close(self) -> None:
        self.states_at_close = await settled_to_thread(self.inbox.counts, 100)
        self.closed = True


def decode(payload: dict[str, Any]) -> dict[str, Any]:
    # A real SDK decoder must also reject unsupported/ambiguous semantic kinds;
    # accepting an empty SDK Update after dropping unknown fields loses events.
    if set(payload) != {'update_id', 'message'} or not isinstance(payload['message'].get('text'), str):
        raise UnsupportedCapability('Unsupported fixture Update')
    return payload['message']


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix='worker demo ') as directory:
        database = Path(directory) / 'project.sqlite'
        inbox, once, outbox = SQLiteInbox(database), SQLiteOnce(database), SQLiteOutbox(database)
        inbox.initialize()
        once.initialize()
        outbox.initialize()
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute('CREATE TABLE orders(id INTEGER PRIMARY KEY,actor INTEGER)')
            connection.execute('CREATE TABLE access(actor INTEGER PRIMARY KEY,allowed INTEGER)')
            connection.execute('INSERT INTO access VALUES(42,1)')
        inbox.receive(100, 0, {'update_id': 0, 'message': {'unsupported': CANARY}})
        for identity in (1, 2):
            inbox.receive(100, identity, {'update_id': identity, 'message': {'text': CANARY}})
        receiver = WebhookReceiver(inbox, bot_id=100, secret_token='fixture-secret')
        response = receiver.receive(
            b'{"update_id":3,"future_event":{"value":"PRIVATE_MESSAGE_CANARY"}}', 'fixture-secret'
        )
        assert response.status == 200

        lines: list[str] = []
        # Production uses a dedicated host-managed key shared across its workers.
        telemetry = Telemetry(secrets.token_bytes(32), lines.append)
        started, release, stop = asyncio.Event(), asyncio.Event(), asyncio.Event()
        session = LocalSession(inbox)

        async def handle(message: dict[str, Any], claim: InboxClaim) -> bool:
            assert not session.closed
            started.set()
            await release.wait()

            def check(connection: sqlite3.Connection, replayed: bool) -> bool:
                # Fixture actor42 stands for the verified adapter identity.
                return connection.execute('SELECT allowed FROM access WHERE actor=42').fetchone() == (1,)

            def apply(connection: sqlite3.Connection) -> dict[str, int]:
                connection.execute('INSERT INTO orders VALUES(?,42)', (claim.update_id,))
                outbox.enqueue(
                    connection,
                    'bot:100:orders',
                    str(claim.update_id),
                    {'method': 'sendMessage', 'chat_id': 42, 'text': 'Order accepted'},
                )
                return {'order_id': claim.update_id}

            with telemetry.bind(bot_id=100, action_id='confirm-order', operation_id=claim.update_id, inherit=True):
                result = await settled_to_thread(
                    once.run_guarded,
                    'bot:100:actor:42:order',
                    str(claim.update_id),
                    {'product_id': 7},
                    apply,
                    check=check,
                )
                telemetry.emit('operation', 'replayed' if result.replayed else 'succeeded', attempt=claim.attempt)
            return True

        worker = InboxWorker(inbox, 100, 'local-worker', decode, handle, telemetry=telemetry)

        async def owner() -> None:
            try:
                assert await worker.run_one() == 'quarantined'  # decode failure retained
                await worker.serve(stop)
            finally:
                await session.close()

        task = asyncio.create_task(owner())
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            stop.set()  # no new claims; the in-flight job drains
            release.set()
            await asyncio.wait_for(task, timeout=5)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        assert session.closed
        assert session.states_at_close == {'pending': 1, 'processing': 0, 'done': 1, 'quarantined': 2}
        assert inbox.get(100, 0).payload['message']['unsupported'] == CANARY
        assert inbox.get(100, 3).reason == 'unknown-update-kind'
        assert outbox.get('bot:100:orders', '1').state == 'pending'
        serialized = '\n'.join(lines)
        assert CANARY not in serialized
        events = [json.loads(line) for line in lines]
        operation = next(event for event in events if event['stage'] == 'operation')
        job = next(event for event in events if event['stage'] == 'job' and event['outcome'] == 'succeeded')
        assert operation['context']['trace_id'] == job['context']['trace_id']
        assert operation['context']['update_ref'] == job['context']['update_ref']
        print(
            json.dumps(
                {
                    'states_at_session_close': session.states_at_close,
                    'business_and_outbox_committed': True,
                    'unknown_raw_payload_preserved': True,
                    'session_closed_after_drain': True,
                    'operation_job_correlated': True,
                    'secret_canary_absent_from_serialized_sink': True,
                    'metric_series': len(telemetry.snapshot().metrics),
                },
                sort_keys=True,
            )
        )


if __name__ == '__main__':
    asyncio.run(main())
