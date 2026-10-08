# restrictChatMember

[Официальные ограничения](https://core.telegram.org/bots/api#restrictchatmember). SDK: aiogram 3.31.0 / RestrictChatMember.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'user_id': 1, 'permissions': {}}
request = build_request("restrictChatMember", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `user_id`, `permissions`.

Все параметры официального снимка: `chat_id`, `user_id`, `permissions`, `use_independent_chat_permissions`, `until_date`.
