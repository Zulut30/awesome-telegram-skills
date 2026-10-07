# editMessageChecklist

[Официальные ограничения](https://core.telegram.org/bots/api#editmessagechecklist). SDK: aiogram 3.31.0 / EditMessageChecklist.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'business_connection_id': 'FIXTURE_REPLACE', 'chat_id': 1, 'message_id': 1, 'checklist': {'title': 'FIXTURE_REPLACE', 'tasks': [{'id': 1, 'text': 'FIXTURE_REPLACE'}]}}
request = build_request("editMessageChecklist", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `business_connection_id`, `chat_id`, `message_id`, `checklist`.

Все параметры официального снимка: `business_connection_id`, `chat_id`, `message_id`, `checklist`, `reply_markup`.
