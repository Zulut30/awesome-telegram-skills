# setManagedBotAccessSettings

[Официальные ограничения](https://core.telegram.org/bots/api#setmanagedbotaccesssettings). SDK: aiogram 3.31.0 / SetManagedBotAccessSettings.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'user_id': 1, 'is_access_restricted': True}
request = build_request("setManagedBotAccessSettings", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `user_id`, `is_access_restricted`.

Все параметры официального снимка: `user_id`, `is_access_restricted`, `added_user_ids`.
