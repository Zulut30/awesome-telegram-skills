# getUserProfileAudios

[Официальные ограничения](https://core.telegram.org/bots/api#getuserprofileaudios). SDK: aiogram 3.31.0 / GetUserProfileAudios.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'user_id': 1}
request = build_request("getUserProfileAudios", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `user_id`.

Все параметры официального снимка: `user_id`, `offset`, `limit`.
