# savePreparedInlineMessage

[Официальные ограничения](https://core.telegram.org/bots/api#savepreparedinlinemessage). SDK: aiogram 3.31.0 / SavePreparedInlineMessage.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'user_id': 1, 'result': {'id': 'FIXTURE_REPLACE', 'audio_file_id': 'FIXTURE_REPLACE', 'type': 'audio'}}
request = build_request("savePreparedInlineMessage", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `user_id`, `result`.

Все параметры официального снимка: `user_id`, `result`, `allow_user_chats`, `allow_bot_chats`, `allow_group_chats`, `allow_channel_chats`.
