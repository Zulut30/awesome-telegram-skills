# Действия при повторе и нескольких workers

Локальная библиотека 0.25.0, optional aiogram 3.31.0. `SQLiteOnce.run_guarded(scope, operation_key, payload, apply, check=...)` сохраняет effect и receipt в одной транзакции и проверяет текущие права в этой же транзакции. `GuardedOnceStore[Transaction]` задает optional контракт backend проекта; старый `OnceStore`/`run` сохраняется. При существующей БД/SDK/Dispatcher подключите эквивалентную текущую transaction capability и Router; не меняйте инфраструктуру ради SQLite-примера. Сам интерфейс не доказывает atomicity адаптера: проект проверяет isolation, uniqueness, rollback и ACL конкурентными испытаниями своей БД.

`check(connection, replayed)` синхронный, возвращает ровно True; SQLite adapter разрешает в check только чтение и запрещает DML, transaction control, PRAGMA, ATTACH и savepoints. `apply` меняет только переданный owned connection; COMMIT/ROLLBACK/executescript запрещены. Trusted Python callbacks не sandbox: они не должны выключать authorizer, запускать сеть или писать в другой backend. Schema/migration принадлежат host и вызываются явно вне callback.

Автор, bot/chat/topic/message и resource связываются с intent на сервере. Callback содержит только непрозрачный серверный operation ID, без доверия к client revision/target/actor. Native origin получают только из **аутентифицированного Update**, не из ручного DTO или произвольного webhook JSON. Parsed SDK объект сам по себе не подтверждает источник. Пример работает с доступными обычными bot messages в private/group/supergroup, включая явно совпадающий topic. Inline/inaccessible/date=0, Business, channel, sender_chat и bot actors отклоняются. Наличие native модели не подтверждает права бота в настоящем чате.

`issue` — явная авторизованная host операция для **уже известного доставленного message_id**. Unknown initial send требует отдельной сверки, не автоматической повторной отправки/нового intent. В транзакции исполнения повторно читаются immutable intent, текущий ACL и domain revision. Для нового эффекта revision должна совпасть; при replay перепроверяются origin/ACL, а receipt относится к исходной операции и не объявляется текущим состоянием ресурса. Измененный payload/intent, чужой автор/scope или отозванное право не возвращают сохраненный результат.

После неизвестного feedback или отмены waiter используйте тот же intent и operation ID. Helper дожидается owned thread work при отмене, прежде чем передать CancelledError. Два процесса на одном локальном SQLite file дают один effect/receipt; это не distributed event isolation всех Updates, не durable inbox/outbox и не remote exactly-once. HTTP/платежи/другие connections не входят в эту atomicity. Храните intents/receipts/generations и revision без reset/reuse; cleanup, миграции и retention регулирует проект. Пример не назначает автоматический TTL.

Полная самостоятельная композиция ниже: `initialize` только явная миграция; существующий Dispatcher сохраняется. Host публикует resource и актуальный ACL своей миграцией/сервисом, вызывает `issue` после известного message receipt и показывает `action_button`. `notify` выбирает безопасный канал ответа; ACK до записи не является успехом. Текст формы/feedback остается обычным читаемым UTF-8.

```python
"""Bind an opaque button to a persistent host intent and a guarded transaction."""
from __future__ import annotations

import asyncio
from contextlib import closing
from dataclasses import dataclass
from functools import partial
import json
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Any, Awaitable, Callable

from aiogram import Dispatcher, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from telegram_patterns import ConflictFailure, OnceResult, PermissionDenied, SQLiteOnce, ValidationFailure
from telegram_patterns.aiogram import ActionResult

_OPERATION = re.compile(r'[0-9a-f]{32}')


@dataclass(frozen=True, slots=True)
class ActionOrigin:
    """Host binding, not identity proof; populate only from authenticated Update."""
    bot_id: int
    chat_id: int
    actor_id: int
    message_id: int
    thread_id: int | None = None

    def __post_init__(self) -> None:
        if any(type(v) is not int or not 0 < v < 2**63 for v in
               (self.bot_id,self.actor_id,self.message_id)):
            raise ValidationFailure('Use verified positive bot, actor and message IDs')
        if type(self.chat_id) is not int or not -(2**63) < self.chat_id < 2**63 or self.chat_id == 0:
            raise ValidationFailure('Use a verified nonzero chat ID')
        if self.thread_id is not None and (type(self.thread_id) is not int or not 0 < self.thread_id < 2**63):
            raise ValidationFailure('Use the actual positive topic ID or None')

    def scope(self) -> str:
        return json.dumps(['action-v1',self.bot_id,self.chat_id,self.actor_id,
                           self.message_id,self.thread_id],separators=(',',':'))


def callback_origin(query: CallbackQuery) -> ActionOrigin:
    message = query.message
    if (not isinstance(message,Message) or message.date.timestamp() <= 0 or query.from_user.is_bot
            or message.business_connection_id is not None or message.sender_chat is not None
            or message.chat.type not in {'private','group','supergroup'}
            or message.from_user is None or message.from_user.id != query.bot.id
            or (message.message_thread_id is not None and message.is_topic_message is not True)
            or (message.is_topic_message is True and message.message_thread_id is None)):
        raise PermissionDenied('Use an accessible ordinary bot message in its actual topic')
    return ActionOrigin(query.bot.id,message.chat.id,query.from_user.id,
                        message.message_id,message.message_thread_id)


async def database_call(function: Callable[..., Any], *args: Any) -> Any:
    """Join owned work on cancellation; preserve the operation ID for recovery."""
    work = asyncio.create_task(asyncio.to_thread(partial(function,*args)))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        while not work.done():
            try:
                await asyncio.shield(work)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not work.cancelled():
            work.exception()
        raise


class ProjectActions:
    """Example for the project's file SQLite; no borrowed host connections.

    Explicit initialize/migrations and authenticated issue belong to the host.
    Intents and receipts are retained; no automatic expiry, deletion or retry.
    ACL, immutable intent, domain revision, effect and receipt share one writer
    transaction. Only effects on its supplied connection are covered.
    """
    def __init__(self,database: Path) -> None:
        self.database = database
        self.once = SQLiteOnce(database)

    def initialize(self) -> None:
        self.once.initialize()
        with closing(sqlite3.connect(self.database,timeout=5)) as c,c:
            c.execute("CREATE TABLE IF NOT EXISTS project_resources(resource TEXT PRIMARY KEY,value INTEGER NOT NULL CHECK(typeof(value)='integer' AND value BETWEEN 0 AND 1000),revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision BETWEEN 1 AND 9223372036854775807))")
            c.execute('CREATE TABLE IF NOT EXISTS project_action_acl(resource TEXT,bot INTEGER,chat INTEGER,actor INTEGER,allowed INTEGER NOT NULL,PRIMARY KEY(resource,bot,chat,actor))')
            c.execute('CREATE TABLE IF NOT EXISTS project_action_intents(operation TEXT PRIMARY KEY,origin TEXT NOT NULL,resource TEXT NOT NULL,revision INTEGER NOT NULL,target INTEGER NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS project_action_changes(id INTEGER PRIMARY KEY,operation TEXT UNIQUE NOT NULL,resource TEXT NOT NULL,actor INTEGER NOT NULL,value INTEGER NOT NULL,revision INTEGER NOT NULL)')

    @staticmethod
    def _allowed(c: sqlite3.Connection,origin: ActionOrigin,resource: str) -> bool:
        row = c.execute('SELECT allowed FROM project_action_acl WHERE resource=? AND bot=? AND chat=? AND actor=?',
                        (resource,origin.bot_id,origin.chat_id,origin.actor_id)).fetchone()
        return row is not None and row[0] == 1

    def issue(self,origin: ActionOrigin,resource: str,target: int) -> str:
        """Explicit host action for a KNOWN delivered message; not a public route.

        An uncertain initial send is reconciled separately, never resent here.
        This sample supports integer domain values; the project owns its rules.
        """
        if not isinstance(resource,str) or not 1 <= len(resource.encode('utf-8')) <= 128:
            raise ValidationFailure('Use a bounded project resource ID')
        if type(target) is not int or not 0 <= target <= 1000:
            raise ValidationFailure('Use an explicitly validated target in 0..1000')
        with closing(sqlite3.connect(self.database,timeout=5)) as c,c:
            c.execute('BEGIN IMMEDIATE')
            if not self._allowed(c,origin,resource):
                raise PermissionDenied('Current resource access denied')
            row = c.execute('SELECT revision FROM project_resources WHERE resource=?',(resource,)).fetchone()
            if row is None:
                raise ConflictFailure('Resource is unavailable')
            if type(row[0]) is not int or not 1 <= row[0] < 2**63-1:
                raise ConflictFailure('Resource revision requires migration')
            operation = secrets.token_hex(16)
            c.execute('INSERT INTO project_action_intents VALUES(?,?,?,?,?)',
                      (operation,origin.scope(),resource,row[0],target))
        return operation

    def execute(self,origin: ActionOrigin,operation: str) -> OnceResult:
        if not isinstance(operation,str) or not _OPERATION.fullmatch(operation):
            raise ValidationFailure('Use the original server-issued operation ID')
        with closing(sqlite3.connect(self.database,timeout=5)) as c:
            intent = c.execute('SELECT origin,resource,revision,target FROM project_action_intents WHERE operation=?',(operation,)).fetchone()
        if intent is None or intent[0] != origin.scope():
            raise PermissionDenied('Action is unavailable in this origin')
        resource,revision,target = intent[1:]
        if (not isinstance(resource,str) or type(revision) is not int or not 1 <= revision < 2**63-1
                or type(target) is not int or not 0 <= target <= 1000):
            raise ConflictFailure('Stored intent requires migration')
        payload = {'resource':resource,'revision':revision,'target':target}
        def check(c: sqlite3.Connection,replayed: bool) -> bool:
            current = c.execute('SELECT origin,resource,revision,target FROM project_action_intents WHERE operation=?',(operation,)).fetchone()
            if current != intent or not self._allowed(c,origin,resource):
                return False
            current_resource = c.execute('SELECT revision FROM project_resources WHERE resource=?',(resource,)).fetchone()
            if current_resource is None:
                return False
            # Replay returns the original result; it is not current object state.
            if not replayed and current_resource[0] != revision:
                raise ConflictFailure('Resource revision changed')
            return True
        def apply(c: sqlite3.Connection) -> dict:
            cursor = c.execute('UPDATE project_resources SET value=?,revision=revision+1 WHERE resource=? AND revision=?',
                               (target,resource,revision))
            if cursor.rowcount != 1:
                raise ConflictFailure('Resource changed before write')
            effect = c.execute('INSERT INTO project_action_changes(operation,resource,actor,value,revision) VALUES(?,?,?,?,?)',
                               (operation,resource,origin.actor_id,target,revision+1))
            return {'operation_id':operation,'change_id':effect.lastrowid,
                    'resource':resource,'value':target,'revision':revision+1}
        return self.once.run_guarded(origin.scope(),operation,payload,apply,check=check)


def action_button(operation: str,text: str = 'Подтвердить') -> InlineKeyboardButton:
    if not isinstance(operation,str) or not _OPERATION.fullmatch(operation):
        raise ValidationFailure('Use a server-issued operation ID')
    return InlineKeyboardButton(text=text,callback_data='once:'+operation)


def attach_actions(dispatcher: Dispatcher,service: ProjectActions,
                   notify: Callable[[CallbackQuery,ActionResult],Awaitable[None]]) -> Router:
    """Retain current Dispatcher/storage/isolation; host chooses safe feedback."""
    router = Router(name='project-concurrent-actions')
    @router.callback_query(F.data.startswith('once:'))
    async def handle(query: CallbackQuery) -> None:
        await query.answer()  # ACK precedes checks/effect; it is not success.
        try:
            origin = callback_origin(query)
            receipt = await database_call(service.execute,origin,(query.data or '')[5:])
        except PermissionDenied:
            result = ActionResult('denied','Действие недоступно.')
        except (ConflictFailure,ValidationFailure):
            result = ActionResult('stale','Действие изменилось. Откройте актуальный экран.')
        else:
            result = ActionResult('replayed' if receipt.replayed else 'accepted',
                                  'Операция сохранена. Номер: '+str(receipt.value['change_id']))
        # A lost feedback/cancel must not generate a new intent or repeat an effect.
        await notify(query,result)
    dispatcher.include_router(router)
    return router
```

Для локальной приемки выполните `offline_concurrent_actions.py` с установленным wheel/SDK: два независимых Dispatcher workers одновременно обрабатывают тот же intent, затем две операции на одной revision. Должны остаться по одной business row/receipt на гонку; unknown feedback сверяется под исходным ID. Проверьте отозванный ACL до replay, чужие bot/chat/actor/message/topic, malformed ID, доступность сообщения, сохранность Router/storage и отсутствие Telegram HTTP. SQLite/network-share или разные хранилища требуют отдельной приемки проекта. SDK/Chrome/mock не подтверждают настоящих Telegram-клиентов, выплаты или независимое человеческое/AI исследование.

6 октября 2026 сверены только эти контракты: [SQLite transactions и BEGIN IMMEDIATE](https://www.sqlite.org/lang_transaction.html), [Python 3.13 sqlite3.set_authorizer](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.set_authorizer), [Telegram CallbackQuery и ACK](https://core.telegram.org/bots/api#callbackquery), [InaccessibleMessage/date=0](https://core.telegram.org/bots/api#inaccessiblemessage). Installed aiogram 3.31.0 и реальный file SQLite используются в локальных probes; дата не относится ко всем Telegram/payment API.
