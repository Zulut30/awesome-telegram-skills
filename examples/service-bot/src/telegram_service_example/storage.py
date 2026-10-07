"""File SQLite FSM and an OS-owned process lock; single process per database."""
from __future__ import annotations
import asyncio
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict
import json
import sys
from pathlib import Path
import sqlite3
from typing import Any, ParamSpec, TypeVar

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey


P = ParamSpec('P')
T = TypeVar('T')


async def io_call(action: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Join owned SQLite work before cancellation unwinds its process owner.

    Cancelling to_thread does not stop its thread. Shield alone also does not
    join it. Preserve caller cancellation, but wait for the local transaction
    to finish; no detached writer may survive releasing ProcessLock.
    """
    work = asyncio.create_task(asyncio.to_thread(action, *args, **kwargs))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        while not work.done():
            try:
                await asyncio.shield(work)
            except asyncio.CancelledError:
                continue  # Repeated shutdown cancellation still owns this work.
            except Exception:
                break
        if not work.cancelled():
            try:
                work.result()
            except Exception:
                pass  # Propagate caller cancellation; failed SQLite writes roll back.
        raise


def _linked(path: Path) -> bool:
    """Known links are refused, except root-owned aliases under / (macOS /var, /tmp -> /private/...)."""
    if not (path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())):
        return False
    try:
        return not (sys.platform != 'win32' and path.is_absolute() and path.parent == Path(path.anchor)
                    and path.lstat().st_uid == 0)
    except OSError:
        return True


class ProcessLock:
    def __init__(self, database: Path):
        for p in (database, *database.parents):
            if _linked(p):
                raise ValueError('Database links are not supported')
        path = database.with_name(database.name + '.lock')
        if path.is_symlink():
            raise ValueError('Lock links are not supported')
        self.file = path.open('a+b')
        try:
            if self.file.seek(0, 2) == 0:
                self.file.write(b'\0'); self.file.flush()
            self.file.seek(0)
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.file.close()
            raise RuntimeError('Another service process owns this database') from None

    def close(self) -> None:
        self.file.close()  # OS releases the lock even after an abrupt process exit.


@contextmanager
def connection(database: Path, *, write: bool = False) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(database, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        if write: db.execute('BEGIN IMMEDIATE')
        yield db
        if write: db.commit()
    except BaseException:
        if write: db.rollback()
        raise
    finally:
        db.close()


class SQLiteFSM(BaseStorage):
    """Application adapter; SimpleEventIsolation + ProcessLock own concurrency.

    State/data writes are separate SDK operations, not a workflow transaction.
    No TTL clears unknown operations. JSON/schema damage requires reconciliation.
    Connections are owned per call and run outside the async event loop.
    """
    def __init__(self, database: Path):
        self.database = database
        self.closed = False

    def key(self, key: StorageKey) -> str:
        if self.closed: raise RuntimeError('FSM is closed')
        return json.dumps(asdict(key), sort_keys=True, separators=(',', ':'))

    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        encoded = self.key(key)
        value = state.state if isinstance(state, State) else state
        if value is not None and (not isinstance(value, str) or len(value) > 256):
            raise ValueError('Invalid FSM state')
        def save():
            with connection(self.database, write=True) as db:
                db.execute("INSERT INTO service_fsm(key,state,data) VALUES (?,?,'{}') "
                           'ON CONFLICT(key) DO UPDATE SET state=excluded.state', (encoded, value))
        await io_call(save)

    async def get_state(self, key: StorageKey) -> str | None:
        encoded = self.key(key)
        def read():
            with connection(self.database) as db:
                row = db.execute('SELECT state FROM service_fsm WHERE key=?', (encoded,)).fetchone()
                return row[0] if row else None
        return await io_call(read)

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        encoded = self.key(key)
        payload = json.dumps(dict(data), ensure_ascii=True, allow_nan=False)
        if len(payload.encode()) > 16384: raise ValueError('FSM data exceeds 16 KiB')
        def save():
            with connection(self.database, write=True) as db:
                db.execute('INSERT INTO service_fsm(key,state,data) VALUES (?,NULL,?) '
                           'ON CONFLICT(key) DO UPDATE SET data=excluded.data', (encoded, payload))
        await io_call(save)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        encoded = self.key(key)
        def read():
            with connection(self.database) as db:
                row = db.execute('SELECT data FROM service_fsm WHERE key=?', (encoded,)).fetchone()
                value = json.loads(row[0]) if row else {}
                if not isinstance(value, dict): raise ValueError('FSM requires reconciliation')
                return value
        return await io_call(read)

    async def close(self) -> None:
        self.closed = True
