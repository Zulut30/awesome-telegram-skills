# Crypto Pay: протокол

Термины: **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

Первичный источник: [Crypto Pay API](https://help.send.tg/en/articles/10279948-crypto-pay-api). Старая [страница](https://help.crypt.bot/crypto-pay-api) перенаправляет к этой документации. 2 октября 2026 года прямое чтение новой страницы вернуло HTTP 403; содержимое доступно через индексированную официальную страницу, снимок которой старше текущей даты. Перед live-интеграцией повторно проверьте текущую схему и retry policy.

- Mainnet: `https://pay.crypt.bot/api/`; testnet: `https://testnet-pay.crypt.bot/api/`.
- Авторизация: `Crypto-Pay-API-Token` в запросе, не в публичном frontend.
- Создание и сверка: `createInvoice`, `getInvoices`; сохранять `invoice_id`. Для пользовательского перехода выбирать актуальный invoice URL, не deprecated `pay_url`.
- Webhook `invoice_paid`: поле `update_id` не уникально.
- `crypto-pay-api-signature`: hex HMAC-SHA256 по исходным байтам тела. Ключ — байты SHA256 app token. JSON parsing/reserialization до проверки может изменить подписанное тело. Сравнение — constant time.
- `request_date` проверяется с учетом реальной задержки доставки; reconciliation устраняет зависимость от единственного webhook.

Опциональный [aiocryptopay](https://github.com/layerqa/aiocryptopay) — async wrapper сообщества. Сверяйте его модели с API; не считайте наличие метода wrapper доказательством поддержки новой схемы поставщиком.
