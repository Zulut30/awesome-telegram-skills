# createForumTopic

[Официальные ограничения](https://core.telegram.org/bots/api#createforumtopic). SDK: aiogram 3.31.0 / CreateForumTopic.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'name': 'fixture_name'}
request = build_request("createForumTopic", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `name`.

Все параметры официального снимка: `chat_id`, `name`, `icon_color`, `icon_custom_emoji_id`.
