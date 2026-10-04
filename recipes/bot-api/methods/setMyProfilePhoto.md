# setMyProfilePhoto

[Официальные ограничения](https://core.telegram.org/bots/api#setmyprofilephoto). SDK: aiogram 3.31.0 / SetMyProfilePhoto.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'photo': {'photo': 'FIXTURE_FILE_ID_REPLACE', 'type': 'static'}}
request = build_request("setMyProfilePhoto", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `photo`.

Все параметры официального снимка: `photo`.
