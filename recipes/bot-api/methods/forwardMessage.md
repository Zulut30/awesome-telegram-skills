# forwardMessage

[Официальные ограничения](https://core.telegram.org/bots/api#forwardmessage). SDK: aiogram 3.31.0 / ForwardMessage.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'from_chat_id': 1, 'message_id': 1}
request = build_request("forwardMessage", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `from_chat_id`, `message_id`.

Все параметры официального снимка: `chat_id`, `message_thread_id`, `direct_messages_topic_id`, `from_chat_id`, `video_start_timestamp`, `disable_notification`, `protect_content`, `message_effect_id`, `suggested_post_parameters`, `message_id`.
