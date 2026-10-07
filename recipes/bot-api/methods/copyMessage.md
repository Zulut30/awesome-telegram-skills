# copyMessage

[Официальные ограничения](https://core.telegram.org/bots/api#copymessage). SDK: aiogram 3.31.0 / CopyMessage.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'from_chat_id': 1, 'message_id': 1}
request = build_request("copyMessage", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `from_chat_id`, `message_id`.

Все параметры официального снимка: `chat_id`, `message_thread_id`, `direct_messages_topic_id`, `from_chat_id`, `message_id`, `video_start_timestamp`, `caption`, `parse_mode`, `caption_entities`, `show_caption_above_media`, `disable_notification`, `protect_content`, `allow_paid_broadcast`, `message_effect_id`, `suggested_post_parameters`, `reply_parameters`, `reply_markup`.
