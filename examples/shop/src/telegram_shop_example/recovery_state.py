"""Closed recovery state shared by HTTP, storage and polling. No activation path."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path


class RecoveryMaintenance(RuntimeError):
    """A restored or unverified recovery database must not serve private data or effects."""

    def __init__(self) -> None:
        super().__init__("Shop recovery requires trusted operator reconciliation")


def assert_operational_connection(db: sqlite3.Connection) -> None:
    # Even a malformed/partial/future marker closes the gate; no state string enables it.
    if db.execute(
        "SELECT 1 FROM sqlite_master WHERE name IN ('shop_recovery_meta','shop_recovery_outgoing') LIMIT 1"
    ).fetchone():
        raise RecoveryMaintenance()


def readiness(database: Path) -> dict:
    try:
        path = database.absolute()
        with closing(
            sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)
        ) as db:
            db.execute("PRAGMA trusted_schema=OFF")
            try:
                assert_operational_connection(db)
            except RecoveryMaintenance:
                return {
                    "ready": False,
                    "mode": "recovery-maintenance",
                    "reason": "operator-reconciliation-required",
                }
            return {"ready": True, "mode": "normal", "reason": "operational"}
    except (OSError, sqlite3.Error, ValueError):
        return {
            "ready": False,
            "mode": "recovery-maintenance",
            "reason": "database-unverified",
        }


def require_operational(database: Path) -> None:
    if not readiness(database)["ready"]:
        raise RecoveryMaintenance()
