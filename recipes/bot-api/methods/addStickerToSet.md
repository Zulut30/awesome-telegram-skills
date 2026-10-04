# addStickerToSet

[Официальные ограничения](https://core.telegram.org/bots/api#addstickertoset). SDK: aiogram 3.31.0 / AddStickerToSet.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'user_id': 1, 'name': 'fixture_name', 'sticker': {'sticker': 'FIXTURE_FILE_ID_REPLACE', 'format': 'static', 'emoji_list': ['FIXTURE_REPLACE']}}
request = build_request("addStickerToSet", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `user_id`, `name`, `sticker`.

Все параметры официального снимка: `user_id`, `name`, `sticker`.
