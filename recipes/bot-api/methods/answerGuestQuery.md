# answerGuestQuery

[Официальные ограничения](https://core.telegram.org/bots/api#answerguestquery). SDK: aiogram 3.31.0 / AnswerGuestQuery.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'guest_query_id': 'FIXTURE_REPLACE', 'result': {'id': 'FIXTURE_REPLACE', 'audio_file_id': 'FIXTURE_REPLACE', 'type': 'audio'}}
request = build_request("answerGuestQuery", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `guest_query_id`, `result`.

Все параметры официального снимка: `guest_query_id`, `result`.
