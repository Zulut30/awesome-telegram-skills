# setChatAdministratorCustomTitle

[Официальные ограничения](https://core.telegram.org/bots/api#setchatadministratorcustomtitle). SDK: aiogram 3.31.0 / SetChatAdministratorCustomTitle.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'user_id': 1, 'custom_title': 'FIXTURE_REPLACE'}
request = build_request("setChatAdministratorCustomTitle", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `user_id`, `custom_title`.

Все параметры официального снимка: `chat_id`, `user_id`, `custom_title`.
