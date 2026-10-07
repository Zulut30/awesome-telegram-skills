# setCustomEmojiStickerSetThumbnail

[Официальные ограничения](https://core.telegram.org/bots/api#setcustomemojistickersetthumbnail). SDK: aiogram 3.31.0 / SetCustomEmojiStickerSetThumbnail.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'name': 'fixture_name'}
request = build_request("setCustomEmojiStickerSetThumbnail", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `name`.

Все параметры официального снимка: `name`, `custom_emoji_id`.
