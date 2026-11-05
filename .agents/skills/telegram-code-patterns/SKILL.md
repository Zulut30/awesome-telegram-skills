---
name: telegram-code-patterns
description: "Подбирает и подключает готовые компоненты общей библиотеки для Telegram-бота или Mini App: импорты Python/TypeScript, совместимость, композиция и проверка в проекте. Используйте, когда пользователь просит переиспользовать код, подключить библиотеку паттернов или добавить компонент в нее. Не для одиночного исправления handler или кода без этой библиотеки → telegram-bot-python."
license: MIT
metadata:
  version: "0.28.0"
---

# Готовые компоненты Telegram

## Когда использовать

Подключение или изменение компонентов библиотеки.

## Когда не использовать

Одиночное исправление обработчика или код без этой библиотеки — telegram-bot-python.

## Алгоритм

1. Проверьте версию `awesome-telegram-patterns`/`@awesome-telegram/patterns`. Установите локальные wheel/tarball; сохраните SDK, БД и frontend.
2. Выберите задачу и откройте reference. Неясны пакет/версия — начните с agent-onboarding.
3. Подключите импорты; приложение обеспечивает права, безопасный повтор и сохранение результата. `validate_init_data` не проверяет права; invoice не выдает доступ.

- [agent-onboarding](references/agent-onboarding.md): пакет и установленная версия
- [components](references/components.md): контракты компонентов
- [gallery-navigation](references/gallery-navigation.md): рецепт в галерее по задаче
- [recipe-execution](references/recipe-execution.md): требования и офлайн-запуск
- [api-reference](references/api-reference.md): публичный символ и его пример
- [starter-selection](references/starter-selection.md): `init`, предварительный просмотр, конфликты
- [quickstart](references/quickstart.md): первый запуск нового бота и Mini App
- [test-environment](references/test-environment.md): тестовый бот
- [doctor](references/doctor.md): установка и диагностика
- [developer-tools](references/developer-tools.md): поиск рецептов в CLI и `run-recipe`
- [keyboard-layouts](references/keyboard-layouts.md): ряды и цвета кнопок
- [keyboard-recipes](references/keyboard-recipes.md): reply, `BackButton`/`MainButton`
- [bot-recipes](references/bot-recipes.md): команды, пагинация, запуск и тесты бота
- [form-recipes](references/form-recipes.md): текстовая форма, повтор отправки
- [dialog-fields](references/dialog-fields.md): типизированный ввод
- [dialog-restart](references/dialog-restart.md): форма после рестарта
- [message-navigation](references/message-navigation.md): экраны одного сообщения
- [selection-controls](references/selection-controls.md): переключатели, множественный выбор, подтверждение
- [calendar-slots](references/calendar-slots.md): календарь и запись на время
- [message-text](references/message-text.md): entities, экранирование, длинный текст
- [rich-messages](references/rich-messages.md): блоки, таблицы, кнопки, запасной текст
- [ephemeral-messages](references/ephemeral-messages.md): ответ в группе только нажавшему
- [communities](references/communities.md): события и права сообществ
- [stars-subscriptions](references/stars-subscriptions.md): подписка Stars и платный доступ
- [component-texts](references/component-texts.md): язык и формулировки
- [framework-adapters](references/framework-adapters.md): React, Vue и Svelte
- [bot-api-10-features](references/bot-api-10-features.md): guest, bot-to-bot, live photo, заявки, медиа опросов
- [ptb-adapter](references/ptb-adapter.md): python-telegram-bot
- [media](references/media.md): фото, документы, альбомы, скачивание
- [profiles](references/profiles.md): профили, фото пользователя, оформление бота
- [inline-search](references/inline-search.md): inline-поиск
- [polls](references/polls.md): опросы и quiz
- [platform-operations](references/platform-operations.md): темы, реакции, заявки, Business, истории, подарки, дочерние боты
- [errors](references/errors.md): ошибки и восстановление
- [concurrent-actions](references/concurrent-actions.md): конкуренция и текущие права
- [durable-inbox](references/durable-inbox.md): прием до ответа, рестарт, карантин
- [webhook-receiver](references/webhook-receiver.md): надежный HTTP-прием
- [retry-policy](references/retry-policy.md): чтение, безопасный повтор и неизвестный внешний эффект
- outbox — намерение отправки в бизнес-транзакции: [контракт](references/transactional-outbox.md)
- [durable-jobs](references/durable-jobs.md): расписание, отписка, ограничения, отмена
- [worker-lifecycle](references/worker-lifecycle.md): остановка и закрытие ресурсов
- [safe-telemetry](references/safe-telemetry.md): корреляция и метрики без секретов
- [mini-app-state](references/mini-app-state.md): запросы, черновик и незавершенная операция
- [mini-app-ui](references/mini-app-ui.md): токены, формы, модальные состояния
- [native-flows](references/native-flows.md): кнопки, разрешения, хранилища
- [payment-ledger](references/payment-ledger.md): суммы, возвраты, доступ
- [payment-providers](references/payment-providers.md): Crypto Pay, Platega, ЮKassa
- [stars-payments](references/stars-payments.md): возврат Stars
- [sqlite-recovery](references/sqlite-recovery.md): копия SQLite, восстановление
- [extensions](references/extensions.md): собственный адаптер
- [api-boundaries](references/api-boundaries.md): новые методы, контекст, права
- [maturity](references/maturity.md): зрелость и доказательства проверки
- [service-bot](references/service-bot.md): пример записи и напоминаний
- [shop-example](references/shop-example.md): пример магазина Mini App и Stars
- [group-bot](references/group-bot.md): модерация

## Проверка

Основной и негативный сценарии проверяйте через установленный пакет. Назовите результат и ограничения. При изменении библиотеки обновите changelog, проверьте wheel/tarball отдельно.

## Типичные ошибки

- Пакет ставится из PyPI или npm, хотя он поставляется локально.
- Ради одного компонента читаются все references.
- Компонент считается проверкой прав или выдачей доступа.

## Источники

[Bot API](https://core.telegram.org/bots/api).

Проверено: 2026-11-05, контракты awesome-telegram-patterns 0.28.0, Bot API 10.3, aiogram 3.31.0.
