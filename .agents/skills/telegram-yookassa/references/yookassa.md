# ЮKassa: протоколы

Термины: **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

Проверено 2 октября 2026 года.

- [Прямой API](https://yookassa.ru/developers/using-api/interaction-format): `https://api.yookassa.ru/v3/`, HTTP Basic с shop ID и secret key; header `Idempotence-Key` для POST/DELETE по контракту метода. Повтор одного логического запроса использует прежний ключ и параметры в документированном окне идемпотентности.
- [Быстрый старт](https://yookassa.ru/developers/payment-acceptance/getting-started/quick-start): создание payment, confirmation URL, server-side статус; выбранная схема capture влияет на момент завершения.
- [Уведомления](https://yookassa.ru/developers/using-api/webhooks): `payment.succeeded`, `payment.waiting_for_capture`, `payment.canceled`, `refund.succeeded`. Подлинность проверять по текущему статусу объекта и/или IP согласно документации. Универсальная signature header не документирована здесь.
- [SDK](https://yookassa.ru/developers/using-api/using-sdks), [Python SDK](https://github.com/yoomoney/yookassa-sdk-python): проверьте sync execution и thread safety конкретной версии.
- [API reference](https://yookassa.ru/developers/api): capture, cancel, refunds, сохраненные методы и параметры чеков читать только по задаче.

При Telegram provider invoice используйте [Bot Payments](https://core.telegram.org/bots/payments): backend получает соответствующее Telegram payment event. Для прямого payment — событие и статус ЮKassa. Не смешивайте оба подтверждения в один независящий от маршрута handler.

Повторная сверка 3 октября 2026 года: ЮKassa сохраняет идемпотентность 24 часа после первого запроса, затем запрос со старым ключом считается новым. Сохраняйте время первой попытки и provider object ID, если он получен. После истечения окна не повторяйте неизвестную финансовую операцию вслепую ни со старым, ни с новым ключом; сначала сверяйте доступное состояние, а при невозможности установите `unknown` и предусмотренный путь разбирательства. Локальная защита выдачи и запись attempts нужны независимо от этого окна.
