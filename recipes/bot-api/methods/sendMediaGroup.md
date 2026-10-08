# sendMediaGroup

[Официальные ограничения](https://core.telegram.org/bots/api#sendmediagroup). SDK: aiogram 3.31.0 / SendMediaGroup.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'media': [{'media': 'FIXTURE_REPLACE', 'type': 'audio'}]}
request = build_request("sendMediaGroup", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `media`.

Все параметры официального снимка: `business_connection_id`, `chat_id`, `message_thread_id`, `direct_messages_topic_id`, `media`, `disable_notification`, `protect_content`, `allow_paid_broadcast`, `message_effect_id`, `reply_parameters`.
