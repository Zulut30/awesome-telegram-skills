# closeForumTopic

[Официальные ограничения](https://core.telegram.org/bots/api#closeforumtopic). SDK: aiogram 3.31.0 / CloseForumTopic.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'message_thread_id': 1}
request = build_request("closeForumTopic", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `message_thread_id`.

Все параметры официального снимка: `chat_id`, `message_thread_id`.
