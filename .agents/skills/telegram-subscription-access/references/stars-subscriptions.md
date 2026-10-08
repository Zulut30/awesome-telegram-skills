# Подписки Telegram Stars

Термины: **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

Ежемесячная подписка Stars создается ссылкой на счет [createInvoiceLink](https://core.telegram.org/bots/api#createinvoicelink) с `currency="XTR"` и `subscription_period=2592000` — сейчас Telegram принимает только 30 дней, цена не выше 10000 Stars. У одного пользователя может быть несколько подписок одновременно, поэтому подписку называет пара «пользователь + `invoice_payload`»: делайте payload уникальным для пользователя и тарифа.

## События и что они значат для доступа

| Событие | Что приходит | Влияние на доступ |
| --- | --- | --- |
| Списание (первое и каждое продление) | сообщение с [SuccessfulPayment](https://core.telegram.org/bots/api#successfulpayment): `is_recurring`, `is_first_recurring`, `subscription_expiration_date`, `telegram_payment_charge_id` | дает период `[дата сообщения, subscription_expiration_date)`; повтор того же charge ничего не продлевает |
| Пользователь отменил продление | update `subscription` — [BotSubscriptionUpdated](https://core.telegram.org/bots/api#botsubscriptionupdated) со `state="canceled"` | оплаченный период сохраняется до конца, следующего списания не будет |
| Пользователь снова включил продление | `state="active"` | ожидается следующее списание |
| Оплата продления не прошла | `state="failed"` | оплаченный период сохраняется до конца; новый период появится только с новым `SuccessfulPayment` |
| Возврат | сообщение с [RefundedPayment](https://core.telegram.org/bots/api#refundedpayment) | снимается период только этого charge |

`BotSubscriptionUpdated` (Bot API 10.2+) содержит `user`, `invoice_payload` и `state` — без даты и без charge. Он не продлевает и не обрывает оплаченное время: срок задают только списания и возвраты. Если боту когда-либо задавали явный `allowed_updates`, добавьте в него `subscription`: без параметра Telegram оставляет прошлую настройку. В aiogram `dispatcher.resolve_used_update_types()` включает `subscription`, когда есть обработчик `router.subscription()`. Бот может сам отменить продление методом [editUserStarSubscription](https://core.telegram.org/bots/api#edituserstarsubscription) (`is_canceled=True`): подписка должна работать до конца текущего периода; `is_canceled=False` снова включает только отмененное ботом.

## С библиотекой awesome-telegram-patterns

`StarsSubscription` из SDK-free ядра хранит списания одной подписки и отвечает, есть ли доступ сейчас:

```python
from telegram_patterns import StarsSubscription, SubscriptionEventRejected

sub = await load(user_id, payload) or StarsSubscription(user_id, payload)
try:
    sub = sub.record_payment(message.successful_payment.model_dump(), user_id=user_id,
                             paid_at=int(message.date.timestamp()))
except SubscriptionEventRejected:
    ...  # другой товар, разовая оплата или конфликт charge: ничего не выдано, нужна сверка
await save(sub)  # sub.as_dict() — JSON для строки в базе; StarsSubscription.from_dict читает его обратно

if sub.has_access(time.time()):  # на каждом защищенном действии, без кеша
    ...
```

- `record_update(event.model_dump())` применяет `BotSubscriptionUpdated` и меняет только `renewal` (`pending`, `active`, `canceled`, `failed`); неизвестное состояние отклоняется до сверки.
- `record_refund(refund.model_dump(), user_id=...)` снимает период своего charge; возврат, пришедший раньше платежа, запоминается, и поздний платеж с тем же ID доступа не дает.
- `access_until(now)` — конец непрерывного доступа с учетом продлений, `renews(now)` — ожидается ли следующее списание.
- Событие чужого пользователя или payload, не XTR, разовая оплата и тот же charge с другими данными — `SubscriptionEventRejected` без изменений состояния.

Порядок событий, хранение и сверку проект берет на себя: при сомнении сравните сохраненные charges с [getStarTransactions](https://core.telegram.org/bots/api#getstartransactions) (`TransactionPartnerUser.invoice_payload` и `subscription_period`).

## Проверка

`telegram-patterns run-recipe demo-stars-subscription --offline` выполняет пример на настоящем `Dispatcher` без сети: ссылка на ежемесячный счет, pre-checkout без выдачи доступа, первое списание и продление, повтор charge, отмена с сохранением оплаченного месяца, сбой продления с уведомлением и окончанием доступа, возврат одного месяца и хранение состояния в JSON. Реальные списания, время продления и порядок событий проверяйте на тестовом боте с настоящими Stars.

Источники: [createInvoiceLink](https://core.telegram.org/bots/api#createinvoicelink), [SuccessfulPayment](https://core.telegram.org/bots/api#successfulpayment), [BotSubscriptionUpdated](https://core.telegram.org/bots/api#botsubscriptionupdated), [RefundedPayment](https://core.telegram.org/bots/api#refundedpayment), [editUserStarSubscription](https://core.telegram.org/bots/api#edituserstarsubscription), [TransactionPartnerUser](https://core.telegram.org/bots/api#transactionpartneruser), [Stars payments](https://core.telegram.org/bots/payments-stars). Проверено 7 октября 2026 года по Bot API 10.3 и aiogram 3.31.0.
