# createInvoiceLink

[Официальные ограничения](https://core.telegram.org/bots/api#createinvoicelink). SDK: aiogram 3.31.0 / CreateInvoiceLink.

Это готовый пример **построения запроса** с искусственными данными. Замените FIXTURE значения, идентификаторы и файлы; проверьте права, контекст и ограничения метода перед отправкой. SDK validation не подтверждает прием запроса Telegram.

```python
from aiogram.types import BufferedInputFile
from telegram_patterns.aiogram import build_request

parameters = {'title': 'FIXTURE_REPLACE', 'description': 'FIXTURE_REPLACE', 'payload': 'FIXTURE_REPLACE', 'currency': 'XTR', 'prices': [{'label': 'FIXTURE_REPLACE', 'amount': 1}]}
request = build_request("createInvoiceLink", parameters)
# В async handler текущего проекта после проверки контекста/прав:
# result = await bot(request)
```

Обязательные параметры SDK: `title`, `description`, `payload`, `currency`, `prices`.

Все параметры официального снимка: `business_connection_id`, `title`, `description`, `payload`, `provider_token`, `currency`, `prices`, `subscription_period`, `max_tip_amount`, `suggested_tip_amounts`, `provider_data`, `photo_url`, `photo_size`, `photo_width`, `photo_height`, `need_name`, `need_phone_number`, `need_email`, `need_shipping_address`, `send_phone_number_to_provider`, `send_email_to_provider`, `is_flexible`.
