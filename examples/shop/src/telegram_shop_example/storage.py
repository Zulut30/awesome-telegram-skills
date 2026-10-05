"""File SQLite FSM and an OS-owned process lock; single process per database."""
from __future__ import annotations
import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
import sys
from pathlib import Path
import sqlite3
from typing import ParamSpec, TypeVar



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


class ProcessLock:
    def __init__(self, database: Path):
        for p in (database, *database.parents):
            if p.is_symlink() or bool(getattr(p, 'is_junction', lambda: False)()):
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
            raise RuntimeError('Another shop process owns this database') from None

    def close(self) -> None:
        self.file.close()  # OS releases the lock even after an abrupt process exit.


@contextmanager
def connection(database: Path, *, write: bool = False) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(database, timeout=1, isolation_level=None)
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
