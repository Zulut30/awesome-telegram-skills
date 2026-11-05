# Надежный прием webhook

Термины: квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта; **outbox** — события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик выполняет их позже; **неизвестный результат** — запрос мог выполниться, но ответа нет (таймаут, обрыв связи); повторять вслепую нельзя, сначала сверка; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

`WebhookReceiver` принимает HTTP body в `SQLiteInbox` без Telegram SDK. `create_aiohttp_webhook_app` — необязательный HTTP adapter: `aiohttp` устанавливает приложение (он также приходит с extra `aiogram`). Core import не требует `aiohttp`. Компоненты пока experimental.

## Контракт приема

1. Host явно вызывает `inbox.initialize()` при подготовке схемы и передает настоящий server-owned `bot_id`, отдельный `secret_token` webhook и лимит тела.
2. Секрет проверяется до JSON/storage через constant-time comparison. HTTP adapter требует ровно один `X-Telegram-Bot-Api-Secret-Token`; секрет не является bot token.
3. Adapter принимает только UTF-8 `application/json` без compression, ограничивает как Content-Length, так и chunked stream и время чтения. По умолчанию лимит 1 MiB, timeout 10 секунд; host задает соответствующий лимит в reverse proxy.
4. Проверяются строгий UTF-8, JSON object, отсутствие повторных JSON keys и нечисловых значений NaN/Infinity, глубина JSON, целочисленный `update_id` и object envelope известного события Bot API 10.3. Полный SDK decode выполняется worker после durable receipt.
5. `200` возвращается только после SQLite COMMIT: принятое событие, тот же повтор или сохраненный карантин. Другой payload/version того же `(bot_id, update_id)` дает `409`; ошибка storage — `503`, без успешного HTTP-ответа. Клиентский timeout после commit оставляет повтор безопасным благодаря inbox identity.

Неизвестное или неоднозначное событие сохраняется атомарно с `unknown-update-kind` и получает `200`; неизвестная **внутренняя версия envelope** — `unsupported-version`. Это наблюдаемый карантин для разбора оператором. Новые поля Bot API не удаляются. Компонент не выпускает карантин автоматически и не пытается угадать бизнес-обработчик. `counts(bot_id)` дает безопасные агрегаты; raw payload доступен только через host-owned storage с контролем доступа и retention.

## Worker и границы

Worker берет fenced claim, декодирует `claim.payload` установленным SDK и после ошибки decode переводит событие в карантин `decode-failed`. Бизнес-операция использует устойчивый operation ID и собственную идемпотентность, например `SQLiteOnce.run_guarded`; затем worker делает `complete`. Истекший claim не дает старому worker завершить событие. Повтор inbox не доказывает exactly-once внешней отправки; HTTP side effects требуют outbox и сверки неизвестного исхода.

Sync SQLite вызывайте через thread boundary в async host. Adapter уже делает `asyncio.to_thread` для приема. Host владеет TLS, socket/process lifecycle, ограничением параллельности, воркерами, сбором метрик и backup. При остановке сначала прекращайте новый HTTP ingress, затем завершайте активные приемы/операции в пределах deadline. Cancellation не откатывает уже запущенный thread: отсутствие HTTP ответа не означает отсутствие receipt.

`create_aiohttp_webhook_app` только создает приложение и POST route; не открывает socket, не вызывает `setWebhook`, `deleteWebhook`, `getUpdates`, не меняет polling и не сбрасывает pending updates. Развертывание и переключение режима host выполняет явно. Не публикуйте loopback fixture как production endpoint.

## Воспроизводимая проверка

После установки wheel с extra `aiogram`:

```powershell
python examples/python/offline_webhook.py
python -m unittest discover -s packages/python/tests -p test_webhook.py -v
```

Fixture поднимает только временный loopback HTTP listener и использует временную SQLite; Telegram и его настройки не затрагиваются. Тесты проверяют реальный HTTP, повторы и изменение данных, неверный или повторный заголовок секрета, лимиты тела, отказ хранения и quarantine после SDK decode error. Это локальная HTTP/SQLite проверка. Доставка от Telegram по публичному HTTPS проверяется отдельно.

## Источники

- [Telegram: Update и setWebhook](https://core.telegram.org/bots/api#setwebhook) — Bot API 10.3, secret header и правила webhook, проверено 5 ноября 2026.
- [aiogram: webhook](https://docs.aiogram.dev/en/latest/dispatcher/webhook.html) — подтверждение до обработки требует собственного надежного приема.
- [aiohttp: Application и request](https://docs.aiohttp.org/en/stable/web_reference.html) — aiohttp 3.14.5, body/HTTP lifecycle.
