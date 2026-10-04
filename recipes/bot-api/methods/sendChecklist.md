# sendChecklist

[Официальные ограничения](https://core.telegram.org/bots/api#sendchecklist). SDK: aiogram 3.31.0 / SendChecklist.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'business_connection_id': 'FIXTURE_REPLACE', 'chat_id': 1, 'checklist': {'title': 'FIXTURE_REPLACE', 'tasks': [{'id': 1, 'text': 'FIXTURE_REPLACE'}]}}
request = build_request("sendChecklist", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `business_connection_id`, `chat_id`, `checklist`.

Все параметры официального снимка: `business_connection_id`, `chat_id`, `checklist`, `disable_notification`, `protect_content`, `message_effect_id`, `reply_parameters`, `reply_markup`.
