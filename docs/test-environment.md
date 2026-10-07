# Тестовое окружение Telegram

Telegram держит отдельное тестовое окружение: в нём можно проверить бота, Mini App и оплату в Telegram Stars, не используя основной аккаунт и рабочего бота. Окружение полностью отделено от основного. Аккаунт, бот, токен, чаты и сообщения там свои, токен основного бота не действует. Лимиты на частоту запросов там не выше, а иногда строже.

## 1. Тестовый аккаунт

Войдите в тестовое окружение официальным клиентом:

- **iOS:** 10 раз нажмите на иконку «Настройки» → Accounts → Login to another account → Test.
- **Telegram Desktop:** ☰ Settings → Shift + Alt + правый клик по «Add Account» → Test Server.
- **macOS:** 10 раз нажмите на иконку «Настройки», откроется Debug Menu; затем ⌘ + клик по «Add Account» и вход по номеру телефона.

Это отдельная регистрация. Основной аккаунт остаётся в клиенте как есть.

## 2. Тестовый бот

В тестовом аккаунте откройте @BotFather и создайте нового бота командой `/newbot`. Полученный токен работает только в тестовом окружении.

## 3. Запуск

Запросы к тестовому окружению идут на `https://api.telegram.org/bot<token>/test/METHOD_NAME`. Библиотека включает этот адрес переменной `TELEGRAM_TEST_ENVIRONMENT`: значения `1`, `true`, `yes`, `on` включают тестовое окружение, `0`, `false`, `no`, `off` или отсутствие переменной оставляют основное. Как и BOT_TOKEN, её можно задать в окружении процесса или в `.env` проекта, созданного `telegram-patterns init`:

```dotenv
BOT_TOKEN=123456789:токен_тестового_бота
TELEGRAM_TEST_ENVIRONMENT=1
```

```bash
.venv/bin/python app.py
```

```powershell
.\.venv\Scripts\python.exe app.py
```

`BotSettings.from_env()` читает флаг в `settings.test_environment`. Флаг учитывают `run_bot` и `create_bot`: без явной session они создают `AiohttpSession(api=aiogram.client.telegram.TEST)`. Свою session создайте с `api=TEST` сами — библиотека её не переписывает и отклоняет session основного окружения. Если тестовое окружение отклонило токен, `run_bot` сообщает, что нужен бот из тестового @BotFather.

Примеры [service-bot](service-bot.md), [group-bot](group-bot.md) и [shop](shop-example.md) читают тот же флаг из окружения процесса:

```bash
BOT_TOKEN=... TELEGRAM_TEST_ENVIRONMENT=1 .venv/bin/telegram-service-example --database ~/service-data/test.sqlite
```

Для тестового окружения держите отдельную базу: записи, пользователи и чаты тестового бота не совпадают с основными.

Если бот уже написан на aiogram без библиотеки, достаточно передать session:

```python
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TEST

bot = Bot(token, session=AiohttpSession(api=TEST))
```

## 4. Проверка

```bash
.venv/bin/python -m telegram_patterns doctor . --webhook --expect polling
```

`doctor --webhook` учитывает `TELEGRAM_TEST_ENVIRONMENT`: проверка `telegram-environment` показывает выбранное окружение, а `getWebhookInfo` уходит на `/test/`. Отклонённый токен в тестовом окружении — почти всегда токен основного бота.

## Mini App и оплата

- В тестовом окружении Mini App можно открыть по HTTP-ссылке без TLS. Для основного окружения HTTPS по-прежнему обязателен.
- initData проверяется токеном тестового бота: подпись основного бота там не совпадёт.
- Оплату в Telegram Stars можно свободно проверить, подключив бота к тестовому окружению. Заказы и доступы тестового бота храните отдельно от рабочих.
- Меню вложений (attachment menu) в основном окружении доступно только крупным рекламодателям, а в тестовом — всем ботам.

## Что это не заменяет

Тестовое окружение подтверждает поведение Bot API и клиентов, но не нагрузку, не настройки рабочего бота и не реальные платежи. Перед выпуском повторите ключевой сценарий на рабочем боте и в клиентах, которыми пользуются ваши пользователи.

Сверено 2026-10-07: [Testing your bot](https://core.telegram.org/bots/features#testing-your-bot), [Using bots in the test environment для Mini Apps](https://core.telegram.org/bots/webapps#using-bots-in-the-test-environment), [Telegram Stars: тестирование](https://core.telegram.org/bots/payments-stars), установленный aiogram 3.31.0 (`aiogram.client.telegram.TEST`, `AiohttpSession(api=...)`) и [aiogram: custom API server](https://docs.aiogram.dev/en/latest/api/session/custom_server.html).
