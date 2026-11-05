"""SDK-free durable receipt and fenced claims; business effects remain host-owned."""

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

InboxState = Literal['pending', 'processing', 'done', 'quarantined']
InboxReason = Literal[
    'unsupported-version',
    'unknown-update-kind',
    'decode-failed',
    'handler-rejected',
    'processing-failed',
    'lease-expired',
    'attempts-exhausted',
    'manual-review',
]
_REASONS = frozenset(
    {
        'unsupported-version',
        'unknown-update-kind',
        'decode-failed',
        'handler-rejected',
        'processing-failed',
        'lease-expired',
        'attempts-exhausted',
        'manual-review',
    }
)
_COLUMNS = frozenset(
    {
        'bot_id',
        'update_id',
        'payload_version',
        'payload_json',
        'payload_hash',
        'state',
        'reason',
        'received_at',
        'available_at',
        'attempts',
        'max_attempts',
        'worker_id',
        'claim_token',
        'lease_until',
    }
)
_UNSET = object()


class InboxConflict(ConflictFailure):
    """An existing delivery identity has a different payload/version or terminal outcome."""


class InboxLeaseLost(UnknownOutcome):
    """Claim ownership was lost; a host business effect may already have happened."""


@dataclass(frozen=True, slots=True)
class InboxReceipt:
    bot_id: int
    update_id: int
    state: InboxState
    duplicate: bool
    payload_version: int
    reason: InboxReason | None


@dataclass(frozen=True, slots=True)
class InboxClaim:
    bot_id: int
    update_id: int
    payload_version: int
    worker_id: str
    token: str = field(repr=False)
    attempt: int
    lease_until: float
    payload_json: str = field(repr=False)

    @property
    def payload(self) -> dict[str, Any]:
        """A fresh decoded copy; mutating it does not alter durable receipt or another caller."""
        return cast(dict[str, Any], json.loads(self.payload_json))


@dataclass(frozen=True, slots=True)
class InboxRecord:
    bot_id: int
    update_id: int
    payload_version: int
    state: InboxState
    reason: InboxReason | None
    attempts: int
    max_attempts: int
    received_at: float
    available_at: float
    worker_id: str | None
    lease_until: float | None
    payload_json: str = field(repr=False)

    @property
    def payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.payload_json))


def _identity(bot_id: int, update_id: object = _UNSET) -> None:
    if type(bot_id) is not int or not 1 <= bot_id <= 2**63 - 1:
        raise ValidationFailure('Use a positive bounded bot ID')
    if update_id is not _UNSET and (type(update_id) is not int or not 0 <= update_id <= 2**63 - 1):
        raise ValidationFailure('Use a nonnegative bounded update ID')


def _number(value: float, maximum: float, *, positive: bool = False) -> float:
    if type(value) not in {int, float}:
        raise ValidationFailure('Use a finite bounded number')
    if not (0 < value <= maximum if positive else 0 <= value <= maximum):
        raise ValidationFailure('Use a finite bounded number')
    if not math.isfinite(value):
        raise ValidationFailure('Use a finite bounded number')
    return float(value)


def _now(value: float | None) -> float:
    return _number(time.time() if value is None else value, float(2**53))


def _deadline(instant: float, duration: float) -> float:
    result = _number(instant + duration, float(2**53))
    if duration > 0 and result <= instant:
        raise ValidationFailure('Duration must advance the configured clock')
    return result


def _reason(value: str | None) -> InboxReason | None:
    if value is not None and (not isinstance(value, str) or value not in _REASONS):
        raise ValidationFailure('Use a documented inbox reason code')
    return cast(InboxReason | None, value)


def _receipt(row: sqlite3.Row, *, duplicate: bool = False) -> InboxReceipt:
    return InboxReceipt(
        row['bot_id'],
        row['update_id'],
        cast(InboxState, row['state']),
        duplicate,
        row['payload_version'],
        cast(InboxReason | None, row['reason']),
    )


class SQLiteInbox:
    """File SQLite receipt store; sync methods need a thread boundary in async hosts.

    Explicit initialize(), host-owned DB access/authorization/retention and reviewed migrations.
    Receipt is durable before receive() returns. A lease fences queue transitions, not arbitrary
    business I/O: use host idempotency/transactions when a handler can be replayed after a crash.
    """

    def __init__(
        self,
        database: str | Path,
        *,
        supported_versions: tuple[int, ...] = (1,),
        max_attempts: int = 5,
        max_payload_bytes: int = 1024 * 1024,
        timeout: float = 5.0,
    ) -> None:
        if not isinstance(database, (str, Path)) or not str(database) or str(database) == ':memory:':
            raise ValidationFailure('Use a file inbox database')
        if (
            not isinstance(supported_versions, tuple)
            or not supported_versions
            or len(supported_versions) > 32
            or any(type(version) is not int or not 1 <= version <= 2**31 - 1 for version in supported_versions)
            or len(set(supported_versions)) != len(supported_versions)
        ):
            raise ValidationFailure('Use distinct positive supported envelope versions')
        if type(max_attempts) is not int or not 1 <= max_attempts <= 1000:
            raise ValidationFailure('Use max_attempts between 1 and 1000')
        if type(max_payload_bytes) is not int or not 128 <= max_payload_bytes <= 8 * 1024 * 1024:
            raise ValidationFailure('Use a payload limit between 128 bytes and 8 MiB')
        self.database = str(database)
        self.supported_versions = frozenset(supported_versions)
        self.max_attempts = max_attempts
        self.max_payload_bytes = max_payload_bytes
        self.timeout = _number(timeout, 300, positive=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=self.timeout, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            # Receipt-before-ACK must not rely on an inherited unsafe synchronous pragma.
            connection.execute('PRAGMA synchronous=FULL')
        except BaseException:
            connection.close()
            raise
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
        with self._transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS telegram_pattern_inbox_meta (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version INTEGER NOT NULL
            )''')
            version = db.execute('SELECT schema_version FROM telegram_pattern_inbox_meta WHERE singleton=1').fetchone()
            if version is not None and version[0] != 1:
                raise UnsupportedCapability('Unsupported inbox schema; apply a reviewed migration')
            db.execute('''CREATE TABLE IF NOT EXISTS telegram_pattern_inbox (
                bot_id INTEGER NOT NULL, update_id INTEGER NOT NULL, payload_version INTEGER NOT NULL,
                payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','processing','done','quarantined')),
                reason TEXT, received_at REAL NOT NULL, available_at REAL NOT NULL,
                attempts INTEGER NOT NULL, max_attempts INTEGER NOT NULL,
                worker_id TEXT, claim_token TEXT, lease_until REAL,
                PRIMARY KEY(bot_id, update_id)
            )''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(telegram_pattern_inbox)')}
            if columns != _COLUMNS:
                raise UnsupportedCapability('Unexpected inbox schema; apply a reviewed migration')
            db.execute('INSERT OR IGNORE INTO telegram_pattern_inbox_meta VALUES (1,1)')
            db.execute('''CREATE INDEX IF NOT EXISTS telegram_pattern_inbox_ready
                ON telegram_pattern_inbox(bot_id,state,available_at,received_at,update_id)''')

    def receive(
        self,
        bot_id: int,
        update_id: int,
        payload: dict[str, Any],
        *,
        payload_version: int = 1,
        quarantine_reason: InboxReason | None = None,
        now: float | None = None,
    ) -> InboxReceipt:
        _identity(bot_id, update_id)
        if type(payload_version) is not int or not 1 <= payload_version <= 2**31 - 1:
            raise ValidationFailure('Use a positive bounded envelope version')
        if (
            type(payload) is not dict
            or type(payload.get('update_id')) is not int
            or payload.get('update_id') != update_id
        ):
            raise ValidationFailure('Payload update_id must match delivery identity')
        reason = _reason(quarantine_reason)
        instant = _now(now)
        try:
            digest = payload_digest(payload)
            serialized = canonical_json(payload)
            size = len(serialized.encode('utf-8'))
        except (UnicodeError, ValueError, RecursionError, TypeError):
            raise ValidationFailure('Use a bounded JSON object payload') from None
        if size > self.max_payload_bytes:
            raise ValidationFailure('Inbox payload exceeds the configured limit')
        if payload_version not in self.supported_versions:
            reason = 'unsupported-version'
        state = 'quarantined' if reason is not None else 'pending'
        with self._transaction() as db:
            old = db.execute(
                'SELECT * FROM telegram_pattern_inbox WHERE bot_id=? AND update_id=?', (bot_id, update_id)
            ).fetchone()
            if old is not None:
                if old['payload_version'] != payload_version or old['payload_hash'] != digest:
                    raise InboxConflict('Delivery identity already has a different payload or envelope version')
                # Duplicate admission is read-only, including proposed quarantine reason/policy changes.
                return _receipt(old, duplicate=True)
            db.execute(
                '''INSERT INTO telegram_pattern_inbox
                (bot_id,update_id,payload_version,payload_json,payload_hash,state,reason,
                 received_at,available_at,attempts,max_attempts) VALUES (?,?,?,?,?,?,?,?,?,0,?)''',
                (
                    bot_id,
                    update_id,
                    payload_version,
                    serialized,
                    digest,
                    state,
                    reason,
                    instant,
                    instant,
                    self.max_attempts,
                ),
            )
            return InboxReceipt(bot_id, update_id, cast(InboxState, state), False, payload_version, reason)

    def claim(
        self, bot_id: int, worker_id: str, *, lease_seconds: float = 30, now: float | None = None
    ) -> InboxClaim | None:
        _identity(bot_id)
        try:
            valid_worker = isinstance(worker_id, str) and bool(worker_id) and len(worker_id.encode('utf-8')) <= 128
        except UnicodeError:
            valid_worker = False
        if not valid_worker:
            raise ValidationFailure('Use a bounded worker identity')
        duration = _number(lease_seconds, 3600, positive=True)
        instant = _now(now)
        lease_until = _deadline(instant, duration)
        with self._transaction() as db:
            # A dead worker's receipt stays in the queue; exhausted work becomes observable quarantine.
            db.execute(
                '''UPDATE telegram_pattern_inbox SET state='quarantined',reason='attempts-exhausted',
                worker_id=NULL,claim_token=NULL,lease_until=NULL
                WHERE bot_id=? AND state IN ('pending','processing') AND attempts>=max_attempts
                AND (state='pending' OR lease_until<=?)''',
                (bot_id, instant),
            )
            db.execute(
                '''UPDATE telegram_pattern_inbox SET state='pending',reason='lease-expired',
                available_at=?,worker_id=NULL,claim_token=NULL,lease_until=NULL
                WHERE bot_id=? AND state='processing' AND lease_until<=?''',
                (instant, bot_id, instant),
            )
            versions = ','.join('?' for _ in self.supported_versions)
            row = db.execute(
                f'''SELECT * FROM telegram_pattern_inbox WHERE bot_id=? AND state='pending'
                AND available_at<=? AND payload_version IN ({versions})
                ORDER BY available_at,received_at,update_id LIMIT 1''',
                (bot_id, instant, *sorted(self.supported_versions)),
            ).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            attempt = row['attempts'] + 1
            db.execute(
                '''UPDATE telegram_pattern_inbox SET state='processing',worker_id=?,claim_token=?,
                lease_until=?,attempts=?,reason=NULL WHERE bot_id=? AND update_id=?''',
                (worker_id, token, lease_until, attempt, bot_id, row['update_id']),
            )
            return InboxClaim(
                bot_id,
                row['update_id'],
                row['payload_version'],
                worker_id,
                token,
                attempt,
                lease_until,
                row['payload_json'],
            )

    @staticmethod
    def _owned(db: sqlite3.Connection, claim: InboxClaim) -> sqlite3.Row:
        if not isinstance(claim, InboxClaim):
            raise ValidationFailure('Use the claim returned by this inbox')
        row = db.execute(
            'SELECT * FROM telegram_pattern_inbox WHERE bot_id=? AND update_id=?', (claim.bot_id, claim.update_id)
        ).fetchone()
        if (
            row is None
            or row['worker_id'] != claim.worker_id
            or row['claim_token'] != claim.token
            or row['attempts'] != claim.attempt
        ):
            raise InboxLeaseLost('Inbox claim is no longer owned')
        return cast(sqlite3.Row, row)

    def _finish(
        self, claim: InboxClaim, state: InboxState, reason: InboxReason | None, delay: float, now: float | None
    ) -> InboxReceipt:
        instant = _now(now)
        available_at = _deadline(instant, delay)
        with self._transaction() as db:
            row = self._owned(db, claim)
            if row['state'] == state and state in {'done', 'quarantined'}:
                if row['reason'] != reason:
                    raise InboxConflict('Terminal inbox outcome changed')
                return _receipt(row)
            if row['state'] != 'processing' or row['lease_until'] <= instant:
                raise InboxLeaseLost('Inbox claim expired or is no longer processing')
            if state == 'pending' and row['attempts'] >= row['max_attempts']:
                state, reason = 'quarantined', 'attempts-exhausted'
            db.execute(
                '''UPDATE telegram_pattern_inbox SET state=?,reason=?,available_at=?,lease_until=NULL,
                worker_id=?,claim_token=? WHERE bot_id=? AND update_id=?''',
                (
                    state,
                    reason,
                    available_at,
                    None if state == 'pending' else claim.worker_id,
                    None if state == 'pending' else claim.token,
                    claim.bot_id,
                    claim.update_id,
                ),
            )
            return InboxReceipt(claim.bot_id, claim.update_id, state, False, row['payload_version'], reason)

    def complete(self, claim: InboxClaim, *, now: float | None = None) -> InboxReceipt:
        return self._finish(claim, 'done', None, 0, now)

    def retry(
        self,
        claim: InboxClaim,
        *,
        delay_seconds: float,
        reason: InboxReason = 'processing-failed',
        now: float | None = None,
    ) -> InboxReceipt:
        delay = _number(delay_seconds, 86400)
        checked_reason = _reason(reason)
        return self._finish(claim, 'pending', checked_reason, delay, now)

    def quarantine(self, claim: InboxClaim, *, reason: InboxReason, now: float | None = None) -> InboxReceipt:
        checked_reason = _reason(reason)
        if checked_reason is None:
            raise ValidationFailure('Quarantine needs a documented reason code')
        return self._finish(claim, 'quarantined', checked_reason, 0, now)

    def renew(self, claim: InboxClaim, *, lease_seconds: float = 30, now: float | None = None) -> InboxClaim:
        duration = _number(lease_seconds, 3600, positive=True)
        instant = _now(now)
        proposed_until = _deadline(instant, duration)
        with self._transaction() as db:
            row = self._owned(db, claim)
            if row['state'] != 'processing' or row['lease_until'] <= instant:
                raise InboxLeaseLost('Inbox claim expired or is no longer processing')
            lease_until = max(row['lease_until'], proposed_until)
            db.execute(
                'UPDATE telegram_pattern_inbox SET lease_until=? WHERE bot_id=? AND update_id=?',
                (lease_until, claim.bot_id, claim.update_id),
            )
            return InboxClaim(
                claim.bot_id,
                claim.update_id,
                claim.payload_version,
                claim.worker_id,
                claim.token,
                claim.attempt,
                lease_until,
                row['payload_json'],
            )

    def get(self, bot_id: int, update_id: int) -> InboxRecord | None:
        _identity(bot_id, update_id)
        db = self._connect()
        try:
            row = db.execute(
                'SELECT * FROM telegram_pattern_inbox WHERE bot_id=? AND update_id=?', (bot_id, update_id)
            ).fetchone()
            if row is None:
                return None
            return InboxRecord(
                row['bot_id'],
                row['update_id'],
                row['payload_version'],
                cast(InboxState, row['state']),
                cast(InboxReason | None, row['reason']),
                row['attempts'],
                row['max_attempts'],
                row['received_at'],
                row['available_at'],
                row['worker_id'],
                row['lease_until'],
                row['payload_json'],
            )
        finally:
            db.close()

    def counts(self, bot_id: int) -> dict[InboxState, int]:
        """Safe aggregates only: expired processing is recovered by the next claim, not this read."""
        _identity(bot_id)
        db = self._connect()
        try:
            result: dict[InboxState, int] = {'pending': 0, 'processing': 0, 'done': 0, 'quarantined': 0}
            query = 'SELECT state,COUNT(*) AS total FROM telegram_pattern_inbox WHERE bot_id=? GROUP BY state'
            for row in db.execute(query, (bot_id,)):
                result[cast(InboxState, row['state'])] = row['total']
            return result
        finally:
            db.close()
