"""Local financial state, explicit adapter trust and durable ambiguous operations.

No DTO authenticates a payment. The host verifier must check the selected provider's
protocol and authoritative outcome before returning an event. No provider I/O occurs
inside a ledger transaction. Call synchronous storage through a thread boundary.
"""

from __future__ import annotations

import inspect
import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Literal, cast

from ._shared import canonical_json, owned_transaction, payload_digest
from .errors import (
    ConflictFailure,
    InvalidType,
    PermissionDenied,
    UnknownOutcome,
    UnsupportedCapability,
    ValidationFailure,
)
from .money import Money
from .stars_subscription import StarsSubscription

PaymentRoute = Literal['external', 'telegram-stars']
PaymentKind = Literal['invoice', 'refund', 'cancel-renewal']
PaymentState = Literal['pending', 'sending', 'confirmed', 'failed', 'cancelled', 'unknown']
ProviderEventKind = Literal['invoice-created', 'paid', 'refunded', 'renewal-state', 'rejected', 'observed']
_KEY = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
_MAX_TIME = 253402300799


class PaymentConflict(ConflictFailure):
    """An immutable binding, receipt or revision conflicts; no new effect is permitted."""


class PaymentLeaseLost(UnknownOutcome):
    """Ownership was lost after an external effect may have started; reconcile first."""


def _key(value: str) -> None:
    if not isinstance(value, str) or _KEY.fullmatch(value) is None:
        raise ValidationFailure('Use a safe opaque identifier of at most 128 ASCII characters')


def _opaque(value: str) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 512 or any(not 33 <= ord(char) <= 126 for char in value):
        raise ValidationFailure('Use a bounded opaque ASCII provider reference')


def _id(value: int) -> None:
    if type(value) is not int or not 1 <= value <= 2**53 - 1:
        raise ValidationFailure('Use a positive exact bounded server identity')


def _integer(value: int, maximum: int = _MAX_TIME, *, positive: bool = False) -> int:
    if type(value) is not int or not (0 < value <= maximum if positive else 0 <= value <= maximum):
        raise ValidationFailure('Use an exact bounded integer')
    return value


def _now(value: int | None) -> int:
    return _integer(int(time.time()) if value is None else value)


def _sync(function: Any, *args: Any) -> Any:
    if not callable(function) or inspect.iscoroutinefunction(function) or inspect.isasyncgenfunction(function):
        raise InvalidType('Supply a synchronous trusted host callback')
    result = function(*args)
    if inspect.isawaitable(result) or inspect.isasyncgen(result):
        if inspect.iscoroutine(result):
            result.close()
        raise InvalidType('Trusted host callback must finish synchronously')
    return result


@dataclass(frozen=True, slots=True)
class PaymentBinding:
    merchant_id: str
    bot_id: int
    user_id: int
    order_id: str
    provider: str
    amount: Money
    route: PaymentRoute = 'external'
    subscription_id: str | None = None
    allow_partial_refunds: bool = False
    revoke_on_partial_refund: bool = False

    def __post_init__(self) -> None:
        for value in (self.merchant_id, self.order_id, self.provider):
            _key(value)
        _id(self.bot_id)
        _id(self.user_id)
        if not isinstance(self.amount, Money) or self.amount.minor_units <= 0:
            raise ValidationFailure('An order needs a positive exact Money amount')
        if self.route not in {'external', 'telegram-stars'}:
            raise ValidationFailure('Use an explicit supported route kind')
        if type(self.allow_partial_refunds) is not bool or type(self.revoke_on_partial_refund) is not bool:
            raise ValidationFailure('Use explicit server-owned refund policy booleans')
        if self.subscription_id is not None:
            _key(self.subscription_id)
        if self.route == 'telegram-stars':
            if self.amount.currency != 'XTR' or self.amount.exponent != 0 or self.allow_partial_refunds:
                raise ValidationFailure('Stars require whole XTR and full-charge refunds')
            if self.subscription_id is not None and self.amount.minor_units > 10000:
                raise ValidationFailure('Stars subscription price exceeds the documented route limit')
        elif self.amount.currency == 'XTR':
            raise ValidationFailure('XTR belongs to the Telegram Stars route')


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    """Host-adapter observation, not cryptographic proof or a client request DTO."""

    binding: PaymentBinding = field(repr=False)
    event_id: str = field(repr=False)
    kind: ProviderEventKind
    provider_state: str
    evidence_ref: str = field(repr=False)
    operation_id: str | None = None
    charge_id: str | None = field(default=None, repr=False)
    refund_id: str | None = field(default=None, repr=False)
    provider_ref: str | None = field(default=None, repr=False)
    amount: Money | None = None
    paid_at: int | None = None
    period_start: int | None = None
    period_end: int | None = None
    renewal: Literal['active', 'canceled', 'failed'] | None = None
    first_recurring: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.binding, PaymentBinding):
            raise InvalidType('Use a server-owned payment binding')
        _opaque(self.event_id)
        _key(self.provider_state)
        _key(self.evidence_ref)
        if self.kind not in {'invoice-created', 'paid', 'refunded', 'renewal-state', 'rejected', 'observed'}:
            raise ValidationFailure('Use a documented provider observation kind')
        for value in (self.charge_id, self.refund_id, self.provider_ref):
            if value is not None:
                _opaque(value)
        if self.operation_id is not None:
            _key(self.operation_id)
        if self.amount is not None and not isinstance(self.amount, Money):
            raise InvalidType('Use an exact Money amount')
        if type(self.first_recurring) is not bool:
            raise ValidationFailure('Use a recurring-charge boolean')
        for timestamp in (self.paid_at, self.period_start, self.period_end):
            if timestamp is not None:
                _integer(timestamp)
        if (self.period_start is None) != (self.period_end is None):
            raise ValidationFailure('Supply both authoritative period boundaries')
        if self.period_start is not None and cast(int, self.period_end) <= self.period_start:
            raise ValidationFailure('Paid periods must have positive half-open boundaries')
        if self.renewal not in {None, 'active', 'canceled', 'failed'}:
            raise ValidationFailure('Use a supported renewal observation')


@dataclass(frozen=True, slots=True)
class PaymentOperation:
    binding: PaymentBinding = field(repr=False)
    operation_id: str
    kind: PaymentKind
    state: PaymentState
    amount: Money
    actor_id: int
    revision: int
    cancel_requested: bool
    charge_id: str | None = field(repr=False)
    provider_ref: str | None = field(repr=False)
    provider_state: str | None
    evidence_ref: str | None = field(repr=False)
    lease_until: int | None


@dataclass(frozen=True, slots=True)
class PaymentClaim:
    binding: PaymentBinding = field(repr=False)
    operation_id: str
    worker_id: str
    token: str = field(repr=False)
    lease_until: int


@dataclass(frozen=True, slots=True)
class PaymentReceipt:
    kind: ProviderEventKind
    duplicate: bool
    event_id: str = field(repr=False)
    order_id: str


@dataclass(frozen=True, slots=True)
class AccessDecision:
    active: bool
    expires_at: int | None
    renewal: str | None
    reason: Literal['active', 'unpaid', 'expired-or-refunded']


@dataclass(frozen=True, slots=True)
class PaymentOrder:
    binding: PaymentBinding = field(repr=False)
    invoice_state: PaymentState
    confirmed_charges: int
    fully_refunded_charges: int
    partially_refunded_charges: int
    provider_state: str | None


PaymentCheck = Callable[[sqlite3.Connection, PaymentOperation, bool], bool]
PaymentVerifier = Callable[[Any], ProviderEvent]


class SQLitePaymentLedger:
    """File SQLite financial ledger. Authentication and route legality remain host-owned."""

    def __init__(self, database: str | Path, *, timeout: int = 5) -> None:
        if not isinstance(database, (str, Path)) or not str(database) or str(database) == ':memory:':
            raise ValidationFailure('Use a file financial database')
        self.database = str(database)
        self.timeout = _integer(timeout, 300, positive=True)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=self.timeout, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA synchronous=FULL')
        except BaseException:
            db.close()
            raise
        return db

    def _read_connection(self) -> sqlite3.Connection:
        db = self._connect()
        try:
            db.execute('BEGIN')
        except BaseException:
            db.close()
            raise
        return db

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            db.set_authorizer(owned_transaction)
            yield db
            db.set_authorizer(None)
            db.commit()
        except BaseException:
            db.set_authorizer(None)
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self) -> None:
        with self._transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS payment_ledger_meta(version INTEGER NOT NULL)')
            version = db.execute('SELECT version FROM payment_ledger_meta').fetchall()
            if version and (len(version) != 1 or version[0][0] != 1):
                raise UnsupportedCapability('Financial schema needs a reviewed migration')
            statements = [
                '''CREATE TABLE IF NOT EXISTS payment_orders(merchant TEXT,bot INTEGER,order_id TEXT,
                    provider TEXT,user_id INTEGER,subscription_id TEXT,route TEXT,binding_json TEXT NOT NULL,
                    binding_hash TEXT NOT NULL,PRIMARY KEY(merchant,bot,order_id))''',
                '''CREATE TABLE IF NOT EXISTS payment_operations(merchant TEXT,bot INTEGER,operation_id TEXT,
                    order_id TEXT NOT NULL,kind TEXT NOT NULL,charge_id TEXT,amount INTEGER NOT NULL,actor_id INTEGER,
                    state TEXT NOT NULL,revision INTEGER NOT NULL,cancel_requested INTEGER NOT NULL,
                    worker_id TEXT,token TEXT,lease_until INTEGER,provider_ref TEXT,provider_state TEXT,
                    evidence_ref TEXT,intent_hash TEXT NOT NULL,PRIMARY KEY(merchant,bot,operation_id))''',
                '''CREATE TABLE IF NOT EXISTS payment_charges(merchant TEXT,bot INTEGER,provider TEXT,charge_id TEXT,
                    order_id TEXT NOT NULL,amount INTEGER NOT NULL,paid_at INTEGER,
                    period_start INTEGER,period_end INTEGER,refunded INTEGER NOT NULL,
                    financial_hash TEXT,provider_state TEXT NOT NULL,evidence_ref TEXT NOT NULL,
                    PRIMARY KEY(merchant,bot,provider,charge_id))''',
                '''CREATE TABLE IF NOT EXISTS payment_refunds(merchant TEXT,bot INTEGER,provider TEXT,refund_id TEXT,
                    order_id TEXT NOT NULL,charge_id TEXT NOT NULL,amount INTEGER NOT NULL,operation_id TEXT,
                    financial_hash TEXT NOT NULL,PRIMARY KEY(merchant,bot,provider,refund_id))''',
                '''CREATE TABLE IF NOT EXISTS payment_subscriptions(merchant TEXT,bot INTEGER,provider TEXT,
                    subscription_id TEXT,user_id INTEGER,route TEXT,currency TEXT,exponent INTEGER,renewal TEXT,
                    stars_json TEXT,PRIMARY KEY(merchant,bot,provider,subscription_id))''',
                '''CREATE TABLE IF NOT EXISTS payment_events(merchant TEXT,bot INTEGER,provider TEXT,event_id TEXT,
                    event_hash TEXT NOT NULL,provider_state TEXT NOT NULL,evidence_ref TEXT NOT NULL,
                    PRIMARY KEY(merchant,bot,provider,event_id))''',
                '''CREATE TABLE IF NOT EXISTS payment_audit(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    merchant TEXT,bot INTEGER,order_id TEXT,operation_id TEXT,kind TEXT,outcome TEXT,
                    provider_state TEXT,evidence_ref TEXT,actor_id INTEGER,recorded_at INTEGER)''',
            ]
            for statement in statements:
                db.execute(statement)
            expected_columns = {
                'payment_orders': (
                    'merchant bot order_id provider user_id subscription_id route binding_json binding_hash'
                ),
                'payment_operations': (
                    'merchant bot operation_id order_id kind charge_id amount actor_id state revision '
                    'cancel_requested worker_id token lease_until provider_ref provider_state evidence_ref intent_hash'
                ),
                'payment_charges': (
                    'merchant bot provider charge_id order_id amount paid_at period_start period_end '
                    'refunded financial_hash provider_state evidence_ref'
                ),
                'payment_refunds': (
                    'merchant bot provider refund_id order_id charge_id amount operation_id financial_hash'
                ),
                'payment_subscriptions': (
                    'merchant bot provider subscription_id user_id route currency exponent renewal stars_json'
                ),
                'payment_events': 'merchant bot provider event_id event_hash provider_state evidence_ref',
                'payment_audit': (
                    'sequence merchant bot order_id operation_id kind outcome provider_state evidence_ref '
                    'actor_id recorded_at'
                ),
            }
            for table, columns in expected_columns.items():
                if {row['name'] for row in db.execute(f'PRAGMA table_info({table})')} != set(columns.split()):
                    raise UnsupportedCapability('Unexpected financial schema; apply a reviewed migration')
            if not version:
                db.execute('INSERT INTO payment_ledger_meta VALUES (1)')

    @staticmethod
    def _key(binding: PaymentBinding) -> tuple[str, int, str]:
        if not isinstance(binding, PaymentBinding):
            raise InvalidType('Use the immutable server-owned order binding')
        return binding.merchant_id, binding.bot_id, binding.order_id

    def _order(self, db: sqlite3.Connection, binding: PaymentBinding) -> sqlite3.Row:
        row = db.execute(
            'SELECT * FROM payment_orders WHERE merchant=? AND bot=? AND order_id=?', self._key(binding)
        ).fetchone()
        if row is None or row['binding_hash'] != payload_digest(asdict(binding)):
            raise PaymentConflict('Stored order binding differs or does not exist')
        return cast(sqlite3.Row, row)

    def _operation(self, db: sqlite3.Connection, binding: PaymentBinding, operation_id: str) -> sqlite3.Row:
        self._order(db, binding)
        _key(operation_id)
        row = db.execute(
            'SELECT * FROM payment_operations WHERE merchant=? AND bot=? AND operation_id=?',
            (binding.merchant_id, binding.bot_id, operation_id),
        ).fetchone()
        if row is None or row['order_id'] != binding.order_id:
            raise PaymentConflict('Operation does not belong to this order')
        return cast(sqlite3.Row, row)

    @staticmethod
    def _snapshot(binding: PaymentBinding, row: sqlite3.Row) -> PaymentOperation:
        return PaymentOperation(
            binding,
            row['operation_id'],
            cast(PaymentKind, row['kind']),
            cast(PaymentState, row['state']),
            Money(row['amount'], binding.amount.currency, binding.amount.exponent),
            row['actor_id'],
            row['revision'],
            bool(row['cancel_requested']),
            row['charge_id'],
            row['provider_ref'],
            row['provider_state'],
            row['evidence_ref'],
            row['lease_until'],
        )

    def _audit(
        self,
        db: sqlite3.Connection,
        binding: PaymentBinding,
        kind: str,
        outcome: str,
        instant: int,
        *,
        operation_id: str | None = None,
        provider_state: str | None = None,
        evidence_ref: str | None = None,
        actor_id: int | None = None,
    ) -> None:
        db.execute(
            '''INSERT INTO payment_audit(merchant,bot,order_id,operation_id,kind,outcome,
            provider_state,evidence_ref,actor_id,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (*self._key(binding), operation_id, kind, outcome, provider_state, evidence_ref, actor_id, instant),
        )

    @staticmethod
    def _check(db: sqlite3.Connection, check: PaymentCheck, operation: PaymentOperation, replayed: bool) -> None:
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
        db.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
        try:
            if _sync(check, db, operation, replayed) is not True:
                raise PermissionDenied('Current financial operation permission was not confirmed')
        finally:
            db.set_authorizer(owned_transaction)

    def _prepare(
        self,
        db: sqlite3.Connection,
        binding: PaymentBinding,
        operation_id: str,
        kind: PaymentKind,
        amount: Money,
        actor_id: int,
        charge_id: str | None,
        instant: int,
        check: PaymentCheck | None = None,
    ) -> PaymentOperation:
        _key(operation_id)
        _id(actor_id)
        digest = payload_digest([asdict(binding), kind, asdict(amount), actor_id, charge_id])
        old = db.execute(
            'SELECT * FROM payment_operations WHERE merchant=? AND bot=? AND operation_id=?',
            (binding.merchant_id, binding.bot_id, operation_id),
        ).fetchone()
        if old is not None:
            if old['intent_hash'] != digest or old['order_id'] != binding.order_id:
                raise PaymentConflict('Operation ID already has another canonical intent')
            result = self._snapshot(binding, old)
            if check is not None:
                self._check(db, check, result, True)
            return result
        result = PaymentOperation(
            binding, operation_id, kind, 'pending', amount, actor_id, 1, False, charge_id, None, None, None, None
        )
        if check is not None:
            self._check(db, check, result, False)
        if kind == 'refund':
            row = self._charge(db, binding, cast(str, charge_id))
            if row['paid_at'] is None:
                raise PaymentConflict('A refund request requires a confirmed payment')
            reserved = sum(
                item[0]
                for item in db.execute(
                    '''SELECT amount FROM payment_operations
                WHERE merchant=? AND bot=? AND order_id=? AND charge_id=? AND kind='refund'
                AND state IN ('pending','sending','unknown')''',
                    (*self._key(binding), charge_id),
                )
            )
            if amount.minor_units > row['amount'] - row['refunded'] - reserved:
                raise PaymentConflict('Refund exceeds paid minus refunded and reserved amounts')
        elif (
            db.execute(
                '''SELECT 1 FROM payment_operations WHERE merchant=? AND bot=? AND order_id=?
            AND kind=? AND state IN ('pending','sending','unknown','confirmed')''',
                (*self._key(binding), kind),
            ).fetchone()
            is not None
        ):
            raise PaymentConflict('Order already has an active or confirmed operation of this kind')
        db.execute(
            '''INSERT INTO payment_operations(merchant,bot,operation_id,order_id,kind,charge_id,amount,
            actor_id,state,revision,cancel_requested,intent_hash) VALUES (?,?,?,?,?,?,?,?,'pending',1,0,?)''',
            (
                binding.merchant_id,
                binding.bot_id,
                operation_id,
                binding.order_id,
                kind,
                charge_id,
                amount.minor_units,
                actor_id,
                digest,
            ),
        )
        self._audit(db, binding, kind, 'prepared', instant, operation_id=operation_id, actor_id=actor_id)
        return result

    def create_order(
        self, binding: PaymentBinding, invoice_operation_id: str, *, now: int | None = None
    ) -> PaymentOperation:
        key, instant = self._key(binding), _now(now)
        with self._transaction() as db:
            old = db.execute('SELECT 1 FROM payment_orders WHERE merchant=? AND bot=? AND order_id=?', key).fetchone()
            if old is None:
                db.execute(
                    'INSERT INTO payment_orders VALUES (?,?,?,?,?,?,?,?,?)',
                    (
                        *key,
                        binding.provider,
                        binding.user_id,
                        binding.subscription_id,
                        binding.route,
                        canonical_json(asdict(binding)),
                        payload_digest(asdict(binding)),
                    ),
                )
            self._order(db, binding)
            if binding.subscription_id is not None:
                subkey = (binding.merchant_id, binding.bot_id, binding.provider, binding.subscription_id)
                sub = db.execute(
                    '''SELECT * FROM payment_subscriptions WHERE merchant=? AND bot=?
                    AND provider=? AND subscription_id=?''',
                    subkey,
                ).fetchone()
                if sub is None:
                    stars = StarsSubscription(binding.user_id, binding.subscription_id).as_dict()
                    db.execute(
                        'INSERT INTO payment_subscriptions VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (
                            *subkey,
                            binding.user_id,
                            binding.route,
                            binding.amount.currency,
                            binding.amount.exponent,
                            'pending',
                            canonical_json(stars) if binding.route == 'telegram-stars' else None,
                        ),
                    )
                elif (sub['user_id'], sub['route'], sub['currency'], sub['exponent']) != (
                    binding.user_id,
                    binding.route,
                    binding.amount.currency,
                    binding.amount.exponent,
                ):
                    raise PaymentConflict('Subscription binding cannot move between owners or routes')
            return self._prepare(
                db, binding, invoice_operation_id, 'invoice', binding.amount, binding.user_id, None, instant
            )

    def request_refund(
        self,
        binding: PaymentBinding,
        charge_id: str,
        refund_operation_id: str,
        amount: Money,
        actor_id: int,
        *,
        check: PaymentCheck,
        now: int | None = None,
    ) -> PaymentOperation:
        self._key(binding)
        _opaque(charge_id)
        binding.amount._compatible(amount)
        if amount.minor_units <= 0 or (not binding.allow_partial_refunds and amount != binding.amount):
            raise ValidationFailure('This route requires a full charge or a positive supported partial refund')
        with self._transaction() as db:
            self._order(db, binding)
            return self._prepare(
                db, binding, refund_operation_id, 'refund', amount, actor_id, charge_id, _now(now), check
            )

    def request_cancel_renewal(
        self, binding: PaymentBinding, operation_id: str, actor_id: int, *, check: PaymentCheck, now: int | None = None
    ) -> PaymentOperation:
        if binding.subscription_id is None:
            raise ValidationFailure('Renewal cancellation requires a bound subscription')
        with self._transaction() as db:
            self._order(db, binding)
            return self._prepare(
                db,
                binding,
                operation_id,
                'cancel-renewal',
                Money(0, binding.amount.currency, binding.amount.exponent),
                actor_id,
                None,
                _now(now),
                check,
            )

    def start_operation(
        self,
        binding: PaymentBinding,
        operation_id: str,
        worker_id: str,
        *,
        check: PaymentCheck,
        lease_seconds: int = 30,
        now: int | None = None,
    ) -> PaymentClaim:
        _key(worker_id)
        instant = _now(now)
        deadline = _integer(instant + _integer(lease_seconds, 3600, positive=True))
        with self._transaction() as db:
            row = self._operation(db, binding, operation_id)
            self._check(db, check, self._snapshot(binding, row), row['state'] != 'pending')
            if row['state'] != 'pending':
                raise PaymentLeaseLost('Operation is not an unstarted pending intent')
            if row['kind'] == 'refund':
                charge = self._charge(db, binding, row['charge_id'])
                reserved = sum(
                    item[0]
                    for item in db.execute(
                        '''SELECT amount FROM payment_operations
                    WHERE merchant=? AND bot=? AND order_id=? AND charge_id=? AND kind='refund'
                    AND state IN ('pending','sending','unknown')''',
                        (*self._key(binding), row['charge_id']),
                    )
                )
                if charge['paid_at'] is None or reserved > charge['amount'] - charge['refunded']:
                    raise PaymentConflict('Reserved refund budget is no longer available')
            token = uuid.uuid4().hex
            db.execute(
                '''UPDATE payment_operations SET state='sending',worker_id=?,token=?,lease_until=?,
                revision=revision+1 WHERE merchant=? AND bot=? AND operation_id=?''',
                (worker_id, token, deadline, binding.merchant_id, binding.bot_id, operation_id),
            )
            self._audit(
                db, binding, row['kind'], 'started', instant, operation_id=operation_id, actor_id=row['actor_id']
            )
            return PaymentClaim(binding, operation_id, worker_id, token, deadline)

    def mark_unknown(self, claim: PaymentClaim, *, now: int | None = None) -> PaymentOperation:
        if not isinstance(claim, PaymentClaim):
            raise InvalidType('Use the issued payment claim')
        instant = _now(now)
        with self._transaction() as db:
            row = self._operation(db, claim.binding, claim.operation_id)
            if (
                row['state'] != 'sending'
                or row['token'] != claim.token
                or row['worker_id'] != claim.worker_id
                or row['lease_until'] <= instant
            ):
                raise PaymentLeaseLost('Financial operation is no longer owned')
            db.execute(
                '''UPDATE payment_operations SET state='unknown',lease_until=NULL,token=NULL,
                revision=revision+1 WHERE merchant=? AND bot=? AND operation_id=?''',
                (claim.binding.merchant_id, claim.binding.bot_id, claim.operation_id),
            )
            self._audit(db, claim.binding, row['kind'], 'unknown', instant, operation_id=claim.operation_id)
            return self._snapshot(claim.binding, self._operation(db, claim.binding, claim.operation_id))

    def recover_expired(self, binding: PaymentBinding, *, now: int | None = None) -> int:
        instant = _now(now)
        with self._transaction() as db:
            self._order(db, binding)
            rows = db.execute(
                '''SELECT * FROM payment_operations WHERE merchant=? AND bot=? AND order_id=?
                AND state='sending' AND lease_until<=?''',
                (*self._key(binding), instant),
            ).fetchall()
            for row in rows:
                db.execute(
                    '''UPDATE payment_operations SET state='unknown',lease_until=NULL,token=NULL,
                    revision=revision+1 WHERE merchant=? AND bot=? AND operation_id=?''',
                    (binding.merchant_id, binding.bot_id, row['operation_id']),
                )
                self._audit(db, binding, row['kind'], 'unknown', instant, operation_id=row['operation_id'])
            return len(rows)

    def cancel_operation(
        self, binding: PaymentBinding, operation_id: str, actor_id: int, *, check: PaymentCheck, now: int | None = None
    ) -> PaymentOperation:
        _id(actor_id)
        with self._transaction() as db:
            row = self._operation(db, binding, operation_id)
            self._check(db, check, self._snapshot(binding, row), True)
            state = 'cancelled' if row['state'] == 'pending' else row['state']
            if row['state'] in {'pending', 'sending', 'unknown'} and not row['cancel_requested']:
                db.execute(
                    '''UPDATE payment_operations SET state=?,cancel_requested=1,revision=revision+1
                    WHERE merchant=? AND bot=? AND operation_id=?''',
                    (state, binding.merchant_id, binding.bot_id, operation_id),
                )
                self._audit(
                    db,
                    binding,
                    row['kind'],
                    'cancel-requested',
                    _now(now),
                    operation_id=operation_id,
                    actor_id=actor_id,
                )
            return self._snapshot(binding, self._operation(db, binding, operation_id))

    def _charge(self, db: sqlite3.Connection, binding: PaymentBinding, charge_id: str) -> sqlite3.Row:
        row = db.execute(
            '''SELECT * FROM payment_charges WHERE merchant=? AND bot=? AND provider=? AND charge_id=?''',
            (binding.merchant_id, binding.bot_id, binding.provider, charge_id),
        ).fetchone()
        if row is None or row['order_id'] != binding.order_id:
            raise PaymentConflict('Charge does not belong to the stored order')
        return cast(sqlite3.Row, row)

    @staticmethod
    def _verified(raw: Any, verify: PaymentVerifier) -> ProviderEvent:
        event = _sync(verify, raw)
        if not isinstance(event, ProviderEvent):
            raise InvalidType('Host verifier must return a validated provider observation')
        return event

    def _sub(self, db: sqlite3.Connection, binding: PaymentBinding) -> sqlite3.Row:
        row = db.execute(
            '''SELECT * FROM payment_subscriptions WHERE merchant=? AND bot=? AND provider=?
            AND subscription_id=?''',
            (binding.merchant_id, binding.bot_id, binding.provider, binding.subscription_id),
        ).fetchone()
        if row is None:
            raise PaymentConflict('Subscription does not exist in this binding')
        return cast(sqlite3.Row, row)

    def _stars(self, db: sqlite3.Connection, event: ProviderEvent) -> None:
        binding = event.binding
        if binding.subscription_id is None or binding.route != 'telegram-stars':
            return
        subscription = StarsSubscription.from_dict(json.loads(self._sub(db, binding)['stars_json']))
        if event.kind == 'paid':
            subscription = subscription.record_payment(
                {
                    'invoice_payload': binding.subscription_id,
                    'currency': 'XTR',
                    'is_recurring': True,
                    'telegram_payment_charge_id': event.charge_id,
                    'total_amount': cast(Money, event.amount).minor_units,
                    'subscription_expiration_date': event.period_end,
                    'is_first_recurring': event.first_recurring,
                },
                user_id=binding.user_id,
                paid_at=cast(int, event.paid_at),
            )
        elif event.kind == 'refunded':
            subscription = subscription.record_refund(
                {
                    'invoice_payload': binding.subscription_id,
                    'currency': 'XTR',
                    'telegram_payment_charge_id': event.charge_id,
                },
                user_id=binding.user_id,
            )
        elif event.kind == 'renewal-state':
            subscription = subscription.record_update(
                {'user': {'id': binding.user_id}, 'invoice_payload': binding.subscription_id, 'state': event.renewal}
            )
        db.execute(
            '''UPDATE payment_subscriptions SET stars_json=?,renewal=? WHERE merchant=? AND bot=?
            AND provider=? AND subscription_id=?''',
            (
                canonical_json(subscription.as_dict()),
                subscription.renewal,
                binding.merchant_id,
                binding.bot_id,
                binding.provider,
                binding.subscription_id,
            ),
        )

    def _settle(self, db: sqlite3.Connection, event: ProviderEvent, kind: PaymentKind) -> None:
        if event.operation_id is None:
            if kind in {'invoice', 'cancel-renewal'}:
                raise ValidationFailure('Operation result requires its stable operation ID')
            return
        row = self._operation(db, event.binding, event.operation_id)
        if row['kind'] != kind or (
            kind == 'refund'
            and event.kind == 'refunded'
            and (row['charge_id'] != event.charge_id or row['amount'] != cast(Money, event.amount).minor_units)
        ):
            raise PaymentConflict('Provider result does not match the prepared financial operation')
        state = 'failed' if event.kind == 'rejected' else 'confirmed'
        if row['state'] == 'confirmed' and state == 'failed':
            raise PaymentConflict('A confirmed operation cannot become a provider rejection')
        provider_ref = event.refund_id if kind == 'refund' and state == 'confirmed' else event.provider_ref
        if row['state'] == 'confirmed' and row['provider_ref'] != provider_ref:
            raise PaymentConflict('Operation already has a different native result identity')
        db.execute(
            '''UPDATE payment_operations SET state=?,provider_ref=?,provider_state=?,evidence_ref=?,
            token=NULL,lease_until=NULL,revision=revision+1 WHERE merchant=? AND bot=? AND operation_id=?''',
            (
                state,
                provider_ref,
                event.provider_state,
                event.evidence_ref,
                event.binding.merchant_id,
                event.binding.bot_id,
                event.operation_id,
            ),
        )

    def _apply(self, db: sqlite3.Connection, event: ProviderEvent) -> None:
        b = event.binding
        self._order(db, b)
        if event.kind in {'paid', 'refunded'}:
            if event.amount is None or event.amount.minor_units <= 0 or event.charge_id is None:
                raise ValidationFailure('Financial receipt requires positive Money and a scoped charge ID')
            b.amount._compatible(event.amount)
            if event.amount.minor_units > b.amount.minor_units:
                raise PaymentConflict('Financial receipt exceeds the immutable order amount')
            existing = db.execute(
                '''SELECT * FROM payment_charges WHERE merchant=? AND bot=? AND provider=?
                AND charge_id=?''',
                (b.merchant_id, b.bot_id, b.provider, event.charge_id),
            ).fetchone()
            if existing is not None and existing['order_id'] != b.order_id:
                raise PaymentConflict('Charge identity already belongs to another order')
            if existing is None:
                db.execute(
                    '''INSERT INTO payment_charges VALUES (?,?,?,?,?,?,NULL,NULL,NULL,0,NULL,?,?)''',
                    (
                        b.merchant_id,
                        b.bot_id,
                        b.provider,
                        event.charge_id,
                        b.order_id,
                        b.amount.minor_units,
                        event.provider_state,
                        event.evidence_ref,
                    ),
                )
            row = self._charge(db, b, event.charge_id)
            if event.kind == 'paid':
                if event.amount != b.amount or event.paid_at is None or event.paid_at <= 0:
                    raise PaymentConflict('Paid receipt must match the server price and authoritative payment time')
                if b.subscription_id is not None:
                    if event.period_start is None or event.period_end is None:
                        raise ValidationFailure('Subscription payment requires authoritative per-charge boundaries')
                    if b.route == 'telegram-stars' and event.period_start != event.paid_at:
                        raise PaymentConflict('Stars paid period starts at its authoritative payment timestamp')
                elif event.period_start is not None or event.first_recurring:
                    raise PaymentConflict('One-time order cannot acquire a subscription period')
                digest = payload_digest(
                    [
                        asdict(b),
                        event.charge_id,
                        event.paid_at,
                        event.period_start,
                        event.period_end,
                        event.first_recurring,
                    ]
                )
                if row['financial_hash'] is not None and row['financial_hash'] != digest:
                    raise PaymentConflict('Charge identity has conflicting payment data')
                if (
                    b.subscription_id is None
                    and db.execute(
                        '''SELECT 1 FROM payment_charges
                    WHERE merchant=? AND bot=? AND order_id=? AND paid_at IS NOT NULL AND charge_id!=?''',
                        (*self._key(b), event.charge_id),
                    ).fetchone()
                    is not None
                ):
                    raise PaymentConflict('One-time order already has a different confirmed charge')
                db.execute(
                    '''UPDATE payment_charges SET paid_at=?,period_start=?,period_end=?,financial_hash=?,
                    provider_state=?,evidence_ref=? WHERE merchant=? AND bot=? AND provider=? AND charge_id=?''',
                    (
                        event.paid_at,
                        event.period_start,
                        event.period_end,
                        digest,
                        event.provider_state,
                        event.evidence_ref,
                        b.merchant_id,
                        b.bot_id,
                        b.provider,
                        event.charge_id,
                    ),
                )
            else:
                if event.refund_id is None:
                    raise ValidationFailure('Refund confirmation requires a stable native refund identity')
                if not b.allow_partial_refunds and event.amount != b.amount:
                    raise PaymentConflict('This route supports only a full-charge refund')
                digest = payload_digest([asdict(b), event.charge_id, asdict(event.amount)])
                refund = db.execute(
                    '''SELECT * FROM payment_refunds WHERE merchant=? AND bot=? AND provider=?
                    AND refund_id=?''',
                    (b.merchant_id, b.bot_id, b.provider, event.refund_id),
                ).fetchone()
                if refund is not None:
                    if refund['financial_hash'] != digest or (
                        refund['operation_id'] is not None
                        and event.operation_id is not None
                        and refund['operation_id'] != event.operation_id
                    ):
                        raise PaymentConflict('Native refund receipt conflicts with its stored financial intent')
                    if event.operation_id is not None and refund['operation_id'] is None:
                        db.execute(
                            '''UPDATE payment_refunds SET operation_id=? WHERE merchant=? AND bot=?
                            AND provider=? AND refund_id=?''',
                            (event.operation_id, b.merchant_id, b.bot_id, b.provider, event.refund_id),
                        )
                else:
                    if event.amount.minor_units > row['amount'] - row['refunded']:
                        raise PaymentConflict('Confirmed refund exceeds the stored charge balance')
                    db.execute(
                        'INSERT INTO payment_refunds VALUES (?,?,?,?,?,?,?,?,?)',
                        (
                            b.merchant_id,
                            b.bot_id,
                            b.provider,
                            event.refund_id,
                            b.order_id,
                            event.charge_id,
                            event.amount.minor_units,
                            event.operation_id,
                            digest,
                        ),
                    )
                    db.execute(
                        '''UPDATE payment_charges SET refunded=refunded+?,provider_state=?,evidence_ref=?
                        WHERE merchant=? AND bot=? AND provider=? AND charge_id=?''',
                        (
                            event.amount.minor_units,
                            event.provider_state,
                            event.evidence_ref,
                            b.merchant_id,
                            b.bot_id,
                            b.provider,
                            event.charge_id,
                        ),
                    )
                self._settle(db, event, 'refund')
            self._stars(db, event)
        elif event.kind == 'invoice-created':
            if event.provider_ref is None:
                raise ValidationFailure('Confirmed invoice creation requires a native provider reference')
            self._settle(db, event, 'invoice')
        elif event.kind == 'rejected':
            if event.operation_id is None:
                raise ValidationFailure('Authoritative rejection requires the operation ID')
            self._settle(db, event, cast(PaymentKind, self._operation(db, b, event.operation_id)['kind']))
        elif event.kind == 'renewal-state':
            if b.subscription_id is None or event.renewal is None:
                raise ValidationFailure('Renewal state requires the bound subscription and explicit state')
            if event.operation_id is not None:
                if event.renewal != 'canceled':
                    raise PaymentConflict('Cancellation receipt must confirm cancellation of renewal')
                self._settle(db, event, 'cancel-renewal')
            self._sub(db, b)
            db.execute(
                '''UPDATE payment_subscriptions SET renewal=? WHERE merchant=? AND bot=? AND provider=?
                AND subscription_id=?''',
                (event.renewal, b.merchant_id, b.bot_id, b.provider, b.subscription_id),
            )
            self._stars(db, event)

    def _accept(self, event: ProviderEvent, instant: int, *, expected_revision: int | None = None) -> PaymentReceipt:
        b = event.binding
        data = asdict(event)
        del data['evidence_ref']  # A fresh verification reference does not create a second financial effect.
        digest = payload_digest(data)
        failure: Exception | None = None
        duplicate = False
        with self._transaction() as db:
            self._order(db, b)
            if expected_revision is not None:
                if event.operation_id is None:
                    raise ValidationFailure('Reconciliation requires the original operation ID')
                op = self._operation(db, b, event.operation_id)
                if op['state'] != 'unknown' or op['revision'] != expected_revision:
                    raise PaymentConflict('Reconciliation state or revision changed')
            db.execute('SAVEPOINT provider_observation')
            try:
                old = db.execute(
                    '''SELECT event_hash FROM payment_events WHERE merchant=? AND bot=? AND provider=?
                    AND event_id=?''',
                    (b.merchant_id, b.bot_id, b.provider, event.event_id),
                ).fetchone()
                if old is not None:
                    if old['event_hash'] != digest:
                        raise PaymentConflict('Provider event identity has conflicting contents')
                    duplicate = True
                else:
                    self._apply(db, event)
                    db.execute(
                        'INSERT INTO payment_events VALUES (?,?,?,?,?,?,?)',
                        (
                            b.merchant_id,
                            b.bot_id,
                            b.provider,
                            event.event_id,
                            digest,
                            event.provider_state,
                            event.evidence_ref,
                        ),
                    )
            except (PaymentConflict, ValidationFailure) as error:
                db.execute('ROLLBACK TO provider_observation')
                failure = error
            finally:
                db.execute('RELEASE provider_observation')
            self._audit(
                db,
                b,
                event.kind,
                'rejected' if failure else 'duplicate' if duplicate else 'accepted',
                instant,
                operation_id=event.operation_id,
                provider_state=event.provider_state,
                evidence_ref=event.evidence_ref,
            )
        if failure is not None:
            raise failure
        return PaymentReceipt(event.kind, duplicate, event.event_id, b.order_id)

    def apply_event(self, raw: Any, *, verify: PaymentVerifier, now: int | None = None) -> PaymentReceipt:
        """ALWAYS verify outside SQLite; a constructed ProviderEvent is never accepted by itself."""
        event = self._verified(raw, verify)
        return self._accept(event, _now(now))

    def reconcile_operation(
        self, raw: Any, *, verify: PaymentVerifier, expected_revision: int, now: int | None = None
    ) -> PaymentReceipt:
        event = self._verified(raw, verify)
        _integer(expected_revision, 2**63 - 1, positive=True)
        if event.kind not in {'invoice-created', 'refunded', 'renewal-state', 'rejected'}:
            raise ValidationFailure('Reconciliation needs an authoritative terminal operation observation')
        return self._accept(event, _now(now), expected_revision=expected_revision)

    def get_operation(self, binding: PaymentBinding, operation_id: str) -> PaymentOperation:
        db = self._read_connection()
        try:
            return self._snapshot(binding, self._operation(db, binding, operation_id))
        finally:
            db.close()

    def get_order(self, binding: PaymentBinding) -> PaymentOrder:
        db = self._read_connection()
        try:
            self._order(db, binding)
            charges = db.execute(
                '''SELECT amount,refunded FROM payment_charges
                WHERE merchant=? AND bot=? AND order_id=? AND paid_at IS NOT NULL''',
                self._key(binding),
            ).fetchall()
            invoice = db.execute(
                '''SELECT state FROM payment_operations WHERE merchant=? AND bot=? AND order_id=?
                AND kind='invoice' ORDER BY rowid DESC LIMIT 1''',
                self._key(binding),
            ).fetchone()
            provider = db.execute(
                '''SELECT provider_state FROM payment_audit WHERE merchant=? AND bot=? AND order_id=?
                AND outcome IN ('accepted','duplicate') AND provider_state IS NOT NULL
                ORDER BY sequence DESC LIMIT 1''',
                self._key(binding),
            ).fetchone()
            return PaymentOrder(
                binding,
                cast(PaymentState, invoice['state']),
                len(charges),
                sum(row['refunded'] == row['amount'] for row in charges),
                sum(0 < row['refunded'] < row['amount'] for row in charges),
                None if provider is None else provider[0],
            )
        finally:
            db.close()

    def get_charge(self, binding: PaymentBinding, charge_id: str) -> dict[str, Any]:
        _opaque(charge_id)
        db = self._read_connection()
        try:
            self._order(db, binding)
            row = self._charge(db, binding, charge_id)
            reserved = sum(
                item[0]
                for item in db.execute(
                    '''SELECT amount FROM payment_operations
                WHERE merchant=? AND bot=? AND order_id=? AND charge_id=? AND kind='refund'
                AND state IN ('pending','sending','unknown')''',
                    (*self._key(binding), charge_id),
                )
            )
            return {
                'paid': row['paid_at'] is not None,
                'amount': binding.amount,
                'refunded': Money(row['refunded'], binding.amount.currency, binding.amount.exponent),
                'reserved': Money(reserved, binding.amount.currency, binding.amount.exponent),
                'provider_state': row['provider_state'],
                'evidence_ref': row['evidence_ref'],
            }
        finally:
            db.close()

    def has_access(self, binding: PaymentBinding, *, now: int | None = None) -> AccessDecision:
        instant = _now(now)
        db = self._read_connection()
        try:
            self._order(db, binding)
            renewal = None
            if binding.subscription_id is not None:
                sub = self._sub(db, binding)
                renewal = sub['renewal']
                if binding.route == 'telegram-stars':
                    stars = StarsSubscription.from_dict(json.loads(sub['stars_json']))
                    active = stars.has_access(instant)
                    return AccessDecision(
                        active, stars.access_until(instant), renewal, 'active' if active else 'expired-or-refunded'
                    )
            rows = db.execute(
                '''SELECT c.*,o.binding_json FROM payment_charges c JOIN payment_orders o
                ON o.merchant=c.merchant AND o.bot=c.bot AND o.order_id=c.order_id
                WHERE o.merchant=? AND o.bot=? AND o.provider=? AND o.user_id=?
                AND (o.order_id=? OR (? IS NOT NULL AND o.subscription_id=?))''',
                (
                    binding.merchant_id,
                    binding.bot_id,
                    binding.provider,
                    binding.user_id,
                    binding.order_id,
                    binding.subscription_id,
                    binding.subscription_id,
                ),
            ).fetchall()
            periods = []
            for row in rows:
                if row['paid_at'] is None or row['paid_at'] > instant or row['refunded'] >= row['amount']:
                    continue
                if row['refunded'] and json.loads(row['binding_json'])['revoke_on_partial_refund']:
                    continue
                if binding.subscription_id is None:
                    return AccessDecision(True, None, None, 'active')
                periods.append((row['period_start'], row['period_end']))
            ends = [end for start, end in periods if start <= instant < end]
            if not ends:
                return AccessDecision(False, None, renewal, 'expired-or-refunded' if rows else 'unpaid')
            end = max(ends)
            while any(start <= end < later for start, later in periods):
                end = max(later for start, later in periods if start <= end < later)
            return AccessDecision(True, end, renewal, 'active')
        finally:
            db.close()

    def audit(self, binding: PaymentBinding, *, after: int = 0, limit: int = 100) -> tuple[dict[str, Any], ...]:
        _integer(after, 2**63 - 1)
        _integer(limit, 1000, positive=True)
        db = self._read_connection()
        try:
            self._order(db, binding)
            return tuple(
                dict(row)
                for row in db.execute(
                    '''SELECT * FROM payment_audit WHERE merchant=? AND bot=?
                AND order_id=? AND sequence>? ORDER BY sequence LIMIT ?''',
                    (*self._key(binding), after, limit),
                )
            )
        finally:
            db.close()
