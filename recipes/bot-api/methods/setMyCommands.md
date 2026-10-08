# setMyCommands

[Официальные ограничения](https://core.telegram.org/bots/api#setmycommands). SDK: aiogram 3.31.0 / SetMyCommands.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'commands': [{'command': 'FIXTURE_REPLACE', 'description': 'FIXTURE_REPLACE'}]}
request = build_request("setMyCommands", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `commands`.

Все параметры официального снимка: `commands`, `scope`, `language_code`.
