"""Project-owned file SQLite adapter; attach the form to the existing Dispatcher."""
from __future__ import annotations

import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Awaitable, Callable, Mapping

from aiogram import Dispatcher, Router
from aiogram.fsm.storage.base import StorageKey
from telegram_patterns.aiogram import (AtomicFSMStorage, DialogLifetime, DialogSubmission,
    EmailField, FSMConflict, FSMSnapshot, NumberField, dialog_form_router)


def _linked(path: Path) -> bool:
    """Known links are refused, except root-owned aliases under / (macOS /var, /tmp -> /private/...)."""
    if not (path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())):
        return False
    try:
        return not (os.name != 'nt' and path.is_absolute() and path.parent == Path(path.anchor)
                    and path.lstat().st_uid == 0)
    except OSError:
        return True


class ProjectSnapshotStore:
    """Example adapter for the project's database, not a shared host connection.

    The caller explicitly runs initialize as its migration. Every read/write
    opens and closes an owned connection; CAS covers the whole snapshot. Keep
    tombstone revisions; no blanket TTL deletion of pending or host data.
    """
    def __init__(self, database: Path) -> None:
        supplied = database.absolute()
        if not supplied.parent.is_dir() or any(_linked(p) for p in (supplied, *supplied.parents)):
            raise ValueError('Use an explicit project database under an existing non-linked directory')
        self.database = supplied

    def initialize(self) -> None:
        with closing(sqlite3.connect(self.database, timeout=5)) as connection:
            with connection:
                connection.execute('CREATE TABLE IF NOT EXISTS dialog_snapshots ('
                    'scope TEXT PRIMARY KEY, state TEXT, data TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision > 0))')

    @staticmethod
    def scope(key: StorageKey) -> str:
        # Never omit bot, topic, Business or destiny from the host's exact key.
        return json.dumps([key.bot_id, key.chat_id, key.user_id, key.thread_id,
                           key.business_connection_id, key.destiny], ensure_ascii=False, separators=(',', ':'))

    def _read(self, key: StorageKey) -> FSMSnapshot:
        with closing(sqlite3.connect(self.database, timeout=5)) as connection:
            row = connection.execute('SELECT state, data, revision FROM dialog_snapshots WHERE scope=?',
                                     (self.scope(key),)).fetchone()
        if row is None:
            return FSMSnapshot(None, {}, 0)
        try:
            return FSMSnapshot(row[0], json.loads(row[1]), row[2])
        except (ValueError, TypeError):
            raise RuntimeError('Stored FSM snapshot requires migration or reconciliation') from None

    async def read(self, key: StorageKey) -> FSMSnapshot:
        return await asyncio.to_thread(self._read, key)

    def _commit(self, key: StorageKey, expected: int, state: str | None, data: Mapping[str, Any]) -> FSMSnapshot:
        snapshot = FSMSnapshot(state, data, expected + 1)
        encoded = json.dumps(snapshot.data, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        scope = self.scope(key)
        with closing(sqlite3.connect(self.database, timeout=5)) as connection:
            with connection:
                connection.execute('BEGIN IMMEDIATE')
                row = connection.execute('SELECT revision FROM dialog_snapshots WHERE scope=?', (scope,)).fetchone()
                current = row[0] if row else 0
                if current != expected:
                    raise FSMConflict('Stored FSM revision changed; reload before another transition')
                connection.execute('INSERT INTO dialog_snapshots(scope,state,data,revision) VALUES(?,?,?,?) '
                    'ON CONFLICT(scope) DO UPDATE SET state=excluded.state,data=excluded.data,revision=excluded.revision',
                    (scope, state, encoded, snapshot.revision))
        return snapshot

    async def compare_and_set(self, key: StorageKey, expected_revision: int,
                              state: str | None, data: Mapping[str, Any]) -> FSMSnapshot:
        return await asyncio.to_thread(self._commit, key, expected_revision, state, data)

    async def close(self) -> None:
        pass  # Per-operation connections are already closed; host DB is retained.


def attach_dialog(dispatcher: Dispatcher, on_submit: Callable[[DialogSubmission], Awaitable[str]], *,
                  lifetime: DialogLifetime | None = None, schema_version: int = 1) -> Router:
    """Retain current storage/isolation/routers; service owns ACL + durable effect."""
    if not isinstance(dispatcher.fsm.storage, AtomicFSMStorage):
        raise RuntimeError('The project must supply an AtomicFSMStorage implementation')
    router = dialog_form_router([
        EmailField('email', 'Email', 'Введите email.'),
        NumberField('seats', 'Места', 'Сколько мест?', minimum='1', maximum='10', decimal_places=0),
    ], on_submit, name='booking', command='booking', schema_version=schema_version,
       lifetime=lifetime or DialogLifetime(3600))
    dispatcher.include_router(router)
    return router
