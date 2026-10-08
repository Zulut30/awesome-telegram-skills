# transferBusinessAccountStars

[Официальные ограничения](https://core.telegram.org/bots/api#transferbusinessaccountstars). SDK: aiogram 3.31.0 / TransferBusinessAccountStars.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'business_connection_id': 'FIXTURE_REPLACE', 'star_count': 1}
request = build_request("transferBusinessAccountStars", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `business_connection_id`, `star_count`.

Все параметры официального снимка: `business_connection_id`, `star_count`.
