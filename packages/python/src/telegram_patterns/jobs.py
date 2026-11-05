"""Durable notification intentions with fenced dispatch and explicit unknown outcomes."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal, cast

from ._shared import canonical_json, payload_digest
from .errors import ConflictFailure, UnknownOutcome, UnsupportedCapability, ValidationFailure

JobState = Literal['scheduled', 'claimed', 'sending', 'sent', 'cancelled', 'expired', 'skipped', 'failed', 'unknown']
JobOutcome = Literal['sent', 'permanent-failure', 'flood', 'unknown']
JobReason = Literal[
    'missing-recipient',
    'opted-out',
    'recipient-unreachable',
    'deadline',
    'cancelled',
    'lease-expired',
    'attempts-exhausted',
    'rate-limited',
    'flood-rejected',
    'retry-window-exceeded',
    'send-outcome-unknown',
    'reconciled-sent',
    'reconciled-failed',
]
_STATES = ('scheduled', 'claimed', 'sending', 'sent', 'cancelled', 'expired', 'skipped', 'failed', 'unknown')
_SAFE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_MAX_ID = 2**53 - 1
_MAX_TIME = 253402300799.0
_COLUMNS = {
    'bot_id',
    'job_id',
    'recipient_id',
    'payload_json',
    'intent_hash',
    'created_at',
    'due_at',
    'deadline_at',
    'state',
    'reason',
    'attempts',
    'max_attempts',
    'worker_id',
    'claim_token',
    'lease_until',
    'cancel_requested',
    'message_id',
    'revision',
    'evidence_ref',
}


class JobConflict(ConflictFailure):
    """An intent, revision or terminal outcome conflicts with durable state."""


class JobLeaseLost(UnknownOutcome):
    """The worker lost ownership; a started external effect may already have happened."""


class JobQueueFull(ConflictFailure):
    """The bot's persisted active-job capacity has been reached."""


@dataclass(frozen=True, slots=True)
class JobClaim:
    bot_id: int
    job_id: str
    recipient_id: int
    worker_id: str
    attempt: int
    lease_until: float
    token: str = field(repr=False)
    payload_json: str = field(repr=False)

    @property
    def payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.payload_json))


@dataclass(frozen=True, slots=True)
class JobRecord:
    bot_id: int
    job_id: str
    recipient_id: int
    state: JobState
    reason: JobReason | None
    due_at: float
    deadline_at: float
    attempts: int
    max_attempts: int
    cancel_requested: bool
    revision: int
    message_id: int | None
    evidence_ref: str | None
    lease_until: float | None
    payload_json: str = field(repr=False)

    @property
    def payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.payload_json))


def _id(value: int, *, recipient: bool = False) -> None:
    if type(value) is not int or (not 0 < abs(value) <= _MAX_ID if recipient else not 0 < value <= _MAX_ID):
        raise ValidationFailure('Use an exact bounded Telegram identity')


def _key(value: str) -> None:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise ValidationFailure('Use a safe opaque ASCII identifier of at most 128 characters')


def _number(value: float, maximum: float, *, positive: bool = False) -> float:
    if type(value) not in {int, float} or not (0 < value <= maximum if positive else 0 <= value <= maximum):
        raise ValidationFailure('Use a finite bounded time value')
    if not math.isfinite(value):
        raise ValidationFailure('Use a finite bounded time value')
    return float(value)


def _now(value: float | None) -> float:
    return _number(time.time() if value is None else value, _MAX_TIME)


def _later(instant: float, duration: float) -> float:
    result = _number(instant + duration, _MAX_TIME)
    if duration > 0 and result <= instant:
        raise ValidationFailure('Duration must advance the configured clock')
    return result


def _record(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        row['bot_id'],
        row['job_id'],
        row['recipient_id'],
        cast(JobState, row['state']),
        cast(JobReason | None, row['reason']),
        row['due_at'],
        row['deadline_at'],
        row['attempts'],
        row['max_attempts'],
        bool(row['cancel_requested']),
        row['revision'],
        row['message_id'],
        row['evidence_ref'],
        row['lease_until'],
        row['payload_json'],
    )


class SQLiteJobQueue:
    """Local SQLite jobs; no transport calls and no implicit replay of a started send.

    The first schedule for a bot persists its capacity and pacing policy. Later workers
    use that policy; a constructor change cannot reset cooldown or widen an existing bot.
    Host business state and schedule() are separate transactions.
    """

    def __init__(
        self,
        database: str | Path,
        *,
        bot_interval: float = 1,
        recipient_interval: float = 3,
        max_active_jobs: int = 10000,
        max_payload_bytes: int = 1024 * 1024,
        timeout: float = 5,
    ) -> None:
        if not isinstance(database, (str, Path)) or not str(database) or str(database) == ':memory:':
            raise ValidationFailure('Use a file jobs database')
        if type(max_active_jobs) is not int or not 1 <= max_active_jobs <= 100000:
            raise ValidationFailure('Use an active-job capacity between 1 and 100000')
        if type(max_payload_bytes) is not int or not 128 <= max_payload_bytes <= 8 * 1024 * 1024:
            raise ValidationFailure('Use a payload limit between 128 bytes and 8 MiB')
        self.database = str(database)
        self.bot_interval = _number(bot_interval, 3600, positive=True)
        self.recipient_interval = _number(recipient_interval, 3600, positive=True)
        if min(self.bot_interval, self.recipient_interval) < 0.001:
            raise ValidationFailure('Use pacing intervals of at least one millisecond')
        self.max_active_jobs = max_active_jobs
        self.max_payload_bytes = max_payload_bytes
        self.timeout = _number(timeout, 300, positive=True)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=self.timeout, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA synchronous=FULL')
        except BaseException:
            db.close()
            raise
        return db

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self) -> None:
        with self._transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS telegram_pattern_jobs_meta (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version INTEGER NOT NULL)''')
            version = db.execute('SELECT schema_version FROM telegram_pattern_jobs_meta WHERE singleton=1').fetchone()
            if version is not None and version[0] != 1:
                raise UnsupportedCapability('Unsupported jobs schema; apply a reviewed migration')
            db.execute('''CREATE TABLE IF NOT EXISTS telegram_pattern_job_bots (
                bot_id INTEGER PRIMARY KEY, next_at REAL NOT NULL, bot_interval REAL NOT NULL,
                recipient_interval REAL NOT NULL, capacity INTEGER NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS telegram_pattern_job_recipients (
                bot_id INTEGER NOT NULL, recipient_id INTEGER NOT NULL, subscribed INTEGER NOT NULL,
                reachable INTEGER NOT NULL, next_at REAL NOT NULL, PRIMARY KEY(bot_id,recipient_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS telegram_pattern_jobs (
                bot_id INTEGER NOT NULL, job_id TEXT NOT NULL, recipient_id INTEGER NOT NULL,
                payload_json TEXT NOT NULL, intent_hash TEXT NOT NULL, created_at REAL NOT NULL,
                due_at REAL NOT NULL, deadline_at REAL NOT NULL, state TEXT NOT NULL, reason TEXT,
                attempts INTEGER NOT NULL, max_attempts INTEGER NOT NULL, worker_id TEXT,
                claim_token TEXT, lease_until REAL, cancel_requested INTEGER NOT NULL DEFAULT 0,
                message_id INTEGER, revision INTEGER NOT NULL, evidence_ref TEXT,
                PRIMARY KEY(bot_id,job_id))''')
            if {row['name'] for row in db.execute('PRAGMA table_info(telegram_pattern_jobs)')} != _COLUMNS:
                raise UnsupportedCapability('Unexpected jobs schema; apply a reviewed migration')
            db.execute('INSERT OR IGNORE INTO telegram_pattern_jobs_meta VALUES (1,1)')
            db.execute('''CREATE INDEX IF NOT EXISTS telegram_pattern_jobs_ready
                ON telegram_pattern_jobs(bot_id,state,due_at,deadline_at)''')

    @staticmethod
    def _get(db: sqlite3.Connection, bot_id: int, job_id: str) -> sqlite3.Row:
        row = db.execute('SELECT * FROM telegram_pattern_jobs WHERE bot_id=? AND job_id=?', (bot_id, job_id)).fetchone()
        if row is None:
            raise JobConflict('Job does not exist in this bot scope')
        return cast(sqlite3.Row, row)

    @staticmethod
    def _suppress(db: sqlite3.Connection, bot_id: int) -> int:
        changed = db.execute(
            '''UPDATE telegram_pattern_jobs SET state='skipped',
            reason=CASE WHEN NOT EXISTS(SELECT 1 FROM telegram_pattern_job_recipients p
              WHERE p.bot_id=telegram_pattern_jobs.bot_id AND p.recipient_id=telegram_pattern_jobs.recipient_id)
              THEN 'missing-recipient'
              WHEN EXISTS(SELECT 1 FROM telegram_pattern_job_recipients p
              WHERE p.bot_id=telegram_pattern_jobs.bot_id AND p.recipient_id=telegram_pattern_jobs.recipient_id
                AND p.subscribed=0) THEN 'opted-out' ELSE 'recipient-unreachable' END,
            worker_id=NULL,claim_token=NULL,lease_until=NULL,revision=revision+1
            WHERE bot_id=? AND state IN ('scheduled','claimed') AND NOT EXISTS(
              SELECT 1 FROM telegram_pattern_job_recipients p WHERE p.bot_id=telegram_pattern_jobs.bot_id
              AND p.recipient_id=telegram_pattern_jobs.recipient_id AND p.subscribed=1 AND p.reachable=1)''',
            (bot_id,),
        ).rowcount
        db.execute(
            '''UPDATE telegram_pattern_jobs SET cancel_requested=1,revision=revision+1
            WHERE bot_id=? AND state='sending' AND cancel_requested=0 AND NOT EXISTS(
              SELECT 1 FROM telegram_pattern_job_recipients p WHERE p.bot_id=telegram_pattern_jobs.bot_id
              AND p.recipient_id=telegram_pattern_jobs.recipient_id AND p.subscribed=1 AND p.reachable=1)''',
            (bot_id,),
        )
        return changed

    def set_recipient(self, bot_id: int, recipient_id: int, *, subscribed: bool, reachable: bool) -> None:
        _id(bot_id)
        _id(recipient_id, recipient=True)
        if type(subscribed) is not bool or type(reachable) is not bool:
            raise ValidationFailure('Use explicit recipient policy booleans')
        with self._transaction() as db:
            db.execute(
                '''INSERT INTO telegram_pattern_job_recipients VALUES (?,?,?,?,0)
                ON CONFLICT(bot_id,recipient_id) DO UPDATE SET subscribed=excluded.subscribed,
                reachable=excluded.reachable''',
                (bot_id, recipient_id, int(subscribed), int(reachable)),
            )
            self._suppress(db, bot_id)

    def schedule(
        self,
        bot_id: int,
        job_id: str,
        recipient_id: int,
        payload: dict[str, Any],
        *,
        due_at: float,
        deadline_at: float,
        max_attempts: int = 3,
        now: float | None = None,
    ) -> JobRecord:
        _id(bot_id)
        _id(recipient_id, recipient=True)
        _key(job_id)
        instant, due, deadline = _now(now), _number(due_at, _MAX_TIME), _number(deadline_at, _MAX_TIME)
        if deadline <= due:
            raise ValidationFailure('Use a useful deadline after the due time')
        if type(max_attempts) is not int or not 1 <= max_attempts <= 100:
            raise ValidationFailure('Use an attempt budget between 1 and 100')
        if type(payload) is not dict:
            raise ValidationFailure('Use a bounded JSON object payload')
        try:
            payload_digest(payload)
            serialized = canonical_json(payload)
            if len(serialized.encode('utf-8')) > self.max_payload_bytes:
                raise ValueError
            digest = payload_digest([recipient_id, serialized, due, deadline, max_attempts])
        except (ValueError, TypeError, RecursionError, UnicodeError):
            raise ValidationFailure('Use a bounded JSON object payload') from None
        with self._transaction() as db:
            old = db.execute(
                'SELECT * FROM telegram_pattern_jobs WHERE bot_id=? AND job_id=?', (bot_id, job_id)
            ).fetchone()
            if old is not None:
                if old['intent_hash'] != digest:
                    raise JobConflict('Job identity already has a different immutable intent')
                return _record(old)
            if deadline <= instant:
                raise ValidationFailure('Use a future useful deadline')
            db.execute(
                '''INSERT OR IGNORE INTO telegram_pattern_job_bots VALUES (?,0,?,?,?)''',
                (bot_id, self.bot_interval, self.recipient_interval, self.max_active_jobs),
            )
            capacity = db.execute(
                'SELECT capacity FROM telegram_pattern_job_bots WHERE bot_id=?', (bot_id,)
            ).fetchone()[0]
            active = db.execute(
                '''SELECT COUNT(*) FROM telegram_pattern_jobs WHERE bot_id=?
                AND state IN ('scheduled','claimed','sending','unknown')''',
                (bot_id,),
            ).fetchone()[0]
            if active >= capacity:
                raise JobQueueFull('Bot active-job capacity reached')
            db.execute(
                '''INSERT INTO telegram_pattern_jobs
                (bot_id,job_id,recipient_id,payload_json,intent_hash,created_at,due_at,deadline_at,
                 state,attempts,max_attempts,revision) VALUES (?,?,?,?,?,?,?,?,'scheduled',0,?,1)''',
                (bot_id, job_id, recipient_id, serialized, digest, instant, due, deadline, max_attempts),
            )
            return _record(self._get(db, bot_id, job_id))

    def _recover(self, db: sqlite3.Connection, bot_id: int, instant: float) -> int:
        changed = db.execute(
            '''UPDATE telegram_pattern_jobs SET state='unknown',reason='send-outcome-unknown',
            lease_until=NULL,revision=revision+1 WHERE bot_id=? AND state='sending' AND lease_until<=?''',
            (bot_id, instant),
        ).rowcount
        changed += db.execute(
            '''UPDATE telegram_pattern_jobs SET
            state=CASE WHEN attempts>=max_attempts THEN 'failed' ELSE 'scheduled' END,
            reason=CASE WHEN attempts>=max_attempts THEN 'attempts-exhausted' ELSE 'lease-expired' END,
            worker_id=NULL,claim_token=NULL,lease_until=NULL,revision=revision+1
            WHERE bot_id=? AND state='claimed' AND lease_until<=?''',
            (bot_id, instant),
        ).rowcount
        changed += db.execute(
            '''UPDATE telegram_pattern_jobs SET state='expired',reason='deadline',
            worker_id=NULL,claim_token=NULL,lease_until=NULL,revision=revision+1
            WHERE bot_id=? AND state IN ('scheduled','claimed') AND deadline_at<=?''',
            (bot_id, instant),
        ).rowcount
        return changed + self._suppress(db, bot_id)

    def recover(self, bot_id: int, *, now: float | None = None) -> int:
        _id(bot_id)
        instant = _now(now)
        with self._transaction() as db:
            return self._recover(db, bot_id, instant)

    def claim(
        self, bot_id: int, worker_id: str, *, lease_seconds: float = 30, now: float | None = None
    ) -> JobClaim | None:
        _id(bot_id)
        _key(worker_id)
        instant = _now(now)
        deadline = _later(instant, _number(lease_seconds, 3600, positive=True))
        with self._transaction() as db:
            self._recover(db, bot_id, instant)
            row = db.execute(
                '''SELECT j.* FROM telegram_pattern_jobs j
                JOIN telegram_pattern_job_bots b ON b.bot_id=j.bot_id
                JOIN telegram_pattern_job_recipients p ON p.bot_id=j.bot_id AND p.recipient_id=j.recipient_id
                WHERE j.bot_id=? AND j.state='scheduled' AND j.due_at<=? AND j.deadline_at>?
                  AND j.attempts<j.max_attempts AND b.next_at<=? AND p.next_at<=?
                  AND p.subscribed=1 AND p.reachable=1 ORDER BY j.due_at,j.created_at,j.job_id LIMIT 1''',
                (bot_id, instant, instant, instant, instant),
            ).fetchone()
            if row is None:
                return None
            token, attempt = uuid.uuid4().hex, row['attempts'] + 1
            db.execute(
                '''UPDATE telegram_pattern_jobs SET state='claimed',reason=NULL,worker_id=?,claim_token=?,
                lease_until=?,attempts=?,revision=revision+1 WHERE bot_id=? AND job_id=?''',
                (worker_id, token, deadline, attempt, bot_id, row['job_id']),
            )
            return JobClaim(
                bot_id, row['job_id'], row['recipient_id'], worker_id, attempt, deadline, token, row['payload_json']
            )

    def _owned(self, db: sqlite3.Connection, claim: JobClaim, instant: float, phases: tuple[str, ...]) -> sqlite3.Row:
        if not isinstance(claim, JobClaim):
            raise ValidationFailure('Use a job claim returned by this queue')
        row = self._get(db, claim.bot_id, claim.job_id)
        if (
            row['worker_id'] != claim.worker_id
            or row['claim_token'] != claim.token
            or row['attempts'] != claim.attempt
            or row['state'] not in phases
            or row['lease_until'] is None
            or row['lease_until'] <= instant
        ):
            raise JobLeaseLost('Job phase or claim is no longer owned')
        return row

    def start(self, claim: JobClaim, *, now: float | None = None) -> JobRecord:
        instant = _now(now)
        with self._transaction() as db:
            row = self._owned(db, claim, instant, ('claimed',))
            if row['deadline_at'] <= instant:
                db.execute(
                    '''UPDATE telegram_pattern_jobs SET state='expired',reason='deadline',lease_until=NULL,
                    claim_token=NULL,worker_id=NULL,revision=revision+1 WHERE bot_id=? AND job_id=?''',
                    (claim.bot_id, claim.job_id),
                )
                return _record(self._get(db, claim.bot_id, claim.job_id))
            self._suppress(db, claim.bot_id)
            row = self._get(db, claim.bot_id, claim.job_id)
            if row['state'] != 'claimed':
                return _record(row)
            policy = db.execute('SELECT * FROM telegram_pattern_job_bots WHERE bot_id=?', (claim.bot_id,)).fetchone()
            recipient = db.execute(
                '''SELECT * FROM telegram_pattern_job_recipients
                WHERE bot_id=? AND recipient_id=?''',
                (claim.bot_id, row['recipient_id']),
            ).fetchone()
            ready_at = max(policy['next_at'], recipient['next_at'])
            if ready_at > instant:
                state, reason = (
                    ('expired', 'deadline') if ready_at >= row['deadline_at'] else ('scheduled', 'rate-limited')
                )
                db.execute(
                    '''UPDATE telegram_pattern_jobs SET state=?,reason=?,due_at=?,attempts=attempts-1,
                    worker_id=NULL,claim_token=NULL,lease_until=NULL,revision=revision+1
                    WHERE bot_id=? AND job_id=?''',
                    (state, reason, ready_at, claim.bot_id, claim.job_id),
                )
            else:
                bot_next = _later(instant, policy['bot_interval'])
                recipient_next = _later(instant, policy['recipient_interval'])
                db.execute('UPDATE telegram_pattern_job_bots SET next_at=? WHERE bot_id=?', (bot_next, claim.bot_id))
                db.execute(
                    '''UPDATE telegram_pattern_job_recipients SET next_at=?
                    WHERE bot_id=? AND recipient_id=?''',
                    (recipient_next, claim.bot_id, row['recipient_id']),
                )
                db.execute(
                    '''UPDATE telegram_pattern_jobs SET state='sending',reason=NULL,revision=revision+1
                    WHERE bot_id=? AND job_id=?''',
                    (claim.bot_id, claim.job_id),
                )
            return _record(self._get(db, claim.bot_id, claim.job_id))

    def renew(self, claim: JobClaim, *, lease_seconds: float = 30, now: float | None = None) -> JobClaim:
        instant = _now(now)
        proposed = _later(instant, _number(lease_seconds, 3600, positive=True))
        with self._transaction() as db:
            row = self._owned(db, claim, instant, ('claimed', 'sending'))
            deadline = max(row['lease_until'], proposed)
            db.execute(
                '''UPDATE telegram_pattern_jobs SET lease_until=?,revision=revision+1
                WHERE bot_id=? AND job_id=?''',
                (deadline, claim.bot_id, claim.job_id),
            )
            return JobClaim(
                claim.bot_id,
                claim.job_id,
                row['recipient_id'],
                claim.worker_id,
                claim.attempt,
                deadline,
                claim.token,
                row['payload_json'],
            )

    def cancel(self, bot_id: int, job_id: str) -> JobRecord:
        _id(bot_id)
        _key(job_id)
        with self._transaction() as db:
            row = self._get(db, bot_id, job_id)
            if row['state'] in {'scheduled', 'claimed'}:
                db.execute(
                    '''UPDATE telegram_pattern_jobs SET state='cancelled',reason='cancelled',
                    cancel_requested=1,worker_id=NULL,claim_token=NULL,lease_until=NULL,revision=revision+1
                    WHERE bot_id=? AND job_id=?''',
                    (bot_id, job_id),
                )
            elif row['state'] in {'sending', 'unknown'} and not row['cancel_requested']:
                db.execute(
                    '''UPDATE telegram_pattern_jobs SET cancel_requested=1,revision=revision+1
                    WHERE bot_id=? AND job_id=?''',
                    (bot_id, job_id),
                )
            return _record(self._get(db, bot_id, job_id))

    def finish(
        self,
        claim: JobClaim,
        *,
        outcome: JobOutcome,
        retry_after: int | None = None,
        message_id: int | None = None,
        now: float | None = None,
    ) -> JobRecord:
        if not isinstance(outcome, str) or outcome not in {'sent', 'permanent-failure', 'flood', 'unknown'}:
            raise ValidationFailure('Use a documented delivery outcome')
        if message_id is not None:
            _id(message_id)
        if message_id is not None and outcome != 'sent':
            raise ValidationFailure('Message identity requires a confirmed successful send')
        if outcome == 'flood':
            if type(retry_after) is not int or not 1 <= retry_after <= 2**31 - 1:
                raise ValidationFailure('Use a bounded confirmed flood retry_after')
        elif retry_after is not None:
            raise ValidationFailure('retry_after requires a confirmed flood rejection')
        instant = _now(now)
        with self._transaction() as db:
            row = self._owned(db, claim, instant, ('sending',))
            state = 'unknown'
            reason: str | None = 'send-outcome-unknown'
            due = row['due_at']
            if outcome == 'sent':
                state, reason = 'sent', None
            elif outcome == 'permanent-failure':
                state, reason = 'failed', 'recipient-unreachable'
                db.execute(
                    '''UPDATE telegram_pattern_job_recipients SET reachable=0
                    WHERE bot_id=? AND recipient_id=?''',
                    (claim.bot_id, row['recipient_id']),
                )
            elif outcome == 'flood':
                due = _later(instant, cast(int, retry_after))
                db.execute(
                    'UPDATE telegram_pattern_job_bots SET next_at=MAX(next_at,?) WHERE bot_id=?', (due, claim.bot_id)
                )
                db.execute(
                    '''UPDATE telegram_pattern_job_recipients SET next_at=MAX(next_at,?)
                    WHERE bot_id=? AND recipient_id=?''',
                    (due, claim.bot_id, row['recipient_id']),
                )
                if row['cancel_requested']:
                    state, reason = 'cancelled', 'cancelled'
                elif row['attempts'] >= row['max_attempts']:
                    state, reason = 'failed', 'attempts-exhausted'
                elif cast(int, retry_after) > 86400:
                    state, reason = 'failed', 'retry-window-exceeded'
                elif due >= row['deadline_at']:
                    state, reason = 'expired', 'deadline'
                else:
                    state, reason = 'scheduled', 'flood-rejected'
            db.execute(
                '''UPDATE telegram_pattern_jobs SET state=?,reason=?,due_at=?,message_id=?,
                lease_until=NULL,worker_id=NULL,claim_token=NULL,revision=revision+1
                WHERE bot_id=? AND job_id=?''',
                (state, reason, due, message_id, claim.bot_id, claim.job_id),
            )
            self._suppress(db, claim.bot_id)
            return _record(self._get(db, claim.bot_id, claim.job_id))

    def reconcile(
        self,
        bot_id: int,
        job_id: str,
        *,
        expected_revision: int,
        evidence_ref: str,
        outcome: Literal['sent', 'failed'],
        message_id: int | None = None,
    ) -> JobRecord:
        _id(bot_id)
        _key(job_id)
        _key(evidence_ref)
        if type(expected_revision) is not int or not 1 <= expected_revision <= 2**63 - 1:
            raise ValidationFailure('Use the observed job revision')
        if (
            not isinstance(outcome, str)
            or outcome not in {'sent', 'failed'}
            or (message_id is not None and outcome != 'sent')
        ):
            raise ValidationFailure('Use a reviewed terminal reconciliation outcome')
        if message_id is not None:
            _id(message_id)
        with self._transaction() as db:
            row = self._get(db, bot_id, job_id)
            if row['state'] != 'unknown' or row['revision'] != expected_revision:
                raise JobConflict('Reconciliation revision or state changed')
            db.execute(
                '''UPDATE telegram_pattern_jobs SET state=?,reason=?,message_id=?,evidence_ref=?,
                revision=revision+1 WHERE bot_id=? AND job_id=? AND revision=? AND state='unknown' ''',
                (outcome, 'reconciled-' + outcome, message_id, evidence_ref, bot_id, job_id, expected_revision),
            )
            return _record(self._get(db, bot_id, job_id))

    def get(self, bot_id: int, job_id: str) -> JobRecord | None:
        _id(bot_id)
        _key(job_id)
        db = self._connect()
        try:
            row = db.execute(
                'SELECT * FROM telegram_pattern_jobs WHERE bot_id=? AND job_id=?', (bot_id, job_id)
            ).fetchone()
            return None if row is None else _record(row)
        finally:
            db.close()

    def counts(self, bot_id: int) -> dict[JobState, int]:
        _id(bot_id)
        db = self._connect()
        try:
            result: dict[JobState, int] = {cast(JobState, state): 0 for state in _STATES}
            for row in db.execute(
                'SELECT state,COUNT(*) AS total FROM telegram_pattern_jobs WHERE bot_id=? GROUP BY state', (bot_id,)
            ):
                result[cast(JobState, row['state'])] = row['total']
            return result
        finally:
            db.close()
