# sendGame

[Официальные ограничения](https://core.telegram.org/bots/api#sendgame). SDK: aiogram 3.31.0 / SendGame.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'chat_id': 1, 'game_short_name': 'FIXTURE_REPLACE'}
request = build_request("sendGame", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `chat_id`, `game_short_name`.

Все параметры официального снимка: `business_connection_id`, `chat_id`, `message_thread_id`, `game_short_name`, `disable_notification`, `protect_content`, `allow_paid_broadcast`, `message_effect_id`, `reply_parameters`, `reply_markup`.
