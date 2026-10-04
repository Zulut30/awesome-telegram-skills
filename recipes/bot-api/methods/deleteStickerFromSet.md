# deleteStickerFromSet

[Официальные ограничения](https://core.telegram.org/bots/api#deletestickerfromset). SDK: aiogram 3.31.0 / DeleteStickerFromSet.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'sticker': 'FIXTURE_FILE_ID_REPLACE'}
request = build_request("deleteStickerFromSet", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `sticker`.

Все параметры официального снимка: `sticker`.
