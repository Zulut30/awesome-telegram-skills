# Карта библиотек

Проверка источников: 2 октября 2026 года. Названия не являются жесткими version pins.

| Роль | Кандидаты и первичные источники |
| --- | --- |
| Python Bot API, async | [aiogram](https://docs.aiogram.dev/en/latest/), [python-telegram-bot](https://docs.python-telegram-bot.org/en/stable/) |
| Существующий TeleBot / sync или async | [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI) |
| Авторизованный пользовательский клиент Python | [Telethon](https://docs.telethon.dev/en/stable/) |
| Официальная клиентская библиотека Telegram | [TDLib](https://core.telegram.org/tdlib); Python binding проверяется отдельно |
| Старый MTProto-проект | [Pyrogram](https://docs.pyrogram.org/): оригинальный проект сообщает, что больше не поддерживается |
| Mini App TypeScript | [native WebApp bridge](https://core.telegram.org/bots/webapps) либо wrapper выбранного проекта; проверять поддержку пакета |
| Асинхронная обертка Crypto Pay от сообщества | [aiocryptopay](https://github.com/layerqa/aiocryptopay); API источника истины — Crypto Pay |
| ЮKassa Python SDK от поставщика | [yookassa-sdk-python](https://github.com/yoomoney/yookassa-sdk-python) |
| Platega SDK | [официальная страница SDK](https://docs.platega.io/sdk-1991993m0); проверять скачиваемый пакет и альтернативу HTTPS API |

Прямой HTTP-клиент может быть достаточным для небольшого provider adapter. FSM storage, БД и очередь выбираются по требованиям состояния и доставки, а не устанавливаются всем набором.
