# transferGift

[Официальные ограничения](https://core.telegram.org/bots/api#transfergift). SDK: aiogram 3.31.0 / TransferGift.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'business_connection_id': 'FIXTURE_REPLACE', 'owned_gift_id': 'FIXTURE_REPLACE', 'new_owner_chat_id': 1}
request = build_request("transferGift", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `business_connection_id`, `owned_gift_id`, `new_owner_chat_id`.

Все параметры официального снимка: `business_connection_id`, `owned_gift_id`, `new_owner_chat_id`, `star_count`.
