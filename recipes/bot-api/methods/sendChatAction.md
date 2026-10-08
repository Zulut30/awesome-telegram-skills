# sendChatAction

[Официальные ограничения](https://core.telegram.org/bots/api#sendchataction). SDK: aiogram 3.31.0 / SendChatAction.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'action': 'typing'}
request = build_request("sendChatAction", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `action`.

Все параметры официального снимка: `business_connection_id`, `chat_id`, `message_thread_id`, `action`.
