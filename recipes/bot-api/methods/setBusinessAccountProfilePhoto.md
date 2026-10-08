# setBusinessAccountProfilePhoto

[Официальные ограничения](https://core.telegram.org/bots/api#setbusinessaccountprofilephoto). SDK: aiogram 3.31.0 / SetBusinessAccountProfilePhoto.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'business_connection_id': 'FIXTURE_REPLACE', 'photo': {'photo': 'FIXTURE_FILE_ID_REPLACE', 'type': 'static'}}
request = build_request("setBusinessAccountProfilePhoto", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `business_connection_id`, `photo`.

Все параметры официального снимка: `business_connection_id`, `photo`, `is_public`.
