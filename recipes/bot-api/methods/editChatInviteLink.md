# editChatInviteLink

[Официальные ограничения](https://core.telegram.org/bots/api#editchatinvitelink). SDK: aiogram 3.31.0 / EditChatInviteLink.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'invite_link': 'FIXTURE_REPLACE'}
request = build_request("editChatInviteLink", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `invite_link`.

Все параметры официального снимка: `chat_id`, `invite_link`, `name`, `expire_date`, `member_limit`, `creates_join_request`.
