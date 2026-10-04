# setPassportDataErrors

[Официальные ограничения](https://core.telegram.org/bots/api#setpassportdataerrors). SDK: aiogram 3.31.0 / SetPassportDataErrors.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'user_id': 1, 'errors': [{'type': 'FIXTURE_REPLACE', 'field_name': 'FIXTURE_REPLACE', 'data_hash': 'FIXTURE_REPLACE', 'message': 'FIXTURE_REPLACE', 'source': 'data'}]}
request = build_request("setPassportDataErrors", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `user_id`, `errors`.

Все параметры официального снимка: `user_id`, `errors`.
