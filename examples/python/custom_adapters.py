"""Offline structural adapters; FixtureProvider is NOT a real payment provider."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from typing import Any, Callable, Mapping
import asyncio

from telegram_patterns import (
    AsyncTransport, OnceResult, OnceStore, OperationConflict, ProviderAdapter,
    SQLiteOnce, safe_error_report,
)


class ProjectStore:
    """Example delegates an atomic transaction to the project's SQLite store."""
    def __init__(self, database: Path) -> None: self.inner = SQLiteOnce(database)
    def initialize(self) -> None: self.inner.initialize()
    def run(self, scope: str, operation_key: str, payload: Any,
            apply: Callable[[sqlite3.Connection], Any]) -> OnceResult:
        return self.inner.run(scope, operation_key, payload, apply)


@dataclass(frozen=True)
class FixtureRequest:
    action: str
    key: str
    product: str = ''


@dataclass(frozen=True)
class FixtureInvoice:
    provider_id: str
    status: str


@dataclass(frozen=True)
class FixtureEvent:
    provider_id: str


class ProjectTransport:
    """Synthetic remote ledger: first create commits but loses its response."""
    def __init__(self) -> None:
        self.orders: dict[str, tuple[str, FixtureInvoice]] = {}
        self.calls = 0
        self.lose_response = True

    async def send(self, request: FixtureRequest) -> FixtureInvoice:
        self.calls += 1
        if request.action == 'get':
            return next(value for _, value in self.orders.values() if value.provider_id == request.key)
        if request.action != 'create': raise ValueError('Unknown fixture request')
        previous = self.orders.get(request.key)
        if previous:
            if previous[0] != request.product: raise OperationConflict('Fixture operation payload changed')
            return previous[1]
        value = FixtureInvoice(f'fixture-{len(self.orders)+1}', 'pending')
        self.orders[request.key] = request.product, value
        if self.lose_response:
            self.lose_response = False
            raise TimeoutError('Fixture response lost after remote persistence')
        return value


class FixtureProvider:
    """Invented fixture protocol; never use this signature for real providers."""
    def __init__(self, transport: AsyncTransport[FixtureRequest, FixtureInvoice], secret: bytes) -> None:
        self.transport, self.secret = transport, secret
    async def create(self, request: str, *, operation_id: str) -> FixtureInvoice:
        return await self.transport.send(FixtureRequest('create', operation_id, request))
    async def get(self, provider_id: str) -> FixtureInvoice:
        return await self.transport.send(FixtureRequest('get', provider_id))
    def verify_event(self, body: bytes, headers: Mapping[str, str]) -> FixtureEvent | None:
        if len(body) > 4096: return None
        expected = hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        candidate = headers.get('x-fixture-signature', '')
        if not re.fullmatch(r'[0-9a-f]{64}', candidate) or not hmac.compare_digest(candidate, expected): return None
        try: value = json.loads(body)
        except (ValueError, UnicodeError, RecursionError): return None
        if not isinstance(value, dict) or not isinstance(value.get('provider_id'), str): return None
        return FixtureEvent(value['provider_id'])


async def probe() -> dict[str, Any]:
    with TemporaryDirectory(prefix='telegram-adapters-') as folder:
        database = Path(folder) / 'project.sqlite'
        storage: OnceStore[sqlite3.Connection] = ProjectStore(database)
        storage.initialize()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('CREATE TABLE entries(id INTEGER PRIMARY KEY, label TEXT)')
        def effect(db: sqlite3.Connection) -> dict[str, Any]:
            return {'id': db.execute('INSERT INTO entries(label) VALUES (?)', ('fixture',)).lastrowid}
        first = storage.run('server-actor:42', 'local-operation', {'label': 'fixture'}, effect)
        replay = storage.run('server-actor:42', 'local-operation', {'label': 'fixture'}, effect)
        with closing(sqlite3.connect(database)) as db:
            effects = db.execute('SELECT COUNT(*) FROM entries').fetchone()[0]
        assert not first.replayed and replay.replayed and effects == 1

    transport = ProjectTransport()
    provider: ProviderAdapter[str, FixtureInvoice, FixtureEvent] = FixtureProvider(transport, b'fixture-only')
    key = 'server-scoped-opaque-operation'
    try: await provider.create('fixture-product', operation_id=key)
    except TimeoutError as error:
        assert safe_error_report(error, operation='write').recovery == 'reconcile'
    else: raise AssertionError('Fixture must lose its first response')
    assert transport.calls == 1 and len(transport.orders) == 1
    # Provider fixture explicitly supports SAME-key replay. The generic
    # interface does not promise that any real provider can do this.
    invoice = await provider.create('fixture-product', operation_id=key)
    assert len(transport.orders) == 1
    try: await provider.create('changed-product', operation_id=key)
    except OperationConflict: pass
    else: raise AssertionError('Payload conflict was accepted')
    body = json.dumps({'provider_id': invoice.provider_id, 'status': 'paid'}).encode()
    headers = {'x-fixture-signature': hmac.new(b'fixture-only', body, hashlib.sha256).hexdigest()}
    assert provider.verify_event(body + b' ', headers) is None
    assert provider.verify_event(body, {'x-fixture-signature':'не ASCII'}) is None
    event = provider.verify_event(body, headers)
    assert event is not None
    authoritative = await provider.get(event.provider_id)
    assert authoritative.status == 'pending'  # Signed event != entitlement grant.
    return {'passed': True, 'network': False, 'custom_storage_effects': effects,
            'remote_effects': len(transport.orders), 'automatic_retries': 0,
            'tampered_event_rejected': True, 'payment_granted': False}


if __name__ == '__main__': print(json.dumps(asyncio.run(probe())))
