import asyncio
import json
from typing import Any, Mapping
from aiogram.fsm.storage.base import StorageKey
from telegram_patterns.aiogram import (AtomicFSMStorage, DialogLifetime, FSMSnapshot,
    FSMConflict, SnapshotStore, SnapshotFSMStorage)


class DemonstrationStore:
    # Contract fixture only; a dict is explicitly not persistent across restart.
    def __init__(self) -> None:
        self.records: dict[StorageKey, FSMSnapshot] = {}

    async def read(self, key: StorageKey) -> FSMSnapshot:
        return self.records.get(key, FSMSnapshot(None, {}, 0))

    async def compare_and_set(self, key: StorageKey, expected_revision: int,
                              state: str | None, data: Mapping[str, Any]) -> FSMSnapshot:
        if (await self.read(key)).revision != expected_revision:
            raise FSMConflict('Stale local revision')
        result = FSMSnapshot(state, data, expected_revision + 1)
        self.records[key] = result
        return result

    async def close(self) -> None:
        pass


async def main() -> None:
    store: SnapshotStore = DemonstrationStore()
    storage = SnapshotFSMStorage(store)
    atomic: AtomicFSMStorage = storage
    key = StorageKey(bot_id=100, chat_id=42, user_id=42)
    policy = DialogLifetime(60, clock=lambda: 100.0)
    old = await atomic.read_snapshot(key)
    saved = await atomic.commit_snapshot(key, old, 'form', {'host': 'ru', 'form': {
        'step': 1, 'schema_version': 3, 'lifetime': policy.start()}})
    assert saved.revision == 1 and saved.data['form']['lifetime']['expires_at'] == 160.0
    try:
        await atomic.commit_snapshot(key, old, 'stale', {})
    except FSMConflict:
        pass
    else:
        raise AssertionError('Stale write accepted')
    assert await storage.get_state(key) == 'form' and not policy.expired(saved.data['form']['lifetime'])
    await storage.close()
    print(json.dumps({'case': 'bot_fsm_storage', 'passed': True, 'network': False}))


if __name__ == '__main__': asyncio.run(main())
