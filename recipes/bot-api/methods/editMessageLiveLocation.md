# editMessageLiveLocation

[Официальные ограничения](https://core.telegram.org/bots/api#editmessagelivelocation). SDK: aiogram 3.31.0 / EditMessageLiveLocation.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'latitude': 1, 'longitude': 1}
request = build_request("editMessageLiveLocation", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `latitude`, `longitude`.

Все параметры официального снимка: `business_connection_id`, `chat_id`, `message_id`, `inline_message_id`, `latitude`, `longitude`, `live_period`, `horizontal_accuracy`, `heading`, `proximity_alert_radius`, `reply_markup`.
