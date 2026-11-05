"""Offline durable receipt, lease recovery and host-owned idempotent business effect."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from telegram_patterns.inbox import InboxLeaseLost, SQLiteInbox
from telegram_patterns.sqlite_once import SQLiteOnce


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="telegram-inbox-demo-") as temporary:
        database = Path(temporary) / "inbox.sqlite"
        inbox = SQLiteInbox(database, max_attempts=3)
        inbox.initialize()
        once = SQLiteOnce(database)
        once.initialize()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("CREATE TABLE demo_counter(value INTEGER NOT NULL)")
            db.execute("INSERT INTO demo_counter VALUES (0)")

        payload = {"update_id": 1, "message": {"text": "offline fixture"}}
        receipt = inbox.receive(100, 1, payload, now=100)
        duplicate = inbox.receive(100, 1, payload, now=101)
        first = inbox.claim(100, "worker-before-restart", lease_seconds=10, now=100)
        if first is None:
            raise RuntimeError("Expected an admitted receipt")

        def effect(db: sqlite3.Connection) -> dict[str, bool]:
            db.execute("UPDATE demo_counter SET value=value+1")
            return {"applied": True}

        # Business mutation and its idempotency result share SQLiteOnce's transaction.
        once.run("bot:100", "update:1", first.payload, effect)
        # Model a crash after that transaction commits, before complete(first).
        restarted = SQLiteInbox(database)
        recovered = restarted.claim(
            100, "worker-after-restart", lease_seconds=10, now=110
        )
        if recovered is None:
            raise RuntimeError("Expected recovery after the expired lease")
        replay = once.run("bot:100", "update:1", recovered.payload, effect)
        restarted.complete(recovered, now=111)
        stale_rejected = False
        try:
            inbox.complete(first, now=111)
        except InboxLeaseLost:
            stale_rejected = True

        quarantine = restarted.receive(
            100,
            2,
            {"update_id": 2, "future_kind": {}},
            quarantine_reason="unknown-update-kind",
            now=112,
        )
        with closing(sqlite3.connect(database)) as db:
            value = db.execute("SELECT value FROM demo_counter").fetchone()[0]
        print(
            json.dumps(
                {
                    "receipt_state": receipt.state,
                    "duplicate": duplicate.duplicate,
                    "recovered_attempt": recovered.attempt,
                    "business_replayed": replay.replayed,
                    "business_counter": value,
                    "stale_claim_rejected": stale_rejected,
                    "quarantine_reason": quarantine.reason,
                    "counts": restarted.counts(100),
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
