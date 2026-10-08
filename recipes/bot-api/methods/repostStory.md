# repostStory

[Официальные ограничения](https://core.telegram.org/bots/api#repoststory). SDK: aiogram 3.31.0 / RepostStory.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'business_connection_id': 'FIXTURE_REPLACE', 'from_chat_id': 1, 'from_story_id': 1, 'active_period': 1}
request = build_request("repostStory", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `business_connection_id`, `from_chat_id`, `from_story_id`, `active_period`.

Все параметры официального снимка: `business_connection_id`, `from_chat_id`, `from_story_id`, `active_period`, `post_to_chat_page`, `protect_content`.
