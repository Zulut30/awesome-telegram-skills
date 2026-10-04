# Примеры дополнительных провайдеров

| Провайдер | Первичные источники и инвариант |
| --- | --- |
| Stripe | [Webhooks](https://docs.stripe.com/webhooks): проверять подпись библиотекой по исходному телу; различать checkout session и состояние выбранной payment/subscription модели |
| Robokassa | [Интерфейс оплаты](https://docs.robokassa.ru/ru/pay-interface), [документация](https://docs.robokassa.ru/ru/quick-start): подписи создания ссылки и Result URL строятся по соответствующей операции и настройкам магазина |
| Любой другой | Начать с официального merchant API и отдельного callback protocol; не подставлять схему Stripe, Crypto Pay или ЮKassa без основания |

Для Telegram проверь [правила цифровых товаров](https://core.telegram.org/bots/payments-stars) и [платежи за физические товары](https://core.telegram.org/bots/payments). Внешний checkout допустим только для соответствующего продуктового сценария; сам adapter не меняет требования платформы.

Состояние документации просмотрено 2 октября 2026 года. Это карта интеграций, а не утверждение о наличии проверенных production adapters в этом наборе.
