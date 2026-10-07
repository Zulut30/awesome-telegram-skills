# Магазин: Mini App, заказ и Telegram Stars

Термины: квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта; **outbox** — события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик выполняет их позже; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

Пример пункта 018 связывает TypeScript-каталог и корзину с Python/aiohttp backend, настоящей SQLite и aiogram 3.31.0. Использует публичные `ApiClient`, `TelegramBridge`, `TelegramNativeAPI`, `createAppShell`, `validate_init_data`, `SQLiteOnce`, `stars_invoice` и `StubSession` библиотеки 0.24.0 (CI проверяет пример на текущей версии). Приложение `awesome-telegram-shop-example` 0.1.0 поставляется отдельно; его классы не public exports библиотеки.

Два учебных цифровых товара стоят 25 и 40 Stars. Backend принимает только IDs, operation UUID и согласие с версией условий. Цена и валюта фиксируются сервером в заказе; клиентские price/user_id/paid поля отклоняются. Данные запуска проходят HMAC/freshness проверку; сервер выдаёт сессионный токен на 10 минут, который frontend хранит только в памяти и передаёт в заголовке `Authorization: Bearer` (почему не cookie — ниже). В production требуются HTTPS и точный origin. `initDataUnsafe` не даёт прав. Получение заказа и материала проверяет владельца из сессии.

Оплата проходит через Stars (`XTR`, пустой provider_token, один price). Счёт связан с owner-scoped заказом. Pre-checkout сверяет bot, пользователя, payload, сумму, валюту, состояние и доступ; ответ не выдаёт товар. Только trusted SDK `successful_payment` атомарно сохраняет receipt, paid и access. Повтор charge не выдаёт доступ второй раз. Второй charge или поздний платёж за уже купленный товар сохраняется для ручной сверки. Публичного HTTP receipt/grant endpoint нет. Invoice callback лишь запускает чтение статуса с backend.

## Установка предоставленных локальных пакетов

Пакеты ещё не опубликованы. В новом окружении:

```powershell
$patternWheel = 'C:\provided\awesome_telegram_patterns-0.24.0-py3-none-any.whl'
$patternTarball = 'C:\provided\awesome-telegram-patterns-0.24.0.tgz'
$shopProject = 'C:\provided\shop'
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install "${patternWheel}[aiogram]" 'aiogram==3.31.0' $shopProject
Push-Location "$shopProject\frontend"
npm.cmd install --save $patternTarball
npm.cmd run build
Pop-Location
```

```bash
PATTERN_WHEEL=~/provided/awesome_telegram_patterns-0.24.0-py3-none-any.whl
PATTERN_TARBALL=~/provided/awesome-telegram-patterns-0.24.0.tgz
SHOP_PROJECT=~/provided/shop
python3 -m venv .venv
.venv/bin/python -m pip install "${PATTERN_WHEEL}[aiogram]" 'aiogram==3.31.0' "$SHOP_PROJECT"
(cd "$SHOP_PROJECT/frontend" && npm install --save "$PATTERN_TARBALL" && npm run build)
```

Install может обращаться к dependency registries. Существующие SDK/БД/frontend сохраняйте: пример показывает контракт приложения, не требует их замены.

## Проверка примера

Из checkout библиотеки, с Chrome или CHROME_PATH:

```bash
python scripts/build_release.py --ref HEAD --output output/release
```

```bash
python scripts/verify_shop_example.py --wheel output/release/awesome_telegram_patterns-0.24.0-py3-none-any.whl --tarball output/release/awesome-telegram-patterns-0.24.0.tgz --output output/shop-check
```

Output должен быть новым. Helper собирает application wheel, устанавливает его с принятым pattern wheel во внешний consumer, копирует frontend и строит его из установленного tarball. Исходники и метаданные, разрешенные origins, Mypy, тесты домена и HTTP и Chrome проверяются отдельно. Loopback HTTP и synthetic initData/SDK updates существуют только в explicit offline fixture; настоящий токен и live entrypoint не используются. Fixture payment control идёт через stdin отдельного процесса, не через публичный HTTP API. Браузер и Python fixture блокируют внешнюю сеть; это не OS sandbox.

## Рабочая конфигурация

После отдельной настройки BOT_TOKEN, проверки, что нет установленного webhook и другого получателя getUpdates, настройки обратного прокси с HTTPS, постоянного локального пути БД, ваших реальных условий и поддержки:

```powershell
& .\.venv\Scripts\telegram-shop-example.exe --database 'C:\shop-data\shop.sqlite' --frontend "$shopProject\frontend\dist" --origin 'https://shop.example.com' --terms 'C:\shop-data\terms.txt' --terms-version '2026-01' --support 'Ваш контакт и порядок обращения к оператору' --port 8080
```

Parent БД должен существовать. Runtime слушает только 127.0.0.1 за вашим HTTPS proxy, владеет OS lock до cleanup HTTP/FSM/session и запускает polling без смены webhook/удаления updates. `/start` в личном чате открывает HTTPS Mini App, `/terms`, `/support`, `/paysupport` доступны пользователю. Production HTML подключает официальный WebApp SDK; обычный браузер показывает каталог и приглашение войти через Telegram. Согласие сохраняется с заказом. Учебные условия нельзя использовать как оферту рабочего магазина.

## Сессия: заголовок вместо cookie

Telegram Web показывает Mini App во фрейме `<iframe>` своего сайта ([методы Mini Apps](https://docs.telegram-mini-apps.com/platform/methods)), поэтому для магазина это сторонний (cross-site) контекст. Cookie `SameSite=Strict` и `Lax` там не отправляются ([Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)); `SameSite=None` требует `Secure`, а сторонние cookie по умолчанию ограничивают Safari (ITP) и Firefox (Total Cookie Protection) ([third-party cookies](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies)). Прежняя cookie `SameSite=Strict` воспроизводимо ломала вход: в Chromium во фрейме с другого сайта `POST /api/session` возвращал 200, cookie не сохранялась, а `POST /api/orders` получал 401.

Поэтому `POST /api/session` возвращает `{token, scope, expires_in}`, а frontend держит токен в переменной модуля и отправляет `Authorization: Bearer <token>`. Браузер не прикладывает такой заголовок сам, поэтому отдельный CSRF-токен не нужен; запись дополнительно требует точный `Origin`. Токен не попадает в localStorage, sessionStorage и cookie; база хранит только его SHA-256. После reload или истечения 10 минут вход повторяется по initData (до часа с запуска). Главный риск такой схемы — XSS: CSP запрещает чужие скрипты, кроме официального SDK. Один способ работает во всех клиентах: в Desktop, iOS и Android Mini App открывается в WebView как страница верхнего уровня, но отдельная ветка для cookie там не нужна.

## Восстановление и границы

Pending operation/cart/terms сохраняются под server-derived scope до POST, отдельно от любой TTL сессии. Если локальное сохранение недоступно, новый заказ не отправляется. Reload проверяет тот же operation ID; 404 допускает явный повтор того же payload/key. Theme, back и resize не пересоздают заказ. Corrupt pending блокирует новый checkout и предлагает историю покупок. Номера в localStorage не разрешают доступ; токен сессии и initData туда не записываются, после reload вход повторяется по initData.

Invoice проходит none → creating → ready. Timeout/invalid response/crash после вызова без сохранённой ссылки дают unknown; новая ссылка автоматически не создаётся. Такой заказ требует сверки. Сохраняется один accepted pre-checkout query на заказ: после неизвестной/прерванной предыдущей оплаты нельзя молча разрешать второй charge. Смена accepted query требует отдельной операторской сверки. Это сознательная граница примера, не полноценный payment orchestration/refund сервис.

Схема SQLite версия 1; corruption/другая схема требуют явной миграции. Один процесс и локальный диск; несколько рабочих процессов, inbox и outbox общего назначения, ограничения частоты, резервные копии, возвраты, chargeback и сверка, мониторинг продакшена и усиление безопасности — отдельные пункты. Памятки демонстрационные, реальные коммерческие материалы должны храниться в защищённом storage проекта. Цифровые товары внутри Telegram не переключаются на внешнюю карточную/крипто оплату.

Приёмка этого примера — установленное приложение, настоящие SQLite/HTTP/процессы, Chrome viewport/theme проверки и покупка во фрейме чужого сайта, как в Telegram Web. Bot transport, launch vectors и native host synthetic; live Telegram/Stars test environment, настоящие клиенты Telegram (Web, Desktop, iOS, Android), физические устройства, screen readers и независимое человеческое удобство не подтверждены. Это experimental example, не объявление production готовности или выпуска 1.0.

Частично сверено 2026-10-05: [Stars digital flow/terms/support](https://core.telegram.org/bots/payments-stars), [createInvoiceLink](https://core.telegram.org/bots/api#createinvoicelink), [SuccessfulPayment](https://core.telegram.org/bots/api#successfulpayment), [Mini App validation](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app), [openInvoice](https://core.telegram.org/bots/webapps#initializing-mini-apps). Остальные даты API/payment каталога не обновляются. Версия SDK проверяется в consumer; подписанный test vector дополнительно проверяет независимый aiogram parser.
