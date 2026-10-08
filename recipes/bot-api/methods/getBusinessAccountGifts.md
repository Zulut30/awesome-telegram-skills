# getBusinessAccountGifts

[Официальные ограничения](https://core.telegram.org/bots/api#getbusinessaccountgifts). SDK: aiogram 3.31.0 / GetBusinessAccountGifts.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'business_connection_id': 'FIXTURE_REPLACE'}
request = build_request("getBusinessAccountGifts", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `business_connection_id`.

Все параметры официального снимка: `business_connection_id`, `exclude_unsaved`, `exclude_saved`, `exclude_unlimited`, `exclude_limited_upgradable`, `exclude_limited_non_upgradable`, `exclude_unique`, `exclude_from_blockchain`, `sort_by_price`, `offset`, `limit`.
