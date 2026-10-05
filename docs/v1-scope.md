# Поддерживаемые сценарии и границы версии 1.0

Это спецификация целевого выпуска из [100 пунктов](library-roadmap-100.md), а не обещание готовности текущей библиотеки. Все 100 пунктов остаются задачами реализации. Закрытие пункта требует предусмотренного им результата и доказательств; статуса `experimental` недостаточно, чтобы объявить незавершенную работу выполненной.

## Для кого и как подключать

Разработчик или ИИ подключает минимальный набор публичных Python/TypeScript компонентов к существующему проекту. Python обслуживает бота и backend, TypeScript — Mini App. Новый Python-бот без иных предпочтений начинается с aiogram; подключение к уже существующему SDK, frontend и storage сохраняет их. Ядро не требует Telegram SDK, web framework или внешнего сервиса. Адаптеры подключаются по сценарию.

Два пакета независимы при выполнении: `awesome-telegram-patterns` / `telegram_patterns` и `@awesome-telegram/patterns`. Совместный starter проверяет согласованность используемых артефактов. Пока доступна локальная поставка, не установка по имени из PyPI/npm. Навык переносится целым каталогом и не требует соседних навыков.

## Карта пользовательских сценариев

| Сценарий / задача | Компоненты и обязанности библиотеки | Точка входа сейчас | Приемка сценария для 1.0 |
| --- | --- | --- | --- |
| Начать проект и выбрать рецепт | Catalog, CLI recipes/init/doctor, dry-run и локальные artifacts | [CLI review](developer-tools-review.md), [gallery](../gallery/index.html) | Новый consumer запускает offline пример; существующие файлы не перезаписаны; диагностика помогает исправить проблему, не раскрывая секреты |
| Каталог и действия в личном чате | Команды, клавиатуры, пагинация, навигация, callbacks | [bot.py](../examples/python/bot.py), [offline_bot.py](../examples/python/offline_bot.py) | Основной live путь, повтор, чужой actor, устаревшая кнопка и отмена; ACK отделен от успеха операции |
| Кнопки, reply-ввод и Telegram events | Native rows, разрешенные стили, emoji fallback, prompt correlation и Update handlers | [keyboards_bot.py](../examples/python/keyboards_bot.py), [offline_keyboards.py](../examples/python/offline_keyboards.py) | Строки 2/3/смешанной ширины, контекстные ограничения, отказ capability, проверка actor/chat/prompt; события не обещают недоступные read receipts |
| Заявка и многошаговая форма | Поля, validation, back/cancel/review, operation identity и durable state | [form_bot.py](../examples/python/form_bot.py), [offline_form.py](../examples/python/offline_form.py) | Перезапуск на каждом шаге, конкурентные отправки, потерянный ответ и сверка той же заявки; значение формы не стирается при исправимой ошибке |
| Запись и уведомления | Calendar, timezone, server slot validation, jobs и unsubscribe | [сервисный бот](service-bot.md): file SQLite FSM, booking/replay и напоминание; live эксплуатация отдельно | Конкурентная запись на слот, restart jobs, rate limits, отписка и прекращение доставки постоянным отказам |
| Сообщения, медиа, inline mode, опросы и профили | Безопасный текст, UTF-16 entities, файлы/альбомы, поиск, poll events и доступные поля | [API request catalog](../recipes/bot-api/README.md) — request construction | Реальные заявленные workflows, формат/размер/rights ошибки, отсутствующие поля и private results; каталог имен отдельно от реализации |
| Группы, каналы и специальные режимы | Rights-aware moderation, join requests, topics, Business и сценарии актуальных special APIs | [Bot API catalog](../catalog/telegram-capabilities.json); групповой пример еще предстоит реализовать | Проверки прав, chat/context, конкурентных действий и разрешенного доступа; workflow, версия и evidence каждого специального модуля указаны явно |
| Бот + Mini App + backend | Проверка запуска, session, object ACL, shared services и deep links | [initData](../packages/python/src/telegram_patterns/initdata.py); [Mini App example](../examples/mini-app/) использует mock backend | Полный signed launch → session → разрешенная операция; чужой объект, forged/stale initData, account switch и revoke отклоняются сервером |
| Каталог, корзина и другие экраны Mini App | Domain/state/API separation, UI components, themes, accessibility и responsive layouts | [TypeScript example](../examples/mini-app/src/index.ts), [shell](../packages/typescript/src/shell.ts) | Телефон/планшет/ПК, обе темы, длинный текст/zoom, клавиатура, back, error/empty/loading и сохранение ввода; реальные клиентские версии зафиксированы |
| Native Mini App capabilities | Typed adapters, version/platform/context gates, permissions, cancellation и cleanup | [native-recipes.ts](../examples/mini-app/src/native-recipes.ts) и [native index](../recipes/mini-app/README.md) | Успех/отказ/нет поддержки в доступных реальных клиентах; invoice callback, biometrics и storage не считаются серверной авторизацией |
| Плохая сеть и неизвестный исход | ApiClient, scoped draft, durable pending identity и reconciliation | [ApiClient](../packages/typescript/src/api-client.ts), [draft](../packages/typescript/src/selection-draft.ts) | Потерянный ответ после effect и reload не создают новый заказ; pending ID живет отдельно от draft TTL; повторное чтение состояния завершает понятный UI |
| Оплата и доступ | Общая модель заказа, разрешенные routes, provider verification, refund и access ledger | Сейчас `stars_invoice` строит request; полноценные Stars/Crypto Pay/Platega/ЮКасса workflows предстоят | Подтвержденный server payment, неверная сумма/получатель, duplicate/out-of-order/unknown outcome, поддерживаемые возвраты и expiry; отдельные provider contracts/sandbox |
| Эксплуатация и доставка | Inbox/outbox, retry policy, shutdown, telemetry, artifacts, migrations и runbooks | [проверка поставки](../scripts/verify_pattern_packages.py); durable inbox/outbox еще предстоят | Fault/restart checks, target environment, backup/restore/rollback, чистый consumer точного wheel/tarball и правила сопровождения |

## Общие границы ответственности

- Библиотека дает готовые механизмы и композиции. Проект владеет бизнес-правилами, secrets, identity/session policy, объектными правами, инфраструктурой и выбором storage; примеры 1.0 должны показать выполнение этих обязанностей.
- Bot API не читает произвольную историю чатов пользовательского аккаунта. MTProto — отдельный явно поставленный сценарий со своим подключением и scope, без скрытой замены Bot API.
- Подписанный launch не разрешает любой заказ. Callback ACK не подтверждает бизнес-effect. Создание invoice и закрытие платежного окна не подтверждают оплату. Клиентские поля не задают цену и права.
- Сохраненный локальный effect не обещает exactly-once доставку по сети. После потерянного ответа опасная операция сверяется по сохраненному operation ID; graceful shutdown и AbortController не доказывают отмену server effect.
- Framework-specific, storage-specific и provider-specific код опционален. Наличие helper не требует миграции существующего приложения или обязательного Redis/Postgres.
- Browser/device evidence относятся к конкретному сценарию, окружению и версии. Отсутствующие устройства/секреты или недоступный sandbox отмечаются как непроверенные условия, а не как PASS.

## Как принимается работа

Для каждого сценария нужны публичный API, runnable consumer example, существенные negative/failure checks, актуальные права и источники, а также синхронизированные exports/catalog/changelog/инструкции. До объявления stable проверяются заявленная support matrix, конкретные artifacts, критические live пути и нерешенные ограничения.

Критерии интерфейса Mini Apps: основной action достижим с экранной клавиатурой; back/resize/theme/resume не стирают ввод; loading завершается понятным состоянием; touch и keyboard доступны на целевых устройствах. Для денег и доступа дополнительный критерий — подтвержденное серверное состояние с проверенными переходами, дублями и восстановлением.

Каждый завершенный пункт плана получает отдельный Git-коммит. [Регистр выполнения](v1-progress.json) хранит весь список из 100 пунктов, статус, измененные artifacts и подтверждающие проверки. Незавершенные пункты остаются pending/in_progress; механическая проверка формата не заменяет приемку поведения.
