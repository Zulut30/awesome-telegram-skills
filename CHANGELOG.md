# Изменения библиотеки компонентов

## Unreleased — подготовка 1.0

- Пункт 001: определены сценарии и границы 1.0, пользовательские задачи, точки входа и критерии приемки; добавлен регистр выполнения всех 100 пунктов.
- Пункт 002 / исходники 0.6.0: maturity групп и recipes, независимый фильтр RecipeCatalog/CLI/галереи, совместимое чтение старых records и переносимые инструкции. SDK/mock/browser evidence не повышает статус до stable автоматически.
- Пункт 003: полные семантические контракты root/aiogram/testing/CLI и TypeScript exports, включая DTO/types, ошибки, ресурсы и обязанности host.
- Пункт 004: правила SemVer, миграций, неизменности релиза и deprecation stable API (два minor и 90 дней); RC identity различает Python/npm форматы.

## 0.5.0 — 4 октября 2026

Добавлены Recipe/RecipeCatalog и локальная галерея с поиском по 298 рецептам: 11 раскладок/ввода, 185 Bot API requests, 99 справочных Mini App фрагментов и три mock-сценария бота. Галерея показывает код, layout preview и точную область SDK/mock/reference проверки; live evidence не выдумывается.

CLI `telegram-patterns recipes/init/doctor` входит в wheel. `init` создает только новый каталог: минимальный aiogram-бот или бот с TypeScript frontend из согласованных локальных wheel/tarball. Поддерживаются dry-run, offline-сценарий и отказ от перезаписи. `doctor` не читает .env, не выводит token, не запускает проект и не обращается к Telegram. Mini App starter пока содержит локальную форму без backend auth.

Каталог содержит 24 группы; навык переиспользования, exports и шаблоны согласованы. Проверка поставки дополнена установленной CLI, созданными проектами, строгой TS-сборкой и Chrome проверками галереи/стартеров. TypeScript runtime API сохранен; версия пакета синхронизирована. [Контракт и проверка](docs/developer-tools-review.md).

## 0.4.0 — 4 октября 2026

Клавиатуры и библиотека рецептов: explicit inline/reply rows (по две/три и смешанные), styles/emoji fallback, request buttons, input prompt/remove, рабочий demo Router с ACK и owner-bound edit. Тот же Dispatcher проверяется offline. SDK method_catalog/build_request охватывает 185 Bot API методов; generated request-only recipes и индекс 400 типов отмечают границы SDK validation. UpdateObserver/event_router работают с native Update kinds без копирования raw данных.

TypeScript: каталог 99 native функций / 44 событий Mini App, TelegramNativeAPI с availability gates, native callback semantics и cleanup, popup/location recipes. Пакеты и переносимый code-patterns навык синхронизированы; release проверяется через wheel/tarball consumers. [Контракты и доказательства](docs/telegram-cookbook-review.md). Live Telegram/device/provider workflows не подменяются SDK/mock проверкой; поставка локальная.

## 0.3.0 — 3 октября 2026

Добавлены TextField/InvalidField, FormSubmission и text_form_router для текстовых форм в личных чатах aiogram. Поля описываются списком; Router проверяет ввод, сохраняет текущий FSM, поддерживает /back, /cancel и явное подтверждение сводки. SDK event isolation обязательна. Owner/operation/message checks отклоняют старые и чужие кнопки; ACK выполняется до сервиса.

Неизвестный результат отправки сохраняет operation_id и ответы; редактирование/отмена/рестарт блокируются до сверки той же операции. Авторизация, durable effect/replay, storage retention и восстановление после рестарта принадлежат приложению. Добавлены пример с настоящим SQLite effect и общий offline-сценарий, включая редактирование и повтор подтверждения. Windows SQLite соединения в примере закрываются явно.

Каталог содержит 17 групп. Публичные API 0.2.0 сохранены; API TypeScript без изменений, версия согласована. [Контракт и проверка](docs/form-tools-review.md). Поставка остается локальной.

## 0.2.0 — 3 октября 2026

Добавлены шесть групп Python-инструментов для повторяющихся задач бота: BotSettings, меню ActionButton/action_menu, paginated_menu/page_number, CommandReply/command_router/command_menu, run_bot и StubSession. Публичные импорты 0.1.1 сохранены; single-button builder перенесен внутрь keyboards.py и доступен через прежний telegram_patterns.aiogram.

Меню собирают строки с уникальными action keys и emoji fallback. Статические команды описываются один раз, Router сохраняет фильтрацию mention и plain text; установка command menu явная. Runner сохраняет Dispatcher/инъекции и закрывает Bot session при завершении/ошибке/cancellation. StubSession записывает реальные SDK методы, требует явные responses и не имеет сетевого fallback. Добавлен один Dispatcher-пример для live polling и offline command → page → selection проверки.

API TypeScript не менялся; версия пакета согласована с общей поставкой. [Контракты и проверка](docs/bot-tools-review.md). Registry publication не выполнялась.

## 0.1.1 — 3 октября 2026

Повторная проверка общего API с воспроизведением ошибок и проверкой собранных пакетов в новых проектах.

- SQLiteOnce блокирует преждевременные COMMIT/ROLLBACK и неявный commit от executescript до сохранения эффекта; savepoints разрешены. Некодируемый initData возвращает InvalidInitData.
- ApiClient принимает успешные HEAD/204/205 без JSON и отделяет обрыв чтения тела от некорректного JSON/decoder.
- Bridge удаляет неуспешную подписку, очищает частичную регистрацию SDK и допускает повторный start. Platform unknown корректно распознается для UI как запуск вне Telegram.
- SelectionDraftStore фиксирует scope/namespace/TTL при создании, защищая черновик от изменения переданного options-объекта.
- Shell использует семантические цвета Telegram и native color-scheme. ID поля/hint/error не конфликтуют с существующим DOM, включая fallback без window/randomUUID.
- Новый verify_pattern_packages.py собирает wheel/tarball, устанавливает их в свежие consumer-окружения, проверяет публичные imports/declarations/CSS и сохраняет логи, версии и SHA256. Browser matrix хранится отдельно для каждой версии.

[Отчет и границы проверки](docs/component-library-hardening.md). Поставка остается локальной, публикация в реестры не выполнялась.

## 0.1.0 — 3 октября 2026

Первый локальный выпуск двух импортируемых пакетов, десять групп компонентов. Python: Mini App HMAC, SQLite effect/replay, четыре aiogram adapters. TypeScript: bridge, HTTP, scoped selection draft, responsive shell/fields/CSS. Публичные типы, контрактные тесты, примеры и навык подключения. Публикация в package registries не выполнялась.

Версия относится к библиотеке компонентов; исторические отчеты навыков имеют собственную дату/область проверки.
