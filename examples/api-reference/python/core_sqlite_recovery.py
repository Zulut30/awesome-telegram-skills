"""Real WAL snapshot and restore retain a public outbox's unknown operation; no service is started."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from telegram_patterns import (
    SQLiteOutbox,
    SQLiteRecoveryError,
    SQLiteRecoveryResult,
    backup_sqlite,
    restore_sqlite_new,
)

with TemporaryDirectory() as directory:
    root = Path(directory)
    root.chmod(0o700)
    data, snapshots, restored = (root / name for name in ("data", "snapshots", "restored"))
    for folder in (data, snapshots, restored):
        folder.mkdir(mode=0o700)
    live = data / "live.sqlite"
    operation_id = "send:unknown-one"
    with closing(sqlite3.connect(live)) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        outbox = SQLiteOutbox(live)
        outbox.initialize()
        writer.execute("CREATE TABLE fixture_orders(id TEXT PRIMARY KEY)")
        with writer:
            writer.execute("INSERT INTO fixture_orders VALUES (?)", (operation_id,))
            outbox.enqueue(writer, "bot:100", operation_id, {"operation_id": operation_id}, now=10)
        claimed = outbox.claim("bot:100", "original-worker", lease_seconds=1, now=10)
        assert claimed is not None
        assert outbox.recover_expired("bot:100", now=11) == 1
        original = outbox.get("bot:100", operation_id)
        assert original is not None and original.state == "unknown"
        with writer:
            writer.execute("CREATE TABLE fixture_committed(id INTEGER PRIMARY KEY)")
            writer.execute("INSERT INTO fixture_committed VALUES (77)")
        assert Path(str(live) + "-wal").is_file()
        snapshot = snapshots / "snapshot.sqlite"
        backup: SQLiteRecoveryResult = backup_sqlite(
            live, snapshot, source_root=data, destination_root=snapshots, deadline_seconds=10
        )
        assert backup.operation == "backup" and backup.bytes == snapshot.stat().st_size
        assert backup.sha256 == hashlib.sha256(snapshot.read_bytes()).hexdigest()
        assert backup.pages > 0 and str(snapshot) not in repr(backup)
        before = snapshot.read_bytes()
        try:
            backup_sqlite(live, snapshot, source_root=data, destination_root=snapshots)
        except SQLiteRecoveryError as error:
            assert error.code == "destination-exists" and str(snapshot) not in str(error)
        else:
            raise AssertionError("An existing snapshot was overwritten")
        assert snapshot.read_bytes() == before
        new_database = restored / "recovered.sqlite"
        recovery = restore_sqlite_new(
            snapshot, new_database, source_root=snapshots, destination_root=restored, deadline_seconds=10
        )
        assert isinstance(recovery, SQLiteRecoveryResult) and recovery.operation == "restore-new"
        recovered_outbox = SQLiteOutbox(new_database)
        recovered_outbox.initialize()
        observed = recovered_outbox.get("bot:100", operation_id)
        assert observed is not None and observed.state == "unknown"
        assert observed.operation_key == original.operation_key == operation_id
        assert observed.revision == original.revision
        assert observed.payload == original.payload
        assert recovered_outbox.claim("bot:100", "replacement-worker", now=12) is None
        with closing(sqlite3.connect(new_database)) as check:
            assert check.execute("SELECT id FROM fixture_committed").fetchall() == [(77,)]
        assert outbox.get("bot:100", operation_id) == original

print(json.dumps({"passed": True, "case": "core_sqlite_recovery", "network": False,
                  "unknown_preserved": True, "automatic_resends": 0}))
