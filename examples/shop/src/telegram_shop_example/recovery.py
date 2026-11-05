"""Offline restored-shop preparation and read-only inspection; activation is deliberately absent."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import sys
import tempfile
import time
from contextlib import ExitStack, closing
from pathlib import Path
from typing import NoReturn

from telegram_patterns import SQLiteRecoveryError, backup_sqlite, restore_sqlite_new

from .recovery_state import readiness
from .storage import ProcessLock


class RecoveryPrepareError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__("Shop recovery refused: " + code)


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RecoveryPrepareError("deadline-exceeded")
    return min(remaining, 300)


def _sha(path: Path, deadline: float) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(65536):
            _remaining(deadline)
            digest.update(chunk)
    return digest.hexdigest()


def _bounded_path(path: Path, root: Path, *, missing: bool = False) -> Path:
    for value in (path, root):
        if ".." in value.parts or any(ord(char) < 32 for char in str(value)):
            raise RecoveryPrepareError("unsafe-path")
        if os.name == "nt":
            devices = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
            devices |= {
                prefix + number
                for prefix in ("COM", "LPT")
                for number in "123456789¹²³"
            }
            if str(value).startswith(("\\\\", "//")):
                raise RecoveryPrepareError("unsafe-path")
            for part in value.parts[1:] if value.anchor else value.parts:
                if (
                    ":" in part
                    or part.endswith((" ", "."))
                    or part.split(".")[0].upper() in devices
                ):
                    raise RecoveryPrepareError("unsafe-path")
    root = root.absolute()
    path = (path if path.is_absolute() else root / path).absolute()
    if not root.is_dir() or not path.is_relative_to(root) or path == root:
        raise RecoveryPrepareError("outside-owned-root")
    for path_component in (*reversed(path.parents), path):
        try:
            info = path_component.lstat()
        except FileNotFoundError:
            if path_component == path and missing:
                continue
            raise RecoveryPrepareError("path-unavailable") from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RecoveryPrepareError("linked-path")
    if not missing and not path.is_file():
        raise RecoveryPrepareError("path-unavailable")
    return path


def _owner(path: Path, owners: ExitStack, code: str) -> None:
    try:
        lock = ProcessLock(path)
    except (OSError, ValueError, RuntimeError):
        raise RecoveryPrepareError(code) from None
    owners.callback(lock.close)


def _schema(db: sqlite3.Connection) -> bool:
    if [row[0] for row in db.execute("SELECT version FROM shop_schema")] != [3]:
        raise RecoveryPrepareError("unsupported-shop-schema")
    found = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE name IN ('telegram_pattern_outbox_meta','telegram_pattern_outbox')"
        )
    }
    if found and found != {"telegram_pattern_outbox_meta", "telegram_pattern_outbox"}:
        raise RecoveryPrepareError("unsupported-outbox-schema")
    if found and [
        row[0]
        for row in db.execute("SELECT schema_version FROM telegram_pattern_outbox_meta")
    ] != [1]:
        raise RecoveryPrepareError("unsupported-outbox-schema")
    expected = {
        "shop_sessions": {"token_hash", "bot_id", "actor_id", "csrf_hash", "expires"},
        "shop_roles": {"bot_id", "actor_id", "role"},
        "shop_operators": {"bot_id", "actor_id", "enabled"},
        "telegram_pattern_outbox": {
            "scope",
            "operation_key",
            "payload_json",
            "payload_hash",
            "state",
            "attempts",
            "max_attempts",
            "revision",
            "created_at",
            "available_at",
            "worker_id",
            "claim_token",
            "lease_until",
            "result_json",
            "evidence_ref",
            "reason",
        },
    }
    for table, columns in expected.items():
        if table == "telegram_pattern_outbox" and not found:
            continue
        if {
            row["name"] for row in db.execute("PRAGMA table_info(" + table + ")")
        } != columns:
            raise RecoveryPrepareError("unsupported-host-schema")
    return bool(found)


def _actors(db: sqlite3.Connection, bot_id: int) -> list[int]:
    actors = set()
    for table in (
        "shop_sessions",
        "shop_roles",
        "shop_operators",
        "shop_orders",
        "shop_access",
        "shop_receipts",
        "shop_payment_links",
        "shop_refund_intents",
        "shop_operator_audit",
    ):
        for row in db.execute("SELECT DISTINCT bot_id,actor_id FROM " + table):
            if (
                row["bot_id"] != bot_id
                or type(row["actor_id"]) is not int
                or row["actor_id"] <= 0
            ):
                raise RecoveryPrepareError("wrong-host-context")
            actors.add(row["actor_id"])
            if len(actors) > 10_000:
                raise RecoveryPrepareError("inventory-limit")
    return sorted(actors)


def _quarantine(
    staged: Path,
    *,
    bot_id: int,
    checkpoint_sha: str,
    restored_sha: str,
    deadline: float,
) -> dict:
    barrier_id = hashlib.sha256(
        ("shop-recovery-v1:" + str(bot_id) + ":" + checkpoint_sha).encode()
    ).hexdigest()
    with closing(sqlite3.connect(staged, timeout=1, isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA trusted_schema=OFF")
        db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 500)
        try:
            db.execute("BEGIN IMMEDIATE")
            has_outbox = _schema(db)
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE name IN ('shop_recovery_meta','shop_recovery_outgoing')"
            ).fetchone():
                raise RecoveryPrepareError("checkpoint-already-quarantined")
            actors = _actors(db, bot_id)
            if (
                has_outbox
                and db.execute(
                    "SELECT count(*) FROM telegram_pattern_outbox"
                ).fetchone()[0]
                > 10_000
            ):
                raise RecoveryPrepareError("inventory-limit")
            outgoing = (
                db.execute(
                    "SELECT * FROM telegram_pattern_outbox WHERE state IN ('pending','sending') ORDER BY scope,operation_key"
                ).fetchall()
                if has_outbox
                else []
            )
            sessions = db.execute("SELECT count(*) FROM shop_sessions").fetchone()[0]
            db.execute("""CREATE TABLE shop_recovery_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                schema_version INTEGER NOT NULL CHECK(schema_version=1),barrier_id TEXT NOT NULL,bot_id INTEGER NOT NULL,
                checkpoint_sha TEXT NOT NULL,restored_sha TEXT NOT NULL,state TEXT NOT NULL CHECK(state='quarantined'),
                revoked_sessions INTEGER NOT NULL,blocked_actors INTEGER NOT NULL,quarantined_outgoing INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE shop_recovery_outgoing(scope TEXT NOT NULL,operation_key TEXT NOT NULL,
                before_state TEXT NOT NULL,before_revision INTEGER NOT NULL,after_revision INTEGER NOT NULL,
                attempts INTEGER NOT NULL,payload_hash TEXT NOT NULL,PRIMARY KEY(scope,operation_key))""")
            db.execute(
                "INSERT INTO shop_recovery_meta VALUES(1,1,?,?,?,?,?,?,?,?)",
                (
                    barrier_id,
                    bot_id,
                    checkpoint_sha,
                    restored_sha,
                    "quarantined",
                    sessions,
                    len(actors),
                    len(outgoing),
                ),
            )
            db.execute("DELETE FROM shop_sessions")
            db.execute("UPDATE shop_operators SET enabled=0")
            for actor in actors:
                db.execute(
                    "INSERT INTO shop_roles VALUES(?,?,'blocked') ON CONFLICT(bot_id,actor_id) DO UPDATE SET role='blocked'",
                    (bot_id, actor),
                )
            for row in outgoing:
                db.execute(
                    "INSERT INTO shop_recovery_outgoing VALUES(?,?,?,?,?,?,?)",
                    (
                        row["scope"],
                        row["operation_key"],
                        row["state"],
                        row["revision"],
                        row["revision"] + 1,
                        row["attempts"],
                        row["payload_hash"],
                    ),
                )
                db.execute(
                    """UPDATE telegram_pattern_outbox SET state='unknown',reason='restored-checkpoint',
                    revision=revision+1,worker_id=NULL,claim_token=NULL,lease_until=NULL
                    WHERE scope=? AND operation_key=? AND revision=? AND state=?""",
                    (row["scope"], row["operation_key"], row["revision"], row["state"]),
                )
            if (
                db.execute("PRAGMA integrity_check(1)").fetchall()[0][0] != "ok"
                or db.execute("PRAGMA foreign_key_check").fetchone() is not None
            ):
                raise RecoveryPrepareError("invalid-candidate")
            _remaining(deadline)
            db.commit()
            return {
                "barrier_id": barrier_id,
                "revoked_sessions": sessions,
                "blocked_actors": len(actors),
                "quarantined_outgoing": len(outgoing),
            }
        except BaseException:
            db.rollback()
            raise
        finally:
            db.set_progress_handler(None, 0)


def _publish_guarded(
    staged: Path, candidate: Path, *, stage: Path, target_root: Path, deadline: float
):
    return backup_sqlite(
        staged,
        candidate,
        source_root=stage,
        destination_root=target_root,
        deadline_seconds=_remaining(deadline),
    )


def _cleanup_stage(
    stage: Path, owned: dict[str, tuple[int, int]], identity: tuple[int, int]
) -> bool:
    try:
        if stage.is_symlink() or bool(getattr(stage, "is_junction", lambda: False)()):
            return False
        info = stage.stat()
        if (info.st_dev, info.st_ino) != identity:
            return False
        for name, file_identity in owned.items():
            file = stage / name
            info = file.lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or (info.st_dev, info.st_ino) != file_identity
            ):
                return False
            file.unlink()
        stage.rmdir()  # Keep unknown caller entries; never recursively delete a stage.
        return True
    except OSError:
        return False


def prepare_restored_shop(
    live: Path,
    snapshot: Path,
    candidate: Path,
    *,
    live_root: Path,
    snapshot_root: Path,
    target_root: Path,
    bot_id: int,
    expected_snapshot_sha256: str,
    deadline_seconds: float = 30,
) -> dict:
    """Only a NEW candidate: restore privately, close sessions/effects, then exclusively publish guarded bytes."""
    if (
        type(bot_id) is not int
        or bot_id <= 0
        or type(deadline_seconds) not in (int, float)
        or not 0 < deadline_seconds <= 300
    ):
        raise RecoveryPrepareError("invalid-arguments")
    if len(expected_snapshot_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in expected_snapshot_sha256
    ):
        raise RecoveryPrepareError("invalid-checkpoint-digest")
    deadline = time.monotonic() + deadline_seconds
    stage = None
    stage_identity = (0, 0)
    owned = {}
    cleanup = True
    published = False
    try:
        live = _bounded_path(live, live_root)
        snapshot = _bounded_path(snapshot, snapshot_root)
        candidate = _bounded_path(candidate, target_root, missing=True)
        if candidate.exists():
            raise RecoveryPrepareError("candidate-exists")
        if candidate == live or snapshot.samefile(live):
            raise RecoveryPrepareError("source-target-conflict")
        with ExitStack() as owners:
            _owner(live, owners, "old-writer-active")
            _owner(candidate, owners, "candidate-writer-active")
            old_sha = _sha(live, deadline)
            checkpoint_sha = _sha(snapshot, deadline)
            if checkpoint_sha != expected_snapshot_sha256:
                raise RecoveryPrepareError("checkpoint-digest-mismatch")
            stage = Path(tempfile.mkdtemp(prefix=".shop-recovery-", dir=target_root))
            info = stage.stat()
            stage_identity = (info.st_dev, info.st_ino)
            staged = stage / "prepared.sqlite"
            restored = restore_sqlite_new(
                snapshot,
                staged,
                source_root=snapshot_root,
                destination_root=stage,
                deadline_seconds=_remaining(deadline),
            )
            info = staged.stat()
            owned[staged.name] = (info.st_dev, info.st_ino)
            _owner(staged, owners, "stage-writer-active")
            lock = staged.with_name(staged.name + ".lock")
            info = lock.stat()
            owned[lock.name] = (info.st_dev, info.st_ino)
            prepared = _quarantine(
                staged,
                bot_id=bot_id,
                checkpoint_sha=checkpoint_sha,
                restored_sha=restored.sha256,
                deadline=deadline,
            )
            if _sha(snapshot, deadline) != checkpoint_sha:
                raise RecoveryPrepareError("checkpoint-drift")
            final = _publish_guarded(
                staged,
                candidate,
                stage=stage,
                target_root=target_root,
                deadline=deadline,
            )
            published = True
            if readiness(candidate)["ready"] or _sha(live, deadline) != old_sha:
                raise RecoveryPrepareError("publication-unknown")
            result = {
                "passed": True,
                "ready": False,
                "mode": "recovery-maintenance",
                **prepared,
                "checkpoint_sha256": checkpoint_sha,
                "candidate_sha256": final.sha256,
                "old_source_unchanged": True,
                "directory_synced": final.directory_synced,
                "core_cleanup_complete": restored.cleanup_complete
                and final.cleanup_complete,
            }
    except RecoveryPrepareError:
        raise
    except SQLiteRecoveryError as error:
        raise RecoveryPrepareError(
            "publication-unknown"
            if published or error.code == "publication-unknown"
            else error.code
        ) from None
    except (OSError, sqlite3.Error, ValueError, TypeError):
        raise RecoveryPrepareError(
            "publication-unknown" if published else "preparation-failed"
        ) from None
    finally:
        if stage is not None:
            cleanup = _cleanup_stage(stage, owned, stage_identity)
    result["cleanup_complete"] = cleanup and result.pop("core_cleanup_complete")
    return result


def inspect_restored_shop(candidate: Path, *, target_root: Path) -> dict:
    candidate = _bounded_path(candidate, target_root)
    status = readiness(candidate)
    result = {"passed": True, **status, "prepared": False}
    try:
        with closing(
            sqlite3.connect(candidate.as_uri() + "?mode=ro", uri=True, timeout=1)
        ) as db:
            db.row_factory = sqlite3.Row
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='shop_recovery_meta'"
            ).fetchone():
                row = db.execute(
                    "SELECT * FROM shop_recovery_meta WHERE singleton=1"
                ).fetchone()
                if row and row["schema_version"] == 1 and row["state"] == "quarantined":
                    result.update(
                        prepared=True,
                        barrier_id=row["barrier_id"],
                        checkpoint_sha256=row["checkpoint_sha"],
                        revoked_sessions=row["revoked_sessions"],
                        blocked_actors=row["blocked_actors"],
                        quarantined_outgoing=row["quarantined_outgoing"],
                    )
    except (sqlite3.Error, IndexError, KeyError, TypeError):
        result.update(
            ready=False, mode="recovery-maintenance", reason="recovery-state-unverified"
        )
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise RecoveryPrepareError("invalid-arguments")


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser(description=__doc__)
        commands = parser.add_subparsers(dest="command", required=True)
        prepare = commands.add_parser(
            "prepare", help="Restore only to a NEW quarantined shop candidate"
        )
        for name in (
            "live",
            "snapshot",
            "candidate",
            "live-root",
            "snapshot-root",
            "target-root",
        ):
            prepare.add_argument("--" + name, type=Path, required=True)
        prepare.add_argument("--bot-id", type=int, required=True)
        prepare.add_argument("--expected-snapshot-sha256", required=True)
        prepare.add_argument("--deadline-seconds", type=float, default=30)
        inspect = commands.add_parser(
            "inspect", help="Read-only status; no activation command exists"
        )
        inspect.add_argument("--candidate", type=Path, required=True)
        inspect.add_argument("--target-root", type=Path, required=True)
        args = parser.parse_args(argv)
        if args.command == "prepare":
            result = prepare_restored_shop(
                args.live,
                args.snapshot,
                args.candidate,
                live_root=args.live_root,
                snapshot_root=args.snapshot_root,
                target_root=args.target_root,
                bot_id=args.bot_id,
                expected_snapshot_sha256=args.expected_snapshot_sha256,
                deadline_seconds=args.deadline_seconds,
            )
        else:
            result = inspect_restored_shop(args.candidate, target_root=args.target_root)
        print(json.dumps(result))
        return 0 if args.command == "prepare" or result["ready"] else 3
    except RecoveryPrepareError as error:
        print(json.dumps({"passed": False, "code": error.code}), file=sys.stderr)
        return 4 if error.code == "publication-unknown" else 2
    except Exception:  # noqa: BLE001 -- fixed operator diagnostics never echo paths or parser values
        print(
            json.dumps({"passed": False, "code": "preparation-failed"}), file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
