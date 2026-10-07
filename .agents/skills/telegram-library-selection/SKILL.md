---
name: telegram-library-selection
description: "Выбирает и проверяет библиотеки Telegram-проекта: Python Bot API, Telethon/TDLib, Mini App SDK и платежные wrappers. Используйте при выборе зависимости или проверке поддержки новой функции. Не для подключения уже выбранной библиотеки паттернов → telegram-code-patterns."
license: MIT
metadata:
  version: "0.24.0"
---

# Выбор библиотек

Сначала установите API-плоскость: Bot API, MTProto, WebApp bridge или API платежного провайдера. Прочитайте [references/libraries.md](references/libraries.md) как карту кандидатов, а не обязательный список установки.

Для существующего проекта сохраняйте выбранную библиотеку. Сопоставьте нужные методы и поля с моделями реально установленной версии, release notes и исходниками. Версия Bot API на сайте не доказывает поддержку SDK.

Для нового проекта оцените async/sync-модель, поддерживаемый Python/runtime, lifecycle, состояние поддержки, release cadence, transport и способ обновления. Выберите одну библиотеку на конкретную роль и обоснуйте ее нужной функцией, а не количеством звезд.

Различайте официальный API, официальный SDK сервиса и wrapper сообщества. Если официальный SDK синхронный, его прямой вызов из async-handler может блокировать процесс: выберите управляемое выполнение или HTTP-клиент согласно проекту.

Проверьте происхождение пакета через документацию и upstream; похожее имя пакета не доказывает принадлежность поставщику. Не устанавливайте непроверенный SDK из поисковой выдачи. Миграция должна учитывать сохраненные sessions, handlers и breaking changes, а не только изменение imports.

Результат: выбор и причина, конкретная совместимая версия, минимальные зависимости, неподдерживаемые функции и проверенная альтернатива. При реализации подтвердите imports, типы и фактическую сериализацию нового поля.

## Источники

[aiogram](https://pypi.org/project/aiogram/), [python-telegram-bot](https://pypi.org/project/python-telegram-bot/), [pyTelegramBotAPI](https://pypi.org/project/pyTelegramBotAPI/), [Telethon](https://pypi.org/project/Telethon/), [Bot API changelog](https://core.telegram.org/bots/api-changelog).

Проверено: 2026-10-07, aiogram 3.31.0, python-telegram-bot 22.8, pyTelegramBotAPI 4.37.0, Telethon 1.45.0 (PyPI).
