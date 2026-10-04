# refundStarPayment

[Официальные ограничения](https://core.telegram.org/bots/api#refundstarpayment). SDK: aiogram 3.31.0 / RefundStarPayment.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'user_id': 1, 'telegram_payment_charge_id': 'FIXTURE_REPLACE'}
request = build_request("refundStarPayment", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `user_id`, `telegram_payment_charge_id`.

Все параметры официального снимка: `user_id`, `telegram_payment_charge_id`.
