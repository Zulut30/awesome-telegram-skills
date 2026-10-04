# sendRichMessageDraft

[Официальные ограничения](https://core.telegram.org/bots/api#sendrichmessagedraft). SDK: aiogram 3.31.0 / SendRichMessageDraft.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'draft_id': 1, 'rich_message': {'html': '<b>Пример</b>'}}
request = build_request("sendRichMessageDraft", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `draft_id`, `rich_message`.

Все параметры официального снимка: `chat_id`, `message_thread_id`, `draft_id`, `rich_message`, `can_stop`, `keep_on_stop`.
