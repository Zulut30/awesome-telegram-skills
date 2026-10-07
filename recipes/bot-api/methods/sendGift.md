# sendGift

[Официальные ограничения](https://core.telegram.org/bots/api#sendgift). SDK: aiogram 3.31.0 / SendGift.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'gift_id': 'FIXTURE_REPLACE'}
request = build_request("sendGift", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `gift_id`.

Все параметры официального снимка: `user_id`, `chat_id`, `gift_id`, `pay_for_upgrade`, `text`, `text_parse_mode`, `text_entities`.
