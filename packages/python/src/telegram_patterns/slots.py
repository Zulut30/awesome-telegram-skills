"""File SQLite slot booking: current ACL, schedule CAS and durable receipts."""

from __future__ import annotations

import json
import math
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from itertools import islice
from pathlib import Path
from typing import Any, Callable, Iterator, Literal, Sequence

from ._shared import canonical_json, instant, micros, owned_transaction, payload_digest
from .calendar_core import TimeSlot
from .errors import ConflictFailure, InvalidType, PermissionDenied, ValidationFailure
from .sqlite_once import OnceResult, OperationConflict


def _string(value: str, maximum: int = 128) -> str:
    try:
        valid = (
            isinstance(value, str)
            and bool(value)
            and len(value.encode('utf-8')) <= maximum
            and not any(ord(c) < 32 or ord(c) == 127 for c in value)
        )
    except UnicodeError:
        valid = False
    if not valid:
        raise ValidationFailure('Use a nonempty bounded identifier without controls')
    return value


def _actor(value: int) -> int:
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise ValidationFailure('Use a verified positive actor ID')
    return value


@dataclass(frozen=True, slots=True)
class SlotSchedule:
    resource: str
    revision: int
    slots: Sequence[TimeSlot]

    def __post_init__(self) -> None:
        _string(self.resource)
        if type(self.revision) is not int or self.revision < 1 or self.revision > 2**63 - 1:
            raise ValidationFailure('Use a positive schedule revision')
        if isinstance(self.slots, (str, bytes)):
            raise InvalidType('Use TimeSlot objects')
        try:
            slots = tuple(islice(iter(self.slots), 1001))
        except TypeError:
            raise InvalidType('Use TimeSlot objects') from None
        if len(slots) > 1000 or any(not isinstance(s, TimeSlot) for s in slots):
            raise ValidationFailure('Use at most 1000 TimeSlot objects (component limit)')
        if len({s.key for s in slots}) != len(slots):
            raise ValidationFailure('Slot keys must be unique within a resource')
        object.__setattr__(self, 'slots', tuple(sorted(slots, key=lambda s: (s.start, s.key))))


@dataclass(frozen=True, slots=True)
class SlotBooking:
    booking_id: str
    resource: str
    slot_key: str
    owner_id: int
    start: datetime
    end: datetime
    status: Literal['active', 'cancelled']

    def __post_init__(self) -> None:
        _string(self.booking_id)
        _string(self.resource)
        _string(self.slot_key, 24)
        _actor(self.owner_id)
        slot = TimeSlot(self.slot_key, self.start, self.end)
        if self.status not in {'active', 'cancelled'}:
            raise ValidationFailure('Use active or cancelled booking status')
        object.__setattr__(self, 'start', slot.start)
        object.__setattr__(self, 'end', slot.end)


class SQLiteSlotStore:
    """One seat per resource interval, across processes sharing one SQLite file.

    authorize(connection, verified_actor_id, resource) must return exactly True
    using current project ACL. It runs inside the transaction BEFORE replay.
    Trusted synchronous callback only: no network or transaction control. Schema
    setup and publish are trusted host/migration operations, never user routes.
    No Telegram calls, holds, reminders, external side effects or cleanup timer.
    Host owns file/migrations/retention; use an async thread boundary and join
    writes during shutdown. An interrupted waiter may have committed: reconcile
    the same operation ID rather than create another intent.
    """

    def __init__(
        self, database: str | Path, *, authorize: Callable[[sqlite3.Connection, int, str], bool], timeout: float = 5.0
    ):
        if not isinstance(database, (str, Path)) or not str(database) or str(database) == ':memory:':
            raise ValidationFailure('Use a file database')
        if not callable(authorize):
            raise InvalidType('Supply a synchronous current-ACL callback')
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValidationFailure('Use a positive finite SQLite timeout')
        self.database, self.timeout, self.authorize = str(database), timeout, authorize

    @contextmanager
    def _transaction(self, *, write: bool = True) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=self.timeout, isolation_level=None)
        try:
            connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            connection.set_authorizer(owned_transaction)
            try:
                yield connection
            finally:
                connection.set_authorizer(None)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _guard(self, connection: sqlite3.Connection, actor_id: int, resource: str) -> None:
        if self.authorize(connection, actor_id, resource) is not True:
            raise PermissionDenied('Current resource access denied')

    def initialize(self) -> None:
        """Explicit additive prefixed schema; never reads secrets or starts a bot."""
        with self._transaction() as c:
            c.execute(
                'CREATE TABLE IF NOT EXISTS telegram_slot_schedules(resource TEXT PRIMARY KEY, revision INTEGER NOT '
                'NULL)'
            )
            c.execute('''CREATE TABLE IF NOT EXISTS telegram_time_slots(
                resource TEXT NOT NULL, slot_key TEXT NOT NULL, start_us INTEGER NOT NULL,
                end_us INTEGER NOT NULL, enabled INTEGER NOT NULL, PRIMARY KEY(resource,slot_key))''')
            c.execute('''CREATE TABLE IF NOT EXISTS telegram_slot_bookings(
                booking_id TEXT PRIMARY KEY, resource TEXT NOT NULL, slot_key TEXT NOT NULL,
                owner_id INTEGER NOT NULL, start_us INTEGER NOT NULL, end_us INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active','cancelled')))''')
            c.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS telegram_slot_active_key ON "
                "telegram_slot_bookings(resource,slot_key) WHERE status='active'"
            )
            c.execute(
                'CREATE INDEX IF NOT EXISTS telegram_slot_intervals ON '
                'telegram_slot_bookings(resource,status,start_us,end_us)'
            )
            c.execute('''CREATE TABLE IF NOT EXISTS telegram_slot_operations(
                resource TEXT NOT NULL, owner_id INTEGER NOT NULL, operation_id TEXT NOT NULL,
                payload_hash TEXT NOT NULL, result_json TEXT NOT NULL,
                PRIMARY KEY(resource,owner_id,operation_id))''')

    def publish(self, resource: str, slots: Sequence[TimeSlot], *, expected_revision: int) -> SlotSchedule:
        """Trusted schedule CAS; replacing dates never moves an existing booking."""
        if type(expected_revision) is not int or not 0 <= expected_revision < 2**63 - 1:
            raise ValidationFailure('Use the current revision, or 0 to create')
        schedule = SlotSchedule(resource, expected_revision + 1, slots)
        with self._transaction() as c:
            current = c.execute('SELECT revision FROM telegram_slot_schedules WHERE resource=?', (resource,)).fetchone()
            if (current[0] if current else 0) != expected_revision:
                raise ConflictFailure('Schedule changed')
            c.execute(
                'INSERT INTO telegram_slot_schedules VALUES(?,?) ON CONFLICT(resource) DO UPDATE SET '
                'revision=excluded.revision',
                (resource, schedule.revision),
            )
            c.execute('DELETE FROM telegram_time_slots WHERE resource=?', (resource,))
            c.executemany(
                'INSERT INTO telegram_time_slots VALUES(?,?,?,?,?)',
                [(resource, s.key, micros(s.start), micros(s.end), int(s.enabled)) for s in schedule.slots],
            )
        return schedule

    @staticmethod
    def _busy(c: sqlite3.Connection, resource: str, start: int, end: int) -> bool:
        return (
            c.execute(
                "SELECT 1 FROM telegram_slot_bookings WHERE resource=? AND status='active' AND start_us<? AND "
                "end_us>? LIMIT 1",
                (resource, end, start),
            ).fetchone()
            is not None
        )

    def schedule(self, resource: str, *, actor_id: int, now: datetime) -> SlotSchedule:
        """Current eligible snapshot; a later reserve always rechecks in a write transaction."""
        _string(resource)
        _actor(actor_id)
        current_time = micros(now)
        with self._transaction(write=False) as c:
            self._guard(c, actor_id, resource)
            revision = c.execute(
                'SELECT revision FROM telegram_slot_schedules WHERE resource=?', (resource,)
            ).fetchone()
            if revision is None:
                raise ConflictFailure('Schedule is not published')
            active_keys = {
                row[0]
                for row in c.execute(
                    "SELECT slot_key FROM telegram_slot_bookings WHERE resource=? AND status='active'", (resource,)
                )
            }
            slots = tuple(
                TimeSlot(
                    key,
                    instant(start),
                    instant(end),
                    bool(
                        enabled
                        and key not in active_keys
                        and start > current_time
                        and not self._busy(c, resource, start, end)
                    ),
                )
                for key, start, end, enabled in c.execute(
                    'SELECT slot_key,start_us,end_us,enabled FROM telegram_time_slots WHERE resource=?', (resource,)
                ).fetchall()
            )
            return SlotSchedule(resource, revision[0], slots)

    def _operation(
        self, resource: str, actor_id: int, operation_id: str, payload: Any, apply: Callable[[sqlite3.Connection], Any]
    ) -> OnceResult:
        _string(resource)
        _actor(actor_id)
        _string(operation_id, 256)
        digest = payload_digest(payload)
        with self._transaction() as c:
            self._guard(c, actor_id, resource)
            old = c.execute(
                'SELECT payload_hash,result_json FROM telegram_slot_operations WHERE resource=? AND owner_id=? AND '
                'operation_id=?',
                (resource, actor_id, operation_id),
            ).fetchone()
            if old:
                if old[0] != digest:
                    raise OperationConflict('Operation ID was reused with another payload')
                return OnceResult(json.loads(old[1]), True)
            serialized = canonical_json(apply(c))
            c.execute(
                'INSERT INTO telegram_slot_operations VALUES(?,?,?,?,?)',
                (resource, actor_id, operation_id, digest, serialized),
            )
            return OnceResult(json.loads(serialized), False)

    def reserve(
        self, resource: str, slot_key: str, *, actor_id: int, expected_revision: int, operation_id: str, now: datetime
    ) -> OnceResult:
        """Atomic current rules + overlap check + booking + immutable receipt.

        A replay returns the original receipt even after cancel/schedule changes;
        booking() returns current status. now is the trusted server clock, never
        a client value; do not include it in an idempotency payload.
        """
        _string(slot_key, 24)
        if type(expected_revision) is not int or not 1 <= expected_revision <= 2**63 - 1:
            raise ValidationFailure('Use a positive expected schedule revision')
        current_time = micros(now)

        def apply(c: sqlite3.Connection) -> dict[str, Any]:
            revision = c.execute(
                'SELECT revision FROM telegram_slot_schedules WHERE resource=?', (resource,)
            ).fetchone()
            if revision is None or revision[0] != expected_revision:
                raise ConflictFailure('Schedule changed')
            row = c.execute(
                'SELECT start_us,end_us,enabled FROM telegram_time_slots WHERE resource=? AND slot_key=?',
                (resource, slot_key),
            ).fetchone()
            if row is None or not row[2] or row[0] <= current_time:
                raise ConflictFailure('Slot is unavailable or in the past')
            if (
                self._busy(c, resource, row[0], row[1])
                or c.execute(
                    "SELECT 1 FROM telegram_slot_bookings WHERE resource=? AND slot_key=? AND status='active'",
                    (resource, slot_key),
                ).fetchone()
            ):
                raise ConflictFailure('Slot or resource interval is already booked')
            booking_id = secrets.token_hex(16)
            c.execute(
                "INSERT INTO telegram_slot_bookings VALUES(?,?,?,?,?,?,'active')",
                (booking_id, resource, slot_key, actor_id, row[0], row[1]),
            )
            return {
                'booking_id': booking_id,
                'resource': resource,
                'slot_key': slot_key,
                'owner_id': actor_id,
                'start': instant(row[0]).isoformat(),
                'end': instant(row[1]).isoformat(),
                'status': 'active',
                'schedule_revision': expected_revision,
            }

        return self._operation(
            resource,
            actor_id,
            operation_id,
            {'kind': 'reserve', 'slot_key': slot_key, 'revision': expected_revision},
            apply,
        )

    def booking(self, resource: str, booking_id: str, *, actor_id: int) -> SlotBooking | None:
        _string(resource)
        _string(booking_id)
        _actor(actor_id)
        with self._transaction(write=False) as c:
            self._guard(c, actor_id, resource)
            row = c.execute(
                'SELECT slot_key,owner_id,start_us,end_us,status FROM telegram_slot_bookings WHERE resource=? AND '
                'booking_id=?',
                (resource, booking_id),
            ).fetchone()
            if row is None:
                return None
            if row[1] != actor_id:
                raise PermissionDenied('Booking belongs to another actor')
            return SlotBooking(booking_id, resource, row[0], row[1], instant(row[2]), instant(row[3]), row[4])

    def cancel(self, resource: str, booking_id: str, *, actor_id: int, operation_id: str) -> OnceResult:
        """Owner-only cancellation and receipt in one transaction; no external calls."""
        _string(booking_id)

        def apply(c: sqlite3.Connection) -> dict[str, str]:
            row = c.execute(
                'SELECT owner_id FROM telegram_slot_bookings WHERE resource=? AND booking_id=?', (resource, booking_id)
            ).fetchone()
            if row is None or row[0] != actor_id:
                raise PermissionDenied('Booking is unavailable to this actor')
            c.execute(
                "UPDATE telegram_slot_bookings SET status='cancelled' WHERE resource=? AND booking_id=?",
                (resource, booking_id),
            )
            return {'booking_id': booking_id, 'status': 'cancelled'}

        return self._operation(resource, actor_id, operation_id, {'kind': 'cancel', 'booking_id': booking_id}, apply)
