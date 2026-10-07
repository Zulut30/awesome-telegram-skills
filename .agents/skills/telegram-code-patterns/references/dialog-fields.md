# Семь типов полей и подтверждение формы

Доступно с 0.18.0, проверено на 0.24.0. Optional aiogram (проверяемый SDK 3.31.0). Подключай `dialog_form_router` в существующий Dispatcher с его FSM/storage и включенной actor-scoped event isolation. `TextField` совместим с новым router; старые `text_form_router` и строковый `FormSubmission` сохраняют контракт. Новые `DialogSubmission.values` содержат строки и плоские immutable metadata; `as_dict()` возвращает свежую JSON-копию. Значения исключены из repr, но приложение само исключает личные данные из логов.

| Поле | Результат и политика |
| --- | --- |
| `NumberField` | Точная decimal-строка; точка/запятая, min/max (нормализованная граница до 64 символов), 0–18 дробных знаков; без float/exponent/округления |
| `EmailField` | ASCII dot-atom до 254 символов; case local-part сохраняется, domain lowercase; DNS/владение mailbox не проверяются |
| `PhoneField` | Явный международный +номер, 7–15 ASCII цифр; пробелы/скобки/дефисы убираются; страна не угадывается, владение не проверяется |
| `DateField` | Реальная дата YYYY-MM-DD с min/max; без неявной locale/timezone |
| `FileField` | Один document, opaque IDs и ограниченные metadata; max_bytes, MIME allowlist; неизвестный размер отклоняется |
| `ContactField` | Контакт с phone/name/optional user_id; default own требует user_id автора, пересылка отклоняется; own=False явно допускает чужой контакт |
| `LocationField` | Статичные lat/lng и optional accuracy 0–1500; finite/range guards; live location и пересылка отклоняются |

Router поддерживает 1–10 уникальных полей, обычный private chat без Business и forum topic, `/collect` для запуска/возобновления, `/back` и `/cancel`. Текст и document принимаются только ответом на **текущий вопрос текущего бота в этом чате**. ForceReply помогает клиенту, но проверку автора/шага выполняет сервер. Контакт и геопозиция из reply-клавиатуры не имеют надежного ID поколения клавиатуры: сначала сохраняется candidate, затем пользователь подтверждает его inline-кнопкой, связанной с автором, шагом, operation_id, nonce и message_id. Замена candidate, возврат и возобновление отзывают старые кнопки. Координаты не доказывают физическое присутствие; совпавший contact.user_id не выдает бизнес-права.

Файлы не скачиваются; file_name не превращается в путь, file_id не показывается в review. MIME/size metadata не доказывают содержимое: отдельная обработка проверяет реальные байты, download limit, тип и безопасность. vCard не сохраняется. Пример хранит личные данные только в выбранном владельцем файле; перед реальным запуском задай необходимость сбора, срок хранения и удаление.

Ниже полная композиция с семью полями и file SQLite. В своем Dispatcher вызывай `attach_dialog`, сохраняя существующий `/help`, storage и middleware. Standalone `main` — явный запуск отдельного тестового бота с локальным BOT_TOKEN; импорт не запускает polling. Сначала проверь, что для токена не работает другой getUpdates consumer.

```python
"""Attach typed forms to an existing Dispatcher; business effect uses file SQLite."""
from __future__ import annotations

import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from telegram_patterns import BotSettings, SQLiteOnce
from telegram_patterns.aiogram import (ContactField, DateField, DialogSubmission, EmailField, FileField,
    LocationField, NumberField, PhoneField, dialog_form_router, run_bot)


def fields():
    return [NumberField('amount','Количество','Введите количество от 1 до 100.',minimum=1,maximum=100,decimal_places=0),
        EmailField('email','Email','Укажите email.'),
        PhoneField('phone','Телефон','Укажите номер с + и кодом страны.'),
        DateField('date','Дата','Введите дату в формате ГГГГ-ММ-ДД.',minimum='2026-10-05'),
        FileField('file','Документ','Пришлите один PDF ответом на этот вопрос.',max_bytes=1024*1024,mime_types=('application/pdf',)),
        ContactField('contact','Контакт','Поделитесь своим контактом через кнопку.'),
        LocationField('location','Место','Поделитесь статичной геопозицией через кнопку.')]


class Requests:
    """Example policy: authenticated private actors create only their own request.

    No entitlement or external action. File metadata isn't content validation.
    Production supplies persistent FSM/isolation and retention for personal data.
    """
    def __init__(self,database:Path):
        self.once=SQLiteOnce(database);self.once.initialize()
        with closing(sqlite3.connect(database)) as connection,connection:
            connection.execute('CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, actor INTEGER NOT NULL, body TEXT NOT NULL)')

    async def submit(self,submission:DialogSubmission)->str:
        if submission.actor_id != submission.chat_id or set(submission.values) != {f.name for f in fields()}:
            raise ValueError('Invalid private request scope')
        values={f.name:f.restore(submission.values[f.name]) for f in fields()}
        if values['contact']['user_id']!=submission.actor_id: raise ValueError('Contact owner mismatch')
        def persist():
            # Current authorization policy checked before effect AND cached replay.
            if submission.actor_id <= 0: raise PermissionError('Actor is not allowed')
            return self.once.run(f'bot:{submission.bot_id}:actor:{submission.actor_id}:dialog',submission.operation_id,values,
                lambda db:{'id':db.execute('INSERT INTO requests(actor,body) VALUES (?,?)',
                    (submission.actor_id,json.dumps(values,ensure_ascii=False))).lastrowid})
        result=await asyncio.to_thread(persist)
        return f"Заявка №{result.value['id']} сохранена."


def attach_dialog(dispatcher:Dispatcher,service:Requests):
    # Preserve existing handlers, commands, storage and middleware.
    dispatcher.include_router(dialog_form_router(fields(),service.submit,name='request',command='collect'))


async def main():
    database=Path(sys.argv[1]) if len(sys.argv)>1 else Path('requests.sqlite')
    dispatcher=Dispatcher(events_isolation=SimpleEventIsolation())
    attach_dialog(dispatcher,Requests(database))
    await run_bot(dispatcher,BotSettings.from_env())


if __name__=='__main__':asyncio.run(main())
```

Перед business effect и cached replay сервис перепроверяет текущую авторизацию и нормализованные значения. `operation_id` — 128-bit server-derived ключ того же намерения, а не право на доступ. `SQLiteOnce` объединяет только effect на своем connection и receipt; HTTP/payments им автоматически не защищены. Внешние эффекты сверяются отдельно.

Final submit сначала ACK, затем сохраняет `submission_started`, потом вызывает async `on_submit`. Timeout, invalid completion или отмена task сохраняют этот ключ и блокируют редактирование/отмену/новую заявку до явной сверки той же кнопкой. Успех очищает форму **до** feedback, поэтому lost feedback и двойное нажатие не создают вторую заявку. Lost prompt/candidate/review не повторяется автоматически: явный `/collect` возобновляет незавершенный draft и привязывает новый UI; accepted answers и operation_id сохраняются.

FSM/storage принадлежит проекту. MemoryStorage теряет draft и pending intent после process restart; для продолжения на рестарте нужен существующий durable FSM, сохраненный operation_id и процедура сверки. SimpleEventIsolation сериализует только один процесс; другой worker требует host storage/isolation. Router проверяет точные schema/owner/value shapes и не сбрасывает поврежденное либо несовместимое состояние. При изменении custom TextField validator повысить `schema_version` и мигрировать/сверить старые формы; callable не сериализуется.

Проверка авторского примера: реальный synthetic Dispatcher, все семь типов, неправильный ответ/автор/шаг, новый candidate и stale кнопка, back/cancel, existing help/data, потерянный receipt после реального SQLite commit, повтор того же intent и одна бизнес-запись. Это SDK/mock evidence; реальные Telegram-клиенты, физические устройства, независимое применение навыка и production pilot требуют своей приемки.

Источники, просмотренный scope 5 октября 2026: [ForceReply](https://core.telegram.org/bots/api#forcereply), [KeyboardButton](https://core.telegram.org/bots/api#keyboardbutton), [Document](https://core.telegram.org/bots/api#document), [Contact](https://core.telegram.org/bots/api#contact), [Location](https://core.telegram.org/bots/api#location); [aiogram 3.31.0 FSM storage](https://docs.aiogram.dev/en/v3.31.0/dispatcher/finite_state_machine/storages.html). Сверены private request buttons, reply UI и optional metadata; этим не обновлены все методы Bot API и платежные источники. Лимиты email/phone/document — явная политика компонента, не обещание Telegram.
