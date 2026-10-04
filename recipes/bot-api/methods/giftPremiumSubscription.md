# giftPremiumSubscription

[Официальные ограничения](https://core.telegram.org/bots/api#giftpremiumsubscription). SDK: aiogram 3.31.0 / GiftPremiumSubscription.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'user_id': 1, 'month_count': 1, 'star_count': 1}
request = build_request("giftPremiumSubscription", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `user_id`, `month_count`, `star_count`.

Все параметры официального снимка: `user_id`, `month_count`, `star_count`, `text`, `text_parse_mode`, `text_entities`.
