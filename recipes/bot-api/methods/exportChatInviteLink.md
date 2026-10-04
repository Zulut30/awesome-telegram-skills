# exportChatInviteLink

[Официальные ограничения](https://core.telegram.org/bots/api#exportchatinvitelink). SDK: aiogram 3.31.0 / ExportChatInviteLink.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1}
request = build_request("exportChatInviteLink", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`.

Все параметры официального снимка: `chat_id`.
