"""Offline transaction example; a real service derives scope after authorization."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import sqlite3
from pathlib import Path
from telegram_patterns import SQLiteOnce


def book(database: Path, key: str):
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY, actor_id INTEGER NOT NULL, slot TEXT NOT NULL UNIQUE)")
    once = SQLiteOnce(database)
    once.initialize()

    def apply(db: sqlite3.Connection):
        booking_id = db.execute("INSERT INTO bookings(actor_id,slot) VALUES (?,?)", (42, "slot-demo")).lastrowid
        return {"booking_id": booking_id, "slot": "slot-demo"}

    # Fixed actor 42 is a local fixture, never a substitute for verified identity.
    return once.run("demo:user:42:booking", key, {"slot": "slot-demo"}, apply)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--key", default="example-operation")
    args = parser.parse_args()
    result = book(args.database, args.key)
    print(json.dumps({"result": result.value, "replayed": result.replayed}, ensure_ascii=False))
