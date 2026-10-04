# editStory

[Официальные ограничения](https://core.telegram.org/bots/api#editstory). SDK: aiogram 3.31.0 / EditStory.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'business_connection_id': 'FIXTURE_REPLACE', 'story_id': 1, 'content': {'photo': 'FIXTURE_FILE_ID_REPLACE', 'type': 'photo'}}
request = build_request("editStory", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `business_connection_id`, `story_id`, `content`.

Все параметры официального снимка: `business_connection_id`, `story_id`, `content`, `caption`, `parse_mode`, `caption_entities`, `areas`.
