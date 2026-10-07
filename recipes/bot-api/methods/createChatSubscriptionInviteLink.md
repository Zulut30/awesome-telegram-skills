# createChatSubscriptionInviteLink

[Официальные ограничения](https://core.telegram.org/bots/api#createchatsubscriptioninvitelink). SDK: aiogram 3.31.0 / CreateChatSubscriptionInviteLink.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'subscription_period': '2026-10-04T12:00:00Z', 'subscription_price': 1}
request = build_request("createChatSubscriptionInviteLink", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `subscription_period`, `subscription_price`.

Все параметры официального снимка: `chat_id`, `name`, `subscription_period`, `subscription_price`.
