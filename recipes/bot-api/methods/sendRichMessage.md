# sendRichMessage

[Официальные ограничения](https://core.telegram.org/bots/api#sendrichmessage). SDK: aiogram 3.31.0 / SendRichMessage.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'rich_message': {'html': '<b>Пример</b>'}}
request = build_request("sendRichMessage", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `rich_message`.

Все параметры официального снимка: `business_connection_id`, `chat_id`, `message_thread_id`, `direct_messages_topic_id`, `ephemeral_message_parameters`, `rich_message`, `disable_notification`, `protect_content`, `allow_paid_broadcast`, `message_effect_id`, `suggested_post_parameters`, `reply_parameters`, `reply_markup`.
