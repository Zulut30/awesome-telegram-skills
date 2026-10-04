# answerChatJoinRequestQuery

[Официальные ограничения](https://core.telegram.org/bots/api#answerchatjoinrequestquery). SDK: aiogram 3.31.0 / AnswerChatJoinRequestQuery.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_join_request_query_id': 'FIXTURE_REPLACE', 'result': 'FIXTURE_REPLACE'}
request = build_request("answerChatJoinRequestQuery", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_join_request_query_id`, `result`.

Все параметры официального снимка: `chat_join_request_query_id`, `result`.
