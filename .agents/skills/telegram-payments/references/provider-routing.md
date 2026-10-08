# Маршрутизация платежей

Термины: **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

Для цифровых товаров и услуг внутри Telegram используется Stars согласно [официальным правилам](https://core.telegram.org/bots/payments-stars). Наличие Crypto Pay, ЮKassa или внешнего сайта не отменяет это требование. Для физических товаров и соответствующих услуг смотрите [Bot Payments](https://core.telegram.org/bots/payments).

| Выбранная интеграция | Следующая ветка |
| --- | --- |
| Stars или Telegram provider invoice | payment-flows.md этого навыка |
| CryptoBot / Crypto Pay | Специализированный навык `telegram-cryptopay`, если доступен; [API](https://help.send.tg/en/articles/10279948-crypto-pay-api) |
| Platega.io | `telegram-platega`, если доступен; [документация](https://docs.platega.io/) |
| ЮKassa | `telegram-yookassa`, если доступен; [документация](https://yookassa.ru/developers/api) |
| Stripe, Robokassa, другой провайдер | `telegram-payment-provider`, если доступен; проверить официальный API конкретной платежки |

Другие навыки опциональны: этот каталог должен переноситься самостоятельно. Без них используйте первичные источники выбранного API и сохраняйте server-side order, проверку подлинности, сверку суммы/валюты и однократную выдачу.
