"""Atomic SQLite-local effect and replay result, across process restarts."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ._shared import canonical_json, owned_transaction, payload_digest
from .errors import ConflictFailure, ValidationFailure


class OperationConflict(ConflictFailure):
    """The scoped operation key was already used for a different payload."""


@dataclass(frozen=True)
class OnceResult:
    value: Any
    replayed: bool


class SQLiteOnce:
    """Use only with synchronous effects on the supplied SQLite connection.

    Scope must be server-derived and authorization checked before run().
    External network calls, COMMIT/ROLLBACK and other databases are not covered.
    Call through an appropriate thread boundary from an async application.
    """

    def __init__(self, database: str | Path, *, timeout: float = 5.0):
        if (
            not str(database)
            or str(database) == ":memory:"
            or type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
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

    def run(
        self, scope: str, operation_key: str, payload: Any, apply: Callable[[sqlite3.Connection], Any]
    ) -> OnceResult:
        for value in (scope, operation_key):
            if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
                raise ValidationFailure("Scope and operation key must be nonempty bounded strings")
        digest = payload_digest(payload)
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
                connection.set_authorizer(owned_transaction)
                try:
                    value = apply(connection)
                finally:
                    connection.set_authorizer(None)
                if not connection.in_transaction:
                    raise RuntimeError("apply must not commit or roll back the transaction")
                serialized = canonical_json(value)
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
