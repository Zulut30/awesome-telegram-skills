"""Atomic SQLite-local effect and replay result, across process restarts."""
from __future__ import annotations
from .errors import ConflictFailure
from .errors import ValidationFailure

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Callable, Any


class OperationConflict(ConflictFailure):
    """The scoped operation key was already used for a different payload."""


@dataclass(frozen=True)
class OnceResult:
    value: Any
    replayed: bool


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


_MAX_PAYLOAD_DEPTH = 64


def _check_payload(value: Any, depth: int = 0) -> None:
    """Only JSON values hash unambiguously: {1: 'a'} vs {'1': 'a'} or tuple vs list would collide."""
    if depth > _MAX_PAYLOAD_DEPTH:
        raise ValidationFailure("Operation payload is nested too deeply")
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationFailure("Operation payload numbers must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _check_payload(item, depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValidationFailure("Operation payload keys must be strings")
            _check_payload(item, depth + 1)
        return
    raise ValidationFailure("Operation payload must contain only dict with str keys, list, str, int, float, bool or None")


def _payload_digest(payload: Any) -> str:
    _check_payload(payload)
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _owned_transaction(action: int, *_arguments: Any) -> int:
    # Includes Python commit/rollback, SQL transaction commands and the
    # implicit COMMIT performed by executescript. Savepoints remain local.
    return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION else sqlite3.SQLITE_OK


class SQLiteOnce:
    """Use only with synchronous effects on the supplied SQLite connection.

    Scope must be server-derived and authorization checked before run().
    External network calls, COMMIT/ROLLBACK and other databases are not covered.
    Call through an appropriate thread boundary from an async application.
    """
    def __init__(self, database: str | Path, *, timeout: float = 5.0):
        if (not str(database) or str(database) == ":memory:" or type(timeout) not in (int, float)
                or not math.isfinite(timeout) or timeout <= 0):
            raise ValidationFailure("Use a file database and a positive finite timeout")
        self.database = str(database)
        self.timeout = timeout

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database, timeout=self.timeout, isolation_level=None)

    def initialize(self) -> None:
        """Explicit schema setup; existing projects may use their own migration."""
        connection = self._connect()
        try:
            connection.execute("""CREATE TABLE IF NOT EXISTS telegram_pattern_operations (
                scope TEXT NOT NULL, operation_key TEXT NOT NULL,
                payload_hash TEXT NOT NULL, result_json TEXT NOT NULL,
                PRIMARY KEY (scope, operation_key)
            )""")
        finally:
            connection.close()

    def run(self, scope: str, operation_key: str, payload: Any,
            apply: Callable[[sqlite3.Connection], Any]) -> OnceResult:
        for value in (scope, operation_key):
            if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
                raise ValidationFailure("Scope and operation key must be nonempty bounded strings")
        digest = _payload_digest(payload)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute(
                "SELECT payload_hash, result_json FROM telegram_pattern_operations WHERE scope=? AND operation_key=?",
                (scope, operation_key),
            ).fetchone()
            if old is not None:
                if old[0] != digest:
                    raise OperationConflict("Operation payload changed")
                value = json.loads(old[1])
                replayed = True
            else:
                # Block accidental transaction control BEFORE an effect escapes.
                # This is a trusted callback contract, not isolation of Python code.
                connection.set_authorizer(_owned_transaction)
                try:
                    value = apply(connection)
                finally:
                    connection.set_authorizer(None)
                if not connection.in_transaction:
                    raise RuntimeError("apply must not commit or roll back the transaction")
                serialized = _json(value)
                connection.execute(
                    "INSERT INTO telegram_pattern_operations VALUES (?, ?, ?, ?)",
                    (scope, operation_key, digest, serialized),
                )
                value = json.loads(serialized)
                replayed = False
            connection.commit()
            return OnceResult(value=value, replayed=replayed)
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
