"""Transactional local intents and conservative external-outcome recovery; no transport."""

from __future__ import annotations

import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal, cast

from ._shared import canonical_json, payload_digest
from .errors import ConflictFailure, UnknownOutcome, UnsupportedCapability, ValidationFailure

OutboxState = Literal['pending', 'sending', 'sent', 'unknown', 'failed']
OutboxResolution = Literal['sent', 'absent', 'unresolved']
_COLUMNS = frozenset(
    {
        'scope',
        'operation_key',
        'payload_json',
        'payload_hash',
        'state',
        'attempts',
        'max_attempts',
        'revision',
        'created_at',
        'available_at',
        'worker_id',
        'claim_token',
        'lease_until',
        'result_json',
        'evidence_ref',
        'reason',
    }
)


class OutboxConflict(ConflictFailure):
    """An intent, receipt or reconciliation revision conflicts with durable state."""


class OutboxLeaseLost(UnknownOutcome):
    """A sender no longer owns this live claim; reconcile its outcome instead."""


@dataclass(frozen=True, slots=True)
class OutboxReceipt:
    scope: str
    operation_key: str
    state: OutboxState
    revision: int
    duplicate: bool


@dataclass(frozen=True, slots=True)
class OutboxClaim:
    scope: str
    operation_key: str
    worker_id: str
    token: str = field(repr=False)
    attempt: int
    lease_until: float
    payload_json: str = field(repr=False)

    @property
    def payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.payload_json))


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    scope: str
    operation_key: str
    state: OutboxState
    revision: int
    attempts: int
    max_attempts: int
    available_at: float
    worker_id: str | None
    lease_until: float | None
    reason: str | None
    evidence_ref: str | None
    payload_json: str = field(repr=False)
    result_json: str | None = field(repr=False)

    @property
    def payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.payload_json))

    @property
    def result(self) -> Any:
        return None if self.result_json is None else json.loads(self.result_json)


def _text(value: str, maximum: int = 256) -> None:
    try:
        valid = isinstance(value, str) and bool(value) and len(value.encode('utf-8')) <= maximum
    except UnicodeError:
        valid = False
    if not valid:
        raise ValidationFailure('Use a nonempty bounded UTF-8 identity/reference')


def _number(value: float, maximum: float = float(2**53), *, positive: bool = False) -> float:
    if type(value) not in (float, int):
        raise ValidationFailure('Use a finite bounded number')
    if not (0 < value <= maximum if positive else 0 <= value <= maximum) or not math.isfinite(value):
        raise ValidationFailure('Use a finite bounded number')
    return float(value)


def _now(value: float | None) -> float:
    return _number(time.time() if value is None else value)


def _deadline(instant: float, duration: float) -> float:
    result = _number(instant + duration)
    if duration > 0 and result <= instant:
        raise ValidationFailure('Duration must advance the configured clock')
    return result


def _record(row: sqlite3.Row) -> OutboxRecord:
    return OutboxRecord(
        row['scope'],
        row['operation_key'],
        cast(OutboxState, row['state']),
        row['revision'],
        row['attempts'],
        row['max_attempts'],
        row['available_at'],
        row['worker_id'],
        row['lease_until'],
        row['reason'],
        row['evidence_ref'],
        row['payload_json'],
        row['result_json'],
    )


class SQLiteOutbox:
    """Persist local business state + intent together; external I/O stays host-owned.

    enqueue() requires the caller's active transaction on this same main file.
    Other methods own short transactions. Expired sending becomes unknown,
    NEVER automatically pending. Call sync methods through the host's thread
    boundary in async applications. Trusted host code owns ACLs and evidence.
    """

    def __init__(
        self,
        database: str | Path,
        *,
        max_attempts: int = 5,
        max_payload_bytes: int = 1024 * 1024,
        timeout: float = 5.0,
    ) -> None:
        if not isinstance(database, (str, Path)) or not str(database) or str(database) == ':memory:':
            raise ValidationFailure('Use a file outbox database')
        if type(max_attempts) is not int or not 1 <= max_attempts <= 1000:
            raise ValidationFailure('Use max_attempts between 1 and 1000')
        if type(max_payload_bytes) is not int or not 128 <= max_payload_bytes <= 8 * 1024 * 1024:
            raise ValidationFailure('Use a payload limit between 128 bytes and 8 MiB')
        self.database = str(Path(database).resolve())
        self.max_attempts = max_attempts
        self.max_payload_bytes = max_payload_bytes
        self.timeout = _number(timeout, 300, positive=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=self.timeout, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA synchronous=FULL')
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute('BEGIN IMMEDIATE')
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Explicit setup only; incompatible existing schemas need a reviewed migration."""
        with self._transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS telegram_pattern_outbox_meta (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version INTEGER NOT NULL
            )''')
            version = db.execute('SELECT schema_version FROM telegram_pattern_outbox_meta WHERE singleton=1').fetchone()
            if version is not None and version[0] != 1:
                raise UnsupportedCapability('Unsupported outbox schema; apply a reviewed migration')
            db.execute('''CREATE TABLE IF NOT EXISTS telegram_pattern_outbox (
                scope TEXT NOT NULL, operation_key TEXT NOT NULL, payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','sending','sent','unknown','failed')),
                attempts INTEGER NOT NULL, max_attempts INTEGER NOT NULL, revision INTEGER NOT NULL,
                created_at REAL NOT NULL, available_at REAL NOT NULL,
                worker_id TEXT, claim_token TEXT, lease_until REAL,
                result_json TEXT, evidence_ref TEXT, reason TEXT,
                PRIMARY KEY(scope,operation_key)
            )''')
            if {row['name'] for row in db.execute('PRAGMA table_info(telegram_pattern_outbox)')} != _COLUMNS:
                raise UnsupportedCapability('Unexpected outbox schema; apply a reviewed migration')
            db.execute('INSERT OR IGNORE INTO telegram_pattern_outbox_meta VALUES(1,1)')
            db.execute('''CREATE INDEX IF NOT EXISTS telegram_pattern_outbox_ready
                ON telegram_pattern_outbox(scope,state,available_at,created_at,operation_key)''')

    def _json(self, value: Any) -> tuple[str, str]:
        try:
            digest = payload_digest(value)
            serialized = canonical_json(value)
            size = len(serialized.encode('utf-8'))
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ValidationFailure('Use bounded strict JSON') from None
        if size > self.max_payload_bytes:
            raise ValidationFailure('Outbox JSON exceeds the configured limit')
        return serialized, digest

    def enqueue(
        self,
        connection: sqlite3.Connection,
        scope: str,
        operation_key: str,
        payload: dict[str, Any],
        *,
        now: float | None = None,
    ) -> OutboxReceipt:
        """Insert intent in the supplied business transaction; NEVER commits.

        Return is provisional until the caller commits. Let failures roll back
        the whole business transaction; do not swallow a conflict and commit.
        A duplicate receipt deduplicates the intent, not arbitrary host writes.
        """
        _text(scope)
        _text(operation_key)
        instant = _now(now)
        if type(payload) is not dict:
            raise ValidationFailure('Use a JSON object intent')
        serialized, digest = self._json(payload)
        if not isinstance(connection, sqlite3.Connection) or not connection.in_transaction:
            raise ValidationFailure('Enqueue needs the active business transaction')
        databases = connection.execute('PRAGMA database_list').fetchall()
        main = next((row[2] for row in databases if row[1] == 'main'), None)
        if not main or Path(main).resolve() != Path(self.database):
            raise ValidationFailure('Business state and outbox must use the same main SQLite file')
        # No implicit transactions or second connection: these statements belong
        # to the host's transaction, including SQLiteOnce.run_guarded apply().
        cursor = connection.execute(
            'SELECT payload_hash,state,revision FROM telegram_pattern_outbox WHERE scope=? AND operation_key=?',
            (scope, operation_key),
        )
        old = cursor.fetchone()
        if old is not None:
            if old[0] != digest:
                raise OutboxConflict('Operation identity already has a different intent')
            return OutboxReceipt(scope, operation_key, cast(OutboxState, old[1]), old[2], True)
        connection.execute(
            '''INSERT INTO telegram_pattern_outbox
               (scope,operation_key,payload_json,payload_hash,state,attempts,max_attempts,revision,created_at,available_at)
               VALUES(?,?,?,?,'pending',0,?,0,?,?)''',
            (scope, operation_key, serialized, digest, self.max_attempts, instant, instant),
        )
        return OutboxReceipt(scope, operation_key, 'pending', 0, False)

    @staticmethod
    def _expire(db: sqlite3.Connection, scope: str, instant: float) -> int:
        return db.execute(
            '''UPDATE telegram_pattern_outbox SET state='unknown',reason='lease-expired',
               revision=revision+1,lease_until=NULL
               WHERE scope=? AND state='sending' AND lease_until<=?''',
            (scope, instant),
        ).rowcount

    def recover_expired(self, scope: str, *, now: float | None = None) -> int:
        _text(scope)
        instant = _now(now)
        with self._transaction() as db:
            return self._expire(db, scope, instant)

    def claim(
        self,
        scope: str,
        worker_id: str,
        *,
        lease_seconds: float = 30,
        now: float | None = None,
    ) -> OutboxClaim | None:
        _text(scope)
        _text(worker_id, 128)
        instant = _now(now)
        deadline = _deadline(instant, _number(lease_seconds, 3600, positive=True))
        with self._transaction() as db:
            self._expire(db, scope, instant)
            row = db.execute(
                '''SELECT * FROM telegram_pattern_outbox WHERE scope=? AND state='pending'
                   AND available_at<=? AND attempts<max_attempts
                   ORDER BY available_at,created_at,operation_key LIMIT 1''',
                (scope, instant),
            ).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            db.execute(
                '''UPDATE telegram_pattern_outbox SET state='sending',worker_id=?,claim_token=?,lease_until=?,
                   attempts=attempts+1,revision=revision+1,reason=NULL WHERE scope=? AND operation_key=?''',
                (worker_id, token, deadline, scope, row['operation_key']),
            )
            return OutboxClaim(
                scope, row['operation_key'], worker_id, token, row['attempts'] + 1, deadline, row['payload_json']
            )

    @staticmethod
    def _owned(db: sqlite3.Connection, claim: OutboxClaim) -> sqlite3.Row:
        if not isinstance(claim, OutboxClaim):
            raise ValidationFailure('Use the claim returned by this outbox')
        row = db.execute(
            'SELECT * FROM telegram_pattern_outbox WHERE scope=? AND operation_key=?',
            (claim.scope, claim.operation_key),
        ).fetchone()
        if (
            row is None
            or row['worker_id'] != claim.worker_id
            or row['claim_token'] != claim.token
            or row['attempts'] != claim.attempt
        ):
            raise OutboxLeaseLost('Outbox claim is no longer owned')
        return cast(sqlite3.Row, row)

    def confirm(self, claim: OutboxClaim, result: Any, *, now: float | None = None) -> OutboxRecord:
        """Persist a definitive success response while this sending claim is live."""
        serialized, _digest = self._json(result)
        instant = _now(now)
        with self._transaction() as db:
            row = self._owned(db, claim)
            if row['state'] == 'sent':
                if row['result_json'] != serialized:
                    raise OutboxConflict('Confirmed receipt changed')
                return _record(row)
            if row['state'] != 'sending' or row['lease_until'] <= instant:
                raise OutboxLeaseLost('Claim expired or is no longer sending; reconcile the result')
            db.execute(
                '''UPDATE telegram_pattern_outbox SET state='sent',result_json=?,revision=revision+1,
                   lease_until=NULL WHERE scope=? AND operation_key=?''',
                (serialized, claim.scope, claim.operation_key),
            )
            return self._get(db, claim.scope, claim.operation_key)

    def mark_unknown(self, claim: OutboxClaim, *, now: float | None = None) -> OutboxRecord:
        """Timeout/cancel/disconnect does not prove absence of the external effect."""
        _now(now)
        with self._transaction() as db:
            row = self._owned(db, claim)
            if row['state'] == 'unknown':
                return _record(row)
            if row['state'] != 'sending':
                raise OutboxLeaseLost('Claim is no longer sending')
            db.execute(
                '''UPDATE telegram_pattern_outbox SET state='unknown',reason='worker-unknown',
                   revision=revision+1,lease_until=NULL WHERE scope=? AND operation_key=?''',
                (claim.scope, claim.operation_key),
            )
            return self._get(db, claim.scope, claim.operation_key)

    def reconcile(
        self,
        scope: str,
        operation_key: str,
        *,
        expected_revision: int,
        outcome: OutboxResolution,
        evidence_ref: str,
        result: Any = None,
        retry_after: float = 0,
        now: float | None = None,
    ) -> OutboxRecord:
        """Resolve ONLY unknown with fresh host-verified evidence and CAS revision.

        absent asserts no effect AND no possible late effect from the old attempt.
        An empty query, elapsed lease or timeout alone is NOT sufficient proof.
        Only this resolution authorizes a bounded retry; no transport is called.
        """
        _text(scope)
        _text(operation_key)
        _text(evidence_ref, 512)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValidationFailure('Use a nonnegative expected revision')
        if not isinstance(outcome, str) or outcome not in {'sent', 'absent', 'unresolved'}:
            raise ValidationFailure('Use a documented reconciliation outcome')
        instant = _now(now)
        available = _deadline(instant, _number(retry_after, 86400))
        if outcome != 'absent' and retry_after != 0:
            raise ValidationFailure('Only proven absence may schedule a retry')
        if outcome != 'sent' and result is not None:
            raise ValidationFailure('Only confirmed success has a receipt')
        serialized = self._json(result)[0] if outcome == 'sent' else None
        with self._transaction() as db:
            row = self._get(db, scope, operation_key)
            if row.state != 'unknown' or row.revision != expected_revision:
                raise OutboxConflict('Reconciliation needs the current unknown revision')
            state: OutboxState = 'unknown'
            reason = 'unresolved'
            if outcome == 'sent':
                state, reason = 'sent', 'reconciled-sent'
            elif outcome == 'absent':
                state = 'pending' if row.attempts < row.max_attempts else 'failed'
                reason = 'reconciled-absent' if state == 'pending' else 'attempts-exhausted'
            db.execute(
                '''UPDATE telegram_pattern_outbox SET state=?,reason=?,evidence_ref=?,result_json=?,
                   available_at=?,revision=revision+1,lease_until=NULL,worker_id=NULL,claim_token=NULL
                   WHERE scope=? AND operation_key=?''',
                (state, reason, evidence_ref, serialized, available, scope, operation_key),
            )
            return self._get(db, scope, operation_key)

    @staticmethod
    def _get(db: sqlite3.Connection, scope: str, operation_key: str) -> OutboxRecord:
        row = db.execute(
            'SELECT * FROM telegram_pattern_outbox WHERE scope=? AND operation_key=?', (scope, operation_key)
        ).fetchone()
        if row is None:
            raise OutboxConflict('Outbox intent does not exist')
        return _record(row)

    def get(self, scope: str, operation_key: str) -> OutboxRecord | None:
        """Read-only observation; call recover_expired explicitly to recover sending."""
        _text(scope)
        _text(operation_key)
        db = self._connect()
        try:
            row = db.execute(
                'SELECT * FROM telegram_pattern_outbox WHERE scope=? AND operation_key=?', (scope, operation_key)
            ).fetchone()
            return None if row is None else _record(row)
        finally:
            db.close()
