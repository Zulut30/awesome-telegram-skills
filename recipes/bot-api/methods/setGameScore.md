# setGameScore

[Официальные ограничения](https://core.telegram.org/bots/api#setgamescore). SDK: aiogram 3.31.0 / SetGameScore.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'user_id': 1, 'score': 1}
request = build_request("setGameScore", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `user_id`, `score`.

Все параметры официального снимка: `user_id`, `score`, `force`, `disable_edit_message`, `chat_id`, `message_id`, `inline_message_id`.
