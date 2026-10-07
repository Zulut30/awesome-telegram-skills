"""Internal form transitions; old MemoryStorage path remains a demonstration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from aiogram.fsm.context import FSMContext

from .fsm_storage import AtomicFSMStorage, DialogLifetime, FSMConflict, FSMSnapshot


class _DialogData(dict[str, Any]):
    snapshot: FSMSnapshot | None

    def __init__(self, values: dict[str, Any], snapshot: FSMSnapshot | None = None) -> None:
        super().__init__(deepcopy(values))
        self.snapshot = snapshot


async def _read_form(
    state: FSMContext, namespace: str, key: str, lifetime: DialogLifetime | None
) -> _DialogData | None:
    atomic = isinstance(state.storage, AtomicFSMStorage)
    if lifetime is not None and not atomic:
        raise RuntimeError('Durable dialog lifetime requires AtomicFSMStorage on the existing Dispatcher')
    if isinstance(state.storage, AtomicFSMStorage):
        snapshot = await state.storage.read_snapshot(state.key)
        current, values = snapshot.state, snapshot.data
    else:
        snapshot = None
        current, values = await state.get_state(), await state.get_data()
    if current != namespace:
        if current is None and key in values:
            raise RuntimeError('Orphan dialog data requires migration or reconciliation')
        return None
    stored = values.get(key)
    if not isinstance(stored, dict):
        raise RuntimeError('Stored dialog requires migration or reconciliation')
    return _DialogData(stored, snapshot)


async def _save_form(state: FSMContext, namespace: str, key: str, data: _DialogData) -> None:
    if isinstance(state.storage, AtomicFSMStorage):
        old = data.snapshot or await state.storage.read_snapshot(state.key)
        if old.state not in (None, namespace) or (data.snapshot is None and key in old.data):
            raise FSMConflict('Dialog changed before its initial transition')
        values = old.data
        values[key] = deepcopy(dict(data))
        data.snapshot = await state.storage.commit_snapshot(state.key, old, namespace, values)
    else:
        await state.update_data({key: deepcopy(dict(data))})
        if await state.get_state() != namespace:
            await state.set_state(namespace)


async def _clear_form(state: FSMContext, key: str, data: _DialogData | None) -> None:
    if data is None:
        return
    if isinstance(state.storage, AtomicFSMStorage):
        old = data.snapshot if data is not None else None
        old = old or await state.storage.read_snapshot(state.key)
        values = old.data
        values.pop(key, None)
        await state.storage.commit_snapshot(state.key, old, None, values)
    else:
        await state.set_state(None)
        values = await state.get_data()
        values.pop(key, None)
        await state.set_data(values)


def _lifetime_data(lifetime: DialogLifetime | None) -> dict[str, Any]:
    return {'lifetime': lifetime.start()} if lifetime is not None else {}
