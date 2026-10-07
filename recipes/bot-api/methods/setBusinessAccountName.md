# setBusinessAccountName

[Официальные ограничения](https://core.telegram.org/bots/api#setbusinessaccountname). SDK: aiogram 3.31.0 / SetBusinessAccountName.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'business_connection_id': 'FIXTURE_REPLACE', 'first_name': 'FIXTURE_REPLACE'}
request = build_request("setBusinessAccountName", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `business_connection_id`, `first_name`.

Все параметры официального снимка: `business_connection_id`, `first_name`, `last_name`.
