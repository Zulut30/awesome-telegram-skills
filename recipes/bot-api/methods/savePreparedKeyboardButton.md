# savePreparedKeyboardButton

[Официальные ограничения](https://core.telegram.org/bots/api#savepreparedkeyboardbutton). SDK: aiogram 3.31.0 / SavePreparedKeyboardButton.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'user_id': 1, 'button': {'text': 'FIXTURE_REPLACE'}}
request = build_request("savePreparedKeyboardButton", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `user_id`, `button`.

Все параметры официального снимка: `user_id`, `button`.
