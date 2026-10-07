# Восстановление диалога после рестарта

Термины: **CAS** — сравнение с заменой: запись сохраняется, только если версия не изменилась с момента чтения; квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта; **outbox** — события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик выполняет их позже; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

Локальная библиотека 0.24.0, optional aiogram 3.31.0. `SnapshotStore` — контракт транзакции проекта; `SnapshotFSMStorage` связывает его с BaseStorage. Если текущий storage уже работает, добавьте ему `AtomicFSMStorage.read_snapshot`/`commit_snapshot`; не меняйте Dispatcher, SDK, backend или инфраструктуру ради примера.

Каждая запись хранит **state и весь JSON data в одной revision**. Missing key = `(None, {}, 0)`; compare-and-set проверяет прежнюю revision и записывает revision+1 атомарно. Mismatch = `FSMConflict`, без записи и без автоматического retry. Используйте все поля `StorageKey`: bot_id, chat_id, user_id, thread_id, business_connection_id, destiny. Снимок отдает detached JSON data, ограниченное 64 KiB и глубиной 16; не храните credentials или бинарные файлы. Legacy host objects требуют явного project codec/migration, не молчаливой сериализации.

`DialogLifetime(seconds=3600, clock=time.time)` задает абсолютный срок черновика. Text/mixed routers с lifetime требуют atomic storage; шаг, версия формы и схемы, `created_at`, `expires_at`, ответы, выбранные кандидаты и ссылки на сообщения интерфейса и `operation_id` попадают в одну запись. `/apply` или команда смешанной формы возобновляет принятые ответы; возврат, resume и рестарт не сдвигают expires_at. `schema_version` повышается при изменении правил/валидатора; mismatched version или поврежденная запись требуют миграции либо сверки, никогда implicit reset. Формы без lifetime сохраняют прежний демонстрационный API.

Просроченный неотправленный черновик удаляется из своего FSM key при следующем update; чужие host data остаются. Это lazy application cleanup, не доказательство физического удаления из backup и не глобальная retention policy. **submission_started переживает TTL**: отмена, возврат и перезапуск команды не сбрасывают его; повторная текущая кнопка сверяет тот же operation_id через project service с ACL и durable effect dedup. После подтвержденного успеха clear идет до feedback. Исчезнувшую review-кнопку/unknown external effect восстанавливает отдельная host reconciliation, не новая заявка. Физическое удаление snapshot/revision без generation создает ABA: сохраняйте tombstone revision, миграцию и retention контролирует проект.

Сначала выберите текущие storage/isolation и границы бизнес-транзакции. Для приведенного file SQLite adapter **явно вызовите initialize как миграцию проекта**, затем передайте его в SnapshotFSMStorage при создании нового Dispatcher. При существующем Dispatcher подключите только Router и optional atomic capability его storage. SimpleEventIsolation подходит для одного процесса; CAS обнаруживает stale record, но не заменяет распределенную сериализацию updates или защиту бизнес-эффекта. Несколько workers и durable inbox/outbox имеют отдельную приемку. MemoryStorage теряет записи при рестарте и остается демонстрацией.

Пример ниже использует owned connection на каждую операцию, не получает и не коммитит host connection. BEGIN IMMEDIATE и CAS сохраняют всю запись в project database; SDK storage adapter дожидается завершения owned storage work при отмене caller, затем возвращает CancelledError. Host service on_submit проверяет текущие права и сохраняет effect/replay независимо от FSM.

```python
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
```

Приемка: локально выполните три процесса `offline_dialog_restart.py` с установленным wheel: input → resume/unknown receipt → expired pending/reconcile. Проверьте TTL обычного черновика, неизменный deadline, версию, native candidate, ошибку CAS до service, cancelled writer, чужие ключи и host data. Synthetic SDK/StubSession не подтверждает live Telegram, устройства, независимое исследование или distributed exactly-once.

Сверено 5 октября 2026: [aiogram 3.31.0 storages/BaseStorage](https://docs.aiogram.dev/en/v3.31.0/dispatcher/finite_state_machine/storages.html), установленный StorageKey и FSMContext; [SQLite transactions](https://www.sqlite.org/lang_transaction.html). Дата относится к snapshot/restart контрактам и MemoryStorage, не ко всем Telegram/payment API.
