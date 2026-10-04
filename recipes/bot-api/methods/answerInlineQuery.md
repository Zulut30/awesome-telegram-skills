# answerInlineQuery

[Официальные ограничения](https://core.telegram.org/bots/api#answerinlinequery). SDK: aiogram 3.31.0 / AnswerInlineQuery.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'inline_query_id': 'FIXTURE_REPLACE', 'results': [{'id': 'FIXTURE_REPLACE', 'audio_file_id': 'FIXTURE_REPLACE', 'type': 'audio'}]}
request = build_request("answerInlineQuery", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `inline_query_id`, `results`.

Все параметры официального снимка: `inline_query_id`, `results`, `cache_time`, `is_personal`, `next_offset`, `button`.
