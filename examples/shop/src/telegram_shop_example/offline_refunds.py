"""Persistent FAKE Stars service for explicit offline probes, never production transport.

Separate SQLite files make a committed remote effect survive a caller crash.
No network, real Telegram credentials, real payment, or sandbox is involved.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path


class FakeStarsHistory:
    def __init__(self, database: Path):
        self.database = database
        with closing(sqlite3.connect(database)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS fake_charges(charge TEXT PRIMARY KEY,actor INTEGER,amount INTEGER,payload TEXT,paid_at INTEGER,refunded_at INTEGER)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS fake_refund_calls(sequence INTEGER PRIMARY KEY AUTOINCREMENT,actor INTEGER,charge TEXT)"
            )

    def paid(
        self, charge: str, actor: int, amount: int, payload: str, paid_at: int
    ) -> None:
        with closing(sqlite3.connect(self.database)) as db, db:
            old = db.execute(
                "SELECT actor,amount,payload,paid_at FROM fake_charges WHERE charge=?",
                (charge,),
            ).fetchone()
            if old is not None:
                if old != (actor, amount, payload, paid_at):
                    raise AssertionError("Conflicting fake native charge")
                return
            db.execute(
                "INSERT INTO fake_charges VALUES(?,?,?,?,?,NULL)",
                (charge, actor, amount, payload, paid_at),
            )

    def refund(self, actor: int, charge: str, now: int) -> bool:
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(
                "INSERT INTO fake_refund_calls(actor,charge) VALUES(?,?)",
                (actor, charge),
            )
            row = db.execute(
                "SELECT actor,refunded_at FROM fake_charges WHERE charge=?", (charge,)
            ).fetchone()
            # Deliberately NOT idempotent: a repeated send is a test failure, not a provider promise.
            if row is None or row[0] != actor or row[1] is not None:
                db.commit()
                raise AssertionError(
                    "Fake provider rejects a repeated or unrelated refund"
                )
            db.execute(
                "UPDATE fake_charges SET refunded_at=? WHERE charge=?", (now, charge)
            )
        return True

    def history(self, offset: int = 0, limit: int = 100) -> dict:
        with closing(sqlite3.connect(self.database)) as db, db:
            rows = db.execute(
                "SELECT charge,actor,amount,payload,paid_at,refunded_at FROM fake_charges"
            ).fetchall()
        records = []
        for charge, actor, amount, payload, paid_at, refunded_at in rows:
            partner = {
                "type": "user",
                "transaction_type": "invoice_payment",
                "user": {"id": actor, "is_bot": False, "first_name": "Fixture"},
                "invoice_payload": payload,
            }
            records.append(
                {"id": charge, "amount": amount, "date": paid_at, "source": partner}
            )
            if refunded_at is not None:
                records.append(
                    {
                        "id": charge,
                        "amount": amount,
                        "date": refunded_at,
                        "receiver": partner,
                    }
                )
        records.sort(key=lambda row: row["date"])
        return {"transactions": records[offset : offset + limit]}

    def calls(self) -> int:
        with closing(sqlite3.connect(self.database)) as db, db:
            return db.execute("SELECT count(*) FROM fake_refund_calls").fetchone()[0]
