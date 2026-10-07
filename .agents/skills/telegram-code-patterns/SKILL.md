---
name: telegram-code-patterns
description: "Подбирает и подключает готовые компоненты общей библиотеки для Telegram-бота или Mini App: импорты Python/TypeScript, совместимость, композиция и проверка в проекте. Используйте, когда пользователь просит переиспользовать код, подключить библиотеку паттернов или добавить компонент в нее. Не для одиночного исправления handler или кода без этой библиотеки → telegram-bot-python."
license: MIT
metadata:
  version: "0.24.0"
---

# Готовые компоненты Telegram

## Когда использовать

Пользователь просит переиспользовать готовый код: подключить библиотеку паттернов, добавить из нее компонент или изменить саму библиотеку.

## Когда не использовать

Одиночное исправление обработчика или код без этой библиотеки — telegram-bot-python.

## Алгоритм

1. Проверьте, установлены ли `awesome-telegram-patterns` и `@awesome-telegram/patterns` и какая версия. Пакеты локальные (wheel, tarball), не из PyPI или npm. SDK, БД и frontend проекта не меняйте.
2. Найдите намерение задачи в списке и откройте только этот reference. Первый пункт — лишь когда неясно, что за пакет передан и какая версия установлена.
3. Встройте импорты в текущую композицию; права, повтор и долговечный результат обеспечивает приложение по контракту. `validate_init_data` не проверяет права, invoice не выдает доступ.

- [agent-onboarding](references/agent-onboarding.md): неясно, что за пакет передан и какая версия установлена
- [components](references/components.md): контракты компонентов
- [gallery-navigation](references/gallery-navigation.md): рецепт в галерее по задаче
- [recipe-execution](references/recipe-execution.md): требования рецепта, offline-запуск
- [api-reference](references/api-reference.md): публичный символ и его пример
- [starter-selection](references/starter-selection.md): выбор компонентов `init`, dry-run, конфликты
- [quickstart](references/quickstart.md): первый запуск нового бота и Mini App
- [test-environment](references/test-environment.md): живой бот без основного аккаунта
- [doctor](references/doctor.md): предупреждения doctor, ошибки установки, manifest, Node/npm
- [developer-tools](references/developer-tools.md): поиск рецептов в CLI и `run-recipe`
- [keyboard-layouts](references/keyboard-layouts.md): ряды и цвета кнопок
- [keyboard-recipes](references/keyboard-recipes.md): reply-ввод, события, нативные кнопки Mini App (BackButton, MainButton)
- [bot-recipes](references/bot-recipes.md): команды, пагинация, запуск и тесты бота
- [form-recipes](references/form-recipes.md): текстовая форма, повтор отправки
- [dialog-fields](references/dialog-fields.md): число, email, телефон, дата, файл, контакт, геопозиция
- [dialog-restart](references/dialog-restart.md): форма после рестарта
- [message-navigation](references/message-navigation.md): экраны и «назад» в одном сообщении
- [selection-controls](references/selection-controls.md): переключатели, множественный выбор, подтверждение
- [calendar-slots](references/calendar-slots.md): календарь и запись на время
- [message-text](references/message-text.md): entities, экранирование, длинный текст
- [rich-messages](references/rich-messages.md): блоки, таблицы, кнопки, запасной текст
- [ephemeral-messages](references/ephemeral-messages.md): ответ в группе только нажавшему
- [communities](references/communities.md): события и права сообществ
- [stars-subscriptions](references/stars-subscriptions.md): подписка Stars и платный доступ
- [component-texts](references/component-texts.md): английский язык и своя формулировка фраз компонентов
- [bot-api-10-features](references/bot-api-10-features.md): guest, bot-to-bot, live photo, заявки, медиа опросов
- [ptb-adapter](references/ptb-adapter.md): проект на python-telegram-bot
- [media](references/media.md): фото, документы, альбомы, скачивание
- [profiles](references/profiles.md): профили, фото пользователя, оформление бота
- [inline-search](references/inline-search.md): inline-поиск
- [polls](references/polls.md): опросы и quiz
- [platform-operations](references/platform-operations.md): темы, реакции, заявки, Business, stories, gifts, managed bots
- [errors](references/errors.md): ошибки и восстановление
- [extensions](references/extensions.md): свой адаптер storage, transport, provider
- [api-boundaries](references/api-boundaries.md): метод новой версии Bot API, контекст и права
- [maturity](references/maturity.md): зрелость и доказательства проверки
- [service-bot](references/service-bot.md): пример записи и напоминаний
- [shop-example](references/shop-example.md): пример магазина Mini App и Stars
- [group-bot](references/group-bot.md): пример: группа, темы, модерация

## Проверка

Основной и негативный сценарий — через установленный пакет; в ответе назовите компоненты, проверки и оставшуюся работу. Изменяя библиотеку, обновите changelog и проверьте wheel/tarball в отдельном consumer.

## Типичные ошибки

- Пакет ставится из PyPI или npm, хотя он поставляется локально.
- Ради одного компонента читаются все references.
- Компонент считается проверкой прав или выдачей доступа.

## Источники

[Bot API](https://core.telegram.org/bots/api).

Проверено: 2026-10-07, awesome-telegram-patterns 0.24.0, Bot API 10.3, aiogram 3.31.0.
