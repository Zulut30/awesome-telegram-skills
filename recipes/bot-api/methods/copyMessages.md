# copyMessages

[Официальные ограничения](https://core.telegram.org/bots/api#copymessages). SDK: aiogram 3.31.0 / CopyMessages.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'from_chat_id': 1, 'message_ids': [1]}
request = build_request("copyMessages", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `from_chat_id`, `message_ids`.

Все параметры официального снимка: `chat_id`, `message_thread_id`, `direct_messages_topic_id`, `from_chat_id`, `message_ids`, `disable_notification`, `protect_content`, `remove_caption`.
