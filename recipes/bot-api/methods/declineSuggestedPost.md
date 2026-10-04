# declineSuggestedPost

[Официальные ограничения](https://core.telegram.org/bots/api#declinesuggestedpost). SDK: aiogram 3.31.0 / DeclineSuggestedPost.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'message_id': 1}
request = build_request("declineSuggestedPost", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `message_id`.

Все параметры официального снимка: `chat_id`, `message_id`, `comment`.
