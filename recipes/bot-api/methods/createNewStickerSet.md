# createNewStickerSet

[Официальные ограничения](https://core.telegram.org/bots/api#createnewstickerset). SDK: aiogram 3.31.0 / CreateNewStickerSet.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'user_id': 1, 'name': 'fixture_name', 'title': 'FIXTURE_REPLACE', 'stickers': [{'sticker': 'FIXTURE_FILE_ID_REPLACE', 'format': 'static', 'emoji_list': ['FIXTURE_REPLACE']}]}
request = build_request("createNewStickerSet", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `user_id`, `name`, `title`, `stickers`.

Все параметры официального снимка: `user_id`, `name`, `title`, `stickers`, `sticker_type`, `needs_repainting`.
