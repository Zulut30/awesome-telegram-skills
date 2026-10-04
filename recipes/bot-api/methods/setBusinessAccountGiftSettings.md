# setBusinessAccountGiftSettings

[Официальные ограничения](https://core.telegram.org/bots/api#setbusinessaccountgiftsettings). SDK: aiogram 3.31.0 / SetBusinessAccountGiftSettings.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'business_connection_id': 'FIXTURE_REPLACE', 'show_gift_button': True, 'accepted_gift_types': {'unlimited_gifts': True, 'limited_gifts': True, 'unique_gifts': True, 'premium_subscription': True, 'gifts_from_channels': True}}
request = build_request("setBusinessAccountGiftSettings", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `business_connection_id`, `show_gift_button`, `accepted_gift_types`.

Все параметры официального снимка: `business_connection_id`, `show_gift_button`, `accepted_gift_types`.
