"""Atomic SQLite-local effect and replay result, across process restarts."""
from __future__ import annotations
from .errors import ConflictFailure
from .errors import InvalidType, PermissionDenied, ValidationFailure

from dataclasses import dataclass
import hashlib
import inspect
import json
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


def _owned_transaction(action: int, *_arguments: Any) -> int:
    # Includes Python commit/rollback, SQL transaction commands and the
    # implicit COMMIT performed by executescript. Savepoints remain local.
    return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION else sqlite3.SQLITE_OK


class SQLiteOnce:
    """Use only with synchronous effects on the supplied SQLite connection.

    Scope must be server-derived and authorization checked before run().
    run_guarded additionally puts current host checks inside its transaction,
    including before replay; host checks bind actor/origin and domain revision.
    External network calls, COMMIT/ROLLBACK and other databases are not covered.
    Call through an appropriate thread boundary from an async application.
    """
    def __init__(self, database: str | Path, *, timeout: float = 5.0):
        if not str(database) or str(database) == ":memory:" or timeout <= 0:
            raise ValidationFailure("Use a file database and a positive timeout")
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
        return self._run(scope, operation_key, payload, apply, check=None)

    def run_guarded(self, scope: str, operation_key: str, payload: Any,
                    apply: Callable[[sqlite3.Connection], Any], *,
                    check: Callable[[sqlite3.Connection, bool], bool]) -> OnceResult:
        """Current host checks and effect/receipt share one owned transaction.

        check(connection, replayed) must be synchronous and return exactly True.
        It runs before both new effects and returned receipts. Read-only SQL is
        enforced for the check; trusted Python callbacks are not sandboxed.
        Check current actor/scope/ACL on replay too; expected domain revision
        usually applies only to a new effect. Payload binds the original intent.
        A saved receipt is the original result, not the current object state.
        """
        if (not callable(check) or inspect.iscoroutinefunction(check)
                or inspect.iscoroutinefunction(getattr(check, '__call__', None))):
            raise InvalidType('Supply a synchronous transaction check')
        return self._run(scope, operation_key, payload, apply, check=check)

    def _run(self, scope: str, operation_key: str, payload: Any,
             apply: Callable[[sqlite3.Connection], Any], *,
             check: Callable[[sqlite3.Connection, bool], bool] | None) -> OnceResult:
        for value in (scope, operation_key):
            if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
                raise ValidationFailure("Scope and operation key must be nonempty bounded strings")
        digest = hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute(
                "SELECT payload_hash, result_json FROM telegram_pattern_operations WHERE scope=? AND operation_key=?",
                (scope, operation_key),
            ).fetchone()
            if check is not None:
                allowed_reads = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ,
                                 sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
                connection.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK
                                          if action in allowed_reads else sqlite3.SQLITE_DENY)
                try:
                    decision = check(connection, old is not None)
                    if inspect.isawaitable(decision):
                        if inspect.iscoroutine(decision):
                            decision.close()
                        raise InvalidType('Transaction check must return a synchronous boolean')
                    if decision is not True:
                        raise PermissionDenied('Current action access denied')
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
