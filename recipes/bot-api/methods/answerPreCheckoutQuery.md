# answerPreCheckoutQuery

[Официальные ограничения](https://core.telegram.org/bots/api#answerprecheckoutquery). SDK: aiogram 3.31.0 / AnswerPreCheckoutQuery.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'pre_checkout_query_id': 'FIXTURE_REPLACE', 'ok': True}
request = build_request("answerPreCheckoutQuery", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `pre_checkout_query_id`, `ok`.

Все параметры официального снимка: `pre_checkout_query_id`, `ok`, `error_message`.
