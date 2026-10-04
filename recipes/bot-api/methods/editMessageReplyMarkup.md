# editMessageReplyMarkup

[Официальные ограничения](https://core.telegram.org/bots/api#editmessagereplymarkup). SDK: aiogram 3.31.0 / EditMessageReplyMarkup.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {}
request = build_request("editMessageReplyMarkup", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: нет.

Все параметры официального снимка: `business_connection_id`, `chat_id`, `message_id`, `inline_message_id`, `reply_markup`.
