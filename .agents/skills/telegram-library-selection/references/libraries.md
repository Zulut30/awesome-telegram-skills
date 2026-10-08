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

Прямой HTTP-клиент может быть достаточным для небольшого адаптера платежного провайдера. Хранилище FSM, БД и очередь выбираются по требованиям состояния и доставки, а не устанавливаются всем набором.

## Снимок для сравнения библиотек Bot API

Данные PyPI и документации на 7 октября 2026 года. Перед выбором перепроверьте их: `pip index versions <пакет>` или страница пакета на PyPI.

| Критерий | aiogram | python-telegram-bot | pyTelegramBotAPI |
| --- | --- | --- | --- |
| Последняя версия и дата | 3.31.0, 26.08.2026 | 22.8, 12.06.2026 | 4.37.0, 21.09.2026 |
| Релизов с 07.10.2025 | 12 | 3 | 9 |
| Модель | только async (asyncio) | async, `Application` с `JobQueue` и `persistence` | sync `TeleBot` и async `AsyncTeleBot` |
| Python | 3.10–3.14 (`<3.15`) | `>=3.10`, классификаторы до 3.15 | `>=3.10` |
| Bot API | 10.3 (`aiogram.__api_version__`) | 10.0 (описание на PyPI) | 10.3 по README репозитория |
| Лицензия | MIT | LGPL-3.0 | GPL-2.0 |
| Состояние диалога | FSM со своими хранилищами (`MemoryStorage`, Redis) | `ConversationHandler` и `persistence` | состояния и хранилища в пакете |

Что значит снимок: aiogram быстрее получает новые поля Bot API, python-telegram-bot отстает на три минорные версии API, но имеет встроенные `JobQueue` и `persistence`. Ни одна строка не заменяет проверку нужного метода в установленной версии.

Telethon 1.45.0 (10.09.2026, MIT) — клиент MTProto для пользовательского аккаунта, а не замена Bot API. Pyrogram больше не поддерживается автором. ЮKassa: официальный пакет `yookassa` 3.13.0 (06.10.2026), синхронный. Crypto Pay: `aiocryptopay` 0.4.8 (04.07.2025) — обертка сообщества, не поставщика.
