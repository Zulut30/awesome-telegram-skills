"""Atomic SQLite-local effect and replay result, across process restarts."""

from __future__ import annotations

import inspect
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ._shared import canonical_json, owned_transaction, payload_digest
from .errors import ConflictFailure, InvalidType, PermissionDenied, ValidationFailure


def _sync_callback(callback: Any, name: str) -> None:
    if not callable(callback) or any(
        predicate(candidate)
        for predicate in (inspect.iscoroutinefunction, inspect.isasyncgenfunction)
        for candidate in (callback, getattr(callback, '__call__', None))
    ):
        raise InvalidType(f'Supply a synchronous {name} callback')


def _sync_result(value: Any, name: str) -> None:
    if inspect.isawaitable(value) or inspect.isasyncgen(value):
        if inspect.iscoroutine(value):
            value.close()
        raise InvalidType(f'{name} must return synchronously')


def _read_only_check(action: int, *_arguments: Any) -> int:
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


class OperationConflict(ConflictFailure):
    """The scoped operation key was already used for a different payload."""


@dataclass(frozen=True)
class OnceResult:
    value: Any
    replayed: bool


class SQLiteOnce:
    """Use only with synchronous effects on the supplied SQLite connection.

    Scope must be server-derived and authorization checked before run(). Use
    run_guarded() to check current access inside the owned writer transaction.
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
        return self._run(scope, operation_key, payload, apply, check=None)

    def run_guarded(
        self,
        scope: str,
        operation_key: str,
        payload: Any,
        apply: Callable[[sqlite3.Connection], Any],
        *,
        check: Callable[[sqlite3.Connection, bool], bool],
    ) -> OnceResult:
        """Check current access and commit a local effect in one writer transaction.

        check(connection, replayed) must return exactly True. It runs before a
        new effect and before returning a saved receipt. SQL in this check is
        read-only. Validate current actor/origin/ACL on both paths; validate the
        expected domain revision for a NEW effect, since its own committed
        effect may already have advanced the revision before replay.

        Both callbacks are trusted synchronous host code, not a sandbox. Only
        effects in this SQLite transaction are covered, never external I/O.
        """
        _sync_callback(check, 'check')
        _sync_callback(apply, 'apply')
        return self._run(scope, operation_key, payload, apply, check=check)

    def _run(
        self,
        scope: str,
        operation_key: str,
        payload: Any,
        apply: Callable[[sqlite3.Connection], Any],
        *,
        check: Callable[[sqlite3.Connection, bool], bool] | None,
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
            if check is not None:
                connection.set_authorizer(_read_only_check)
                try:
                    decision = check(connection, old is not None)
                    _sync_result(decision, 'check')
                    if decision is not True:
                        raise PermissionDenied('Current operation access denied')
                finally:
                    connection.set_authorizer(None)
                if not connection.in_transaction:
                    raise RuntimeError('check must preserve the owned transaction')
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
                    if check is not None:
                        _sync_result(value, 'apply')
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
