# sendPaidMedia

[Официальные ограничения](https://core.telegram.org/bots/api#sendpaidmedia). SDK: aiogram 3.31.0 / SendPaidMedia.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'star_count': 1, 'media': [{'media': 'FIXTURE_REPLACE', 'photo': 'FIXTURE_FILE_ID_REPLACE', 'type': 'live_photo'}]}
request = build_request("sendPaidMedia", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `star_count`, `media`.

Все параметры официального снимка: `business_connection_id`, `chat_id`, `message_thread_id`, `direct_messages_topic_id`, `star_count`, `media`, `payload`, `caption`, `parse_mode`, `caption_entities`, `show_caption_above_media`, `disable_notification`, `protect_content`, `allow_paid_broadcast`, `suggested_post_parameters`, `reply_parameters`, `reply_markup`.
