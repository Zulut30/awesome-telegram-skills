# setStickerSetTitle

[Официальные ограничения](https://core.telegram.org/bots/api#setstickersettitle). SDK: aiogram 3.31.0 / SetStickerSetTitle.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'name': 'fixture_name', 'title': 'FIXTURE_REPLACE'}
request = build_request("setStickerSetTitle", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `name`, `title`.

Все параметры официального снимка: `name`, `title`.
