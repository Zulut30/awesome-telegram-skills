# answerShippingQuery

[Официальные ограничения](https://core.telegram.org/bots/api#answershippingquery). SDK: aiogram 3.31.0 / AnswerShippingQuery.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'shipping_query_id': 'FIXTURE_REPLACE', 'ok': True}
request = build_request("answerShippingQuery", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `shipping_query_id`, `ok`.

Все параметры официального снимка: `shipping_query_id`, `ok`, `shipping_options`, `error_message`.
