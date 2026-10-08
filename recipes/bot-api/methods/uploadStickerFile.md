# uploadStickerFile

[Официальные ограничения](https://core.telegram.org/bots/api#uploadstickerfile). SDK: aiogram 3.31.0 / UploadStickerFile.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'user_id': 1, 'sticker': BufferedInputFile(b"OFFLINE_FIXTURE_NOT_REAL_MEDIA", filename="fixture.bin"), 'sticker_format': 'FIXTURE_REPLACE'}
request = build_request("uploadStickerFile", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `user_id`, `sticker`, `sticker_format`.

Все параметры официального снимка: `user_id`, `sticker`, `sticker_format`.
