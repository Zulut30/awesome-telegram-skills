# Telethon и сессии

Первичные источники: [Telethon](https://docs.telethon.dev/en/stable/), [client reference](https://docs.telethon.dev/en/stable/modules/client.html), [signing in](https://docs.telethon.dev/en/stable/basic/signing-in.html), [session storage](https://docs.telethon.dev/en/stable/concepts/sessions.html), [events](https://docs.telethon.dev/en/stable/modules/events.html). Сигнатуры ниже сверены с установленным Telethon 1.45.0 7 октября 2026 года; перед использованием сверьте их со своей версией.

## Вход и сессии

`api_id` и `api_hash` (выдаются на my.telegram.org) определяют приложение, но не авторизуют пользователя. Доступ к чатам дает только пользовательская сессия после входа по номеру, коду и, если включена, паролю 2FA. Токен бота в MTProto дает только идентичность бота: истории личных чатов пользователя через него нет.

Сессия — это полномочия аккаунта. Файл `*.session` (SQLite) или строка `StringSession` хранятся вне исходников, в секретах окружения или в файле с ограниченными правами, и не попадают в логи, ответы и репозиторий. Вход выполняет владелец аккаунта отдельно (`client.start()` спрашивает номер, код и пароль); рабочий скрипт только подключается к готовой сессии и завершается понятной ошибкой, если она отозвана. У каждой сессии один процесс-владелец: общий SQLite-файл в нескольких процессах блокируется.

## Чтение истории с checkpoint

`iter_messages(entity, min_id=last_id, reverse=True, wait_time=1)` отдает сообщения от старых к новым после `last_id`; Telethon сам делит выдачу на страницы. Короткий `FloodWait` (до `flood_sleep_threshold`, по умолчанию 60 секунд) клиент пережидает сам, более долгий приходит исключением `FloodWaitError` с полем `seconds`.

```python
import asyncio
import os
import sqlite3

from telethon import TelegramClient, errors, utils
from telethon.sessions import StringSession

ALLOWED = ["@first_group", "@second_group", -1001234567890]  # только выбранные чаты
BATCH = 100

db = sqlite3.connect("history.db")
db.executescript("""
CREATE TABLE IF NOT EXISTS messages (peer_id INTEGER, id INTEGER, date TEXT, sender_id INTEGER, text TEXT,
    edited TEXT, deleted INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (peer_id, id));
CREATE TABLE IF NOT EXISTS checkpoints (peer_id INTEGER PRIMARY KEY, last_id INTEGER NOT NULL);
""")


def save(peer_id: int, message) -> None:
    """Вставка или обновление по (peer_id, id): повтор того же сообщения не создает дубль."""
    db.execute(
        "INSERT INTO messages (peer_id, id, date, sender_id, text, edited) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (peer_id, id) DO UPDATE SET text = excluded.text, edited = excluded.edited",
        (peer_id, message.id, message.date.isoformat(), message.sender_id, message.message,
         message.edit_date.isoformat() if message.edit_date else None))


def checkpoint(peer_id: int) -> int:
    row = db.execute("SELECT last_id FROM checkpoints WHERE peer_id = ?", (peer_id,)).fetchone()
    return row[0] if row else 0


async def read_history(client: TelegramClient, chat) -> None:
    entity = await client.get_entity(chat)
    peer_id = utils.get_peer_id(entity)
    while True:
        last_id, pending = checkpoint(peer_id), 0
        try:
            async for message in client.iter_messages(entity, min_id=last_id, reverse=True, wait_time=1):
                save(peer_id, message)
                last_id, pending = message.id, pending + 1
                if pending == BATCH:  # сообщения и checkpoint фиксируются вместе
                    db.execute("INSERT OR REPLACE INTO checkpoints VALUES (?, ?)", (peer_id, last_id))
                    db.commit()
                    pending = 0
            db.execute("INSERT OR REPLACE INTO checkpoints VALUES (?, ?)", (peer_id, last_id))
            db.commit()
            return
        except errors.FloodWaitError as error:
            db.rollback()  # незафиксированная пачка будет прочитана снова от checkpoint
            await asyncio.sleep(error.seconds + 1)


async def main() -> None:
    client = TelegramClient(StringSession(os.environ["TG_SESSION"]), int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise SystemExit("Сессия не авторизована или отозвана: владелец аккаунта должен войти заново.")
        for chat in ALLOWED:
            await read_history(client, chat)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
```

## История и новые сообщения без разрыва и дублей

1. Зарегистрируйте обработчики `events.NewMessage(chats=ALLOWED)` и `events.MessageEdited(chats=ALLOWED)` **до** чтения истории, чтобы сообщения, пришедшие во время выгрузки, не потерялись.
2. Обработчики вызывают `save()` и сразу `db.commit()`: вставка по ключу `(peer_id, id)` поглощает дубли между историей и новыми сообщениями.
3. Checkpoint двигает только последовательное чтение истории. Если двигать его из обработчика новых сообщений, сбой между ними оставит дыру.
4. После переподключения и рестарта снова вызовите `read_history` от checkpoint: он доберет пропущенное. Параметр `catch_up=True` у `TelegramClient` (по умолчанию `False`) просит пропущенные updates, но не заменяет эту проверку.
5. Правки сохраняйте обновлением строки (`edited`). `events.MessageDeleted` приходит не всегда, а `chat_id` в нем есть только для каналов и супергрупп; в личных чатах и малых группах ID сообщения уникален в пределах аккаунта, поэтому удаление ищите по `id` среди таких чатов и помечайте `deleted = 1`.
6. Правки и удаления, случившиеся, пока клиент был выключен, чтение от checkpoint не вернет. Если они важны, периодически перечитывайте последнее окно сообщений; иначе явно запишите это ограничение.
7. Вся схема только читает: ни выгрузка истории, ни обработчики не отмечают сообщения прочитанными и ничего не отправляют. Скажите это в описании решения, а тестовые сообщения пишите вручную в обычном приложении Telegram.

## Что чтение не делает

`iter_messages` и обработчики событий не отмечают сообщения прочитанными. Не вызывайте `send_read_acknowledge`, отправку сообщений, вступление в группы и выгрузку контактов, если задача этого прямо не требует. Секретные чаты не входят в облачную историю и через `iter_messages` недоступны.

## Типичные ошибки

- Вход токеном бота или попытка «обойти» ограничения сменой аккаунтов и повторными входами в цикле.
- Нет списка разрешенных чатов: скрипт читает все диалоги через `iter_dialogs`.
- `FloodWaitError` пойман вне цикла: чат пропускается целиком, а не дочитывается после паузы.
- Checkpoint пишется до сохранения сообщений или из обработчика новых сообщений.
- Ключ сообщения — только `id` без чата: в каналах ID повторяются между каналами.
- Строка сессии печатается в лог или хранится в коде; `telethon.sync` внутри работающего цикла событий async-приложения.

## Другие библиотеки

Telethon — библиотека сообщества поверх MTProto. Официальный клиентский фундамент Telegram — [TDLib](https://core.telegram.org/tdlib). [Pyrogram](https://docs.pyrogram.org/) сообщает о прекращении поддержки; не выбирайте оригинальный пакет для нового проекта без учета этого. Поддержка форков проверяется отдельно.
