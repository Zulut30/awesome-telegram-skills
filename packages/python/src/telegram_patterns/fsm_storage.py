"""Optional aiogram snapshot adapter; persistence and migrations belong to host."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import inspect
import math
import time
from typing import Any, Awaitable, Callable, Mapping, Protocol, TypeVar, runtime_checkable

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from .errors import ValidationFailure


def _json_data(data: Mapping[str, Any]) -> str:
    def check(value: Any, depth: int = 0) -> None:
        if depth > 16:
            raise ValidationFailure('FSM data exceeds JSON nesting limit')
        if isinstance(value, Mapping):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValidationFailure('FSM JSON object keys must be strings')
                check(item, depth + 1)
        elif type(value) is list:
            for item in value:
                check(item, depth + 1)
        elif type(value) not in (str, int, float, bool, type(None)):
            raise ValidationFailure('FSM data must contain plain JSON values')
        elif type(value) is float and not math.isfinite(value):
            raise ValidationFailure('FSM JSON numbers must be finite')
    if not isinstance(data, Mapping):
        raise ValidationFailure('FSM data must be a JSON object')
    check(data)
    try:
        encoded = json.dumps(dict(data), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))
        if len(encoded.encode('utf-8')) > 65536:
            raise ValueError
        return encoded
    except (TypeError, ValueError, UnicodeError, OverflowError):
        raise ValidationFailure('FSM data must be valid JSON up to 64 KiB') from None


@dataclass(frozen=True, slots=True, init=False)
class FSMSnapshot:
    """One state/data revision; data returns a detached JSON copy, repr hides it."""
    state: str | None
    revision: int
    _json: str = field(repr=False)

    def __init__(self, state: str | None, data: Mapping[str, Any], revision: int = 0) -> None:
        if state is not None and (not isinstance(state, str) or not 1 <= len(state) <= 256):
            raise ValidationFailure('Use a nonempty bounded FSM state or None')
        if type(revision) is not int or not 0 <= revision < 2**63 - 1:
            raise ValidationFailure('Use a bounded nonnegative FSM revision')
        object.__setattr__(self, 'state', state)
        object.__setattr__(self, 'revision', revision)
        object.__setattr__(self, '_json', _json_data(data))

    @property
    def data(self) -> dict[str, Any]:
        return json.loads(self._json)


class FSMConflict(RuntimeError):
    """A stale snapshot was rejected before an effect; caller reloads explicitly."""


class SnapshotStore(Protocol):
    """Host-owned durable transaction contract. Keep every StorageKey field.

    Missing keys read as FSMSnapshot(None, {}, 0). CAS must atomically compare
    revision and write state plus the complete JSON data, then return revision+1.
    A mismatch raises FSMConflict without writing. Do not physically delete or
    reset revisions (ABA); retention/migration and business effects are separate.
    close releases only resources owned by this adapter, never host connections.
    """
    async def read(self, key: StorageKey) -> FSMSnapshot: ...
    async def compare_and_set(self, key: StorageKey, expected_revision: int,
                              state: str | None, data: Mapping[str, Any]) -> FSMSnapshot: ...
    async def close(self) -> None: ...


@runtime_checkable
class AtomicFSMStorage(Protocol):
    """Optional capability for existing project BaseStorage implementations."""
    async def read_snapshot(self, key: StorageKey) -> FSMSnapshot: ...
    async def commit_snapshot(self, key: StorageKey, snapshot: FSMSnapshot,
                              state: str | None, data: Mapping[str, Any]) -> FSMSnapshot: ...


_T = TypeVar('_T')


async def _settled(work: Awaitable[_T]) -> _T:
    # An owned storage write must not outlive event isolation on caller cancel.
    task = asyncio.ensure_future(work)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise


class SnapshotFSMStorage(BaseStorage):
    """BaseStorage facade over an explicitly supplied project SnapshotStore.

    Conventional set_state/set_data each change one snapshot but two separate
    SDK calls are not one transition. Forms use commit_snapshot. No retry, new
    infrastructure, event isolation or business exactly-once guarantee is added.
    """
    def __init__(self, store: SnapshotStore) -> None:
        self.store = store

    async def read_snapshot(self, key: StorageKey) -> FSMSnapshot:
        result = await _settled(self.store.read(key))
        if not isinstance(result, FSMSnapshot):
            raise RuntimeError('SnapshotStore returned an invalid snapshot')
        return result

    async def commit_snapshot(self, key: StorageKey, snapshot: FSMSnapshot,
                              state: str | None, data: Mapping[str, Any]) -> FSMSnapshot:
        expected = FSMSnapshot(state, data, snapshot.revision + 1)
        result = await _settled(self.store.compare_and_set(key, snapshot.revision, state, expected.data))
        if result != expected:
            raise RuntimeError('SnapshotStore violated its atomic commit contract; reconcile storage')
        return result

    async def set_state(self, key: StorageKey, state: State | str | None = None) -> None:
        value = state.state if isinstance(state, State) else state
        old = await self.read_snapshot(key)
        await self.commit_snapshot(key, old, value, old.data)

    async def get_state(self, key: StorageKey) -> str | None:
        return (await self.read_snapshot(key)).state

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        old = await self.read_snapshot(key)
        await self.commit_snapshot(key, old, old.state, data)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        return (await self.read_snapshot(key)).data

    async def update_data(self, key: StorageKey, data: Mapping[str, Any]) -> dict[str, Any]:
        old = await self.read_snapshot(key)
        values = old.data
        values.update(data)
        return (await self.commit_snapshot(key, old, old.state, values)).data

    async def close(self) -> None:
        await _settled(self.store.close())


@dataclass(frozen=True, slots=True)
class DialogLifetime:
    """Absolute draft deadline; changes/resume do not extend it, pending survives."""
    seconds: int = 3600
    clock: Callable[[], float] = field(default=time.time, repr=False, compare=False)

    def __post_init__(self) -> None:
        if (type(self.seconds) is not int or not 1 <= self.seconds <= 2592000 or not callable(self.clock)
                or inspect.iscoroutinefunction(self.clock) or inspect.iscoroutinefunction(getattr(self.clock, '__call__', None))):
            raise ValidationFailure('Use a 1..2592000 second lifetime and a wall clock')

    def now(self) -> float:
        value = self.clock()
        if type(value) not in (int, float) or not 0 <= value < 2**53 or not math.isfinite(value):
            raise ValidationFailure('Dialog clock must return a finite nonnegative Unix timestamp')
        return float(value)

    def start(self) -> dict[str, float]:
        created = self.now()
        return {'created_at': created, 'expires_at': created + self.seconds}

    def expired(self, metadata: object) -> bool:
        if (not isinstance(metadata, dict) or set(metadata) != {'created_at', 'expires_at'}
                or any(type(v) not in (int, float) or not 0 <= v < 2**53 or not math.isfinite(v) for v in metadata.values())
                or not 0 < metadata['expires_at'] - metadata['created_at'] <= 2592000):
            raise RuntimeError('Stored dialog lifetime requires migration or reconciliation')
        return self.now() >= metadata['expires_at']
