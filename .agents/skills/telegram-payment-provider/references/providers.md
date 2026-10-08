# Примеры дополнительных провайдеров

Это карта интеграций, а не утверждение о готовых проверенных адаптерах в этом наборе. Документация Robokassa и Stripe перечитана 7 октября 2026 года; перед реализацией откройте ее снова — поля и формулы подписи меняются.

| Провайдер | Первичные источники и инвариант |
| --- | --- |
| Stripe | [Webhooks](https://docs.stripe.com/webhooks), [Idempotent requests](https://docs.stripe.com/api/idempotent_requests): подпись проверяется библиотекой по исходному телу; checkout session и состояние выбранной модели оплаты или подписки различаются |
| Robokassa | [Интерфейс оплаты](https://docs.robokassa.ru/ru/pay-interface), [Уведомления](https://docs.robokassa.ru/ru/notifications-and-redirects), [XML-интерфейсы](https://docs.robokassa.ru/ru/xml-interfaces), [API возвратов](https://docs.robokassa.ru/ru/refund-api), [Холдирование](https://docs.robokassa.ru/ru/holding), [Тестовый режим](https://docs.robokassa.ru/ru/testing-mode) |
| Любой другой | Начните с официального API для магазинов и отдельного протокола уведомлений; не подставляйте схему Stripe, Crypto Pay или ЮKassa без основания |

## Robokassa

| Метод адаптера | Robokassa |
| --- | --- |
| `create_payment` | Ссылка или форма на `https://auth.robokassa.ru/Merchant/Index.aspx` с `SignatureValue` и уникальным `InvId` |
| `fetch_status` | `OpStateExt`; в тестовом режиме не работает. `Result.Code` 0 — запрос обработан; состояние в `State.Code`: 5 — создана, не оплачена; 10 — отменена, денег нет; 20 — холдирование; 50 — деньги получены, идет зачисление; 60 — отказ в зачислении, деньги возвращены; 80 — приостановлена; 100 — оплачена. Выдача — только при 100 |
| `parse_notification` | ResultURL: подпись с паролем #2, ответ `OK{InvId}` |
| `refund` | `Refund/Create` в API возвратов: JWT с `Password3` и `OpKey` операции, полный или частичный возврат |
| `cancel` | Только для холдирования (`StepByStep=true`, до 7 дней): `Merchant/Payment/Cancel`; списание — `Merchant/Payment/Confirm`, уведомление о предавторизации — на ResultURL2. Обычный платеж не отменяется, только возвращается |

- **Ссылка на оплату.** `SignatureValue` — хеш строки `MerchantLogin:OutSum:InvId:<модификаторы>:Пароль#1:<Shp_*>`. Модификаторы (например, `Receipt` для чека) идут в порядке из документации, параметры `Shp_*` — после пароля, строго по алфавиту, в виде `Shp_key=value`, с учетом регистра. Алгоритм хеша (по умолчанию MD5) задан в технических настройках магазина. `InvId` уникален для каждой оплаты: повтор номера дает ошибку 40.
- **Уведомление ResultURL.** Подпись — хеш `OutSum:InvId:Пароль#2[:Shp_*]`, без `MerchantLogin`; шестнадцатеричная строка сравнивается без учета регистра. `OutSum` для подписи берите строкой как пришла: в рабочем режиме у суммы шесть знаков после точки, в тестовом — два; сумму с заказом сравнивайте как `Decimal`. После проверки и сохранения ответьте текстом `OK{InvId}` (например, `OK5`); иначе уведомление считается непринятым.
- **Статус и возврат.** Статус счета — `OpStateExt` (подпись `MerchantLogin:InvoiceID:Пароль#2`); в тестовом режиме метод не работает. Возврат — `Refund/Create` в API возвратов: JWT, подписанный `Password3`, с `OpKey` операции из `OpStateExt` или уведомления `Result2`.
- **Тестовый режим.** `IsTest=1` и отдельный набор тестовых паролей #1 и #2; рабочие пароли в тесте не подходят.

Проверка подписи ResultURL на Python:

```python
import hashlib
import hmac


def robokassa_result_valid(params: dict[str, str], password2: str, algorithm: str = "md5") -> bool:
    shp = sorted((key, value) for key, value in params.items() if key.startswith("Shp_"))
    base = ":".join([params["OutSum"], params["InvId"], password2, *(f"{key}={value}" for key, value in shp)])
    expected = hashlib.new(algorithm, base.encode()).hexdigest()
    return hmac.compare_digest(expected.upper(), params.get("SignatureValue", "").upper())
```

Пример из документации: `OutSum=100.000000`, `InvId=450009`, `Shp_login=Vasya`, `Shp_oplata=1` дают строку `100.000000:450009:Пароль#2:Shp_login=Vasya:Shp_oplata=1`.

## Stripe

- **Уведомления.** Подпись — заголовок `Stripe-Signature` и секрет `whsec_...` конечной точки; проверяйте `stripe.Webhook.construct_event(payload, signature, endpoint_secret)` по сырому телу запроса, до разбора JSON. Ответ 2xx — быстро, до тяжелой логики.
- **Порядок и дубли.** Stripe не гарантирует порядок событий и может доставить событие повторно: храните обработанные ID событий (`evt_...`), не определяйте порядок по полю `created`, недостающее состояние запрашивайте через API.
- **Создание платежа.** Заголовок `Idempotency-Key` до 255 символов, без личных данных; ключ можно повторить в течение как минимум 24 часов, повтор с другими параметрами вернет ошибку.
- **Смена секрета.** Старый секрет может действовать до 24 часов параллельно с новым — проверка должна принимать оба на это время.

## Правила Telegram

Для цифровых товаров проверьте [правила Stars](https://core.telegram.org/bots/payments-stars), для физических — [Bot Payments](https://core.telegram.org/bots/payments). Внешняя оплата допустима только в подходящем продуктовом сценарии; сам адаптер не меняет требования платформы.
