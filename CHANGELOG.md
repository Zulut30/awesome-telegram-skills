# Изменения библиотеки компонентов

## Unreleased — подготовка 1.0

- Пункт 019: самостоятельное приложение `examples/group-bot` / `awesome-telegram-group-example` 0.1.0. Темы, свежие права bot/actor, context-bound confirmation, обычные/assigned заявки и десятиминутная модерация; file SQLite journal, миграции и membership invalidation. Повтор и crash после synthetic API-запроса не отправляют действие заново. Внешний consumer проверяет wheel/RECORD/entrypoint, типы, 19 тестов и четыре реальные процессные фазы. Live права/delivery не объявлены проверенными; публичный API библиотеки 0.13.0 не изменился.

- Пункт 018: отдельный `examples/shop` / application 0.1.0 связывает установленную библиотеку 0.13.0, TypeScript каталог/корзину и Python/aiohttp backend с реальной SQLite. Signed initData → hashed session/CSRF → owner ACL; цена/валюта/terms и order operation — серверные. Stars invoice, pre-checkout и атомарный receipt/paid/access подключены через публичные компоненты и trusted SDK Router. Invoice callback не выдаёт доступ. Pending ID переживает reload, unknown invoice не пересоздаётся; duplicate/second receipt сохраняются без двойной выдачи. Separate consumer tests и Chrome проверяют композицию; transport/native/launch остаются synthetic, live Stars/device acceptance отдельно. Пакеты библиотеки и их публичные exports не изменены.

- Пункт 017: отдельное приложение `examples/service-bot` / `awesome-telegram-service-example` 0.1.0 использует принятую библиотеку 0.13.0. Меню, запись через text_form_router, file SQLite FSM, owner-scoped доступ, transactional replay, согласие и durable намерение напоминания. Actual crash после commit сохраняет один эффект; crash после synthetic отправки оставляет unknown без автоматического дубля. OS process lock и join SQLite work при отмене предотвращают продолжение записи после освобождения базы. Внешний consumer устанавливает оба wheel, проверяет типы, восемь domain/lifecycle тестов и семь отдельных restart/crash фаз. Synthetic SDK transport не подтверждает live Telegram; общая библиотека и её public exports не изменились.

- Пункт 016, 0.13.0: у всех 299 cookbook recipes появились execution requirements. Публичные frozen RecipeRunPlan/RecipeRunResult, plan_recipe/run_recipe_offline и CLI run-recipe сначала показывают план, затем по --offline запускают закрытый fixture из установленного пакета. 200 Python сценариев выполняются без токена: 185 SDK requests, 11 markup builders, три Dispatcher-композиции и один SQLite lost-response. 99 native references дают явный отказ без host/аргументов.

  Изолированный child получает только системный env, owns temporary files и не выполняет recipe.code/user application. Real SDK HTTP и внешний Python DNS/connect запрещены; доверенный fixture worker не является OS sandbox. Сессия/FSM явно закрываются. Requirements panel отделяет offline readiness от live auth/ACL/entitlement; SDK can_* hints не объявляются полным permission engine. Предыдущие API/schema defaults сохранены; maturity/evidence не повышены. Каталог: 29 групп, справочник: 120 символов и 19 полных примеров. Поставка локальная.

- Пункт 015, 0.12.0: галерея и SDK-free RecipeCatalog/CLI ищут по задаче, контексту, SDK/снимку и версии API независимо от maturity/evidence. Источники и executable проверки связаны с каждой записью; standalone export копирует связанные файлы byte-exact. Добавлен существующий SQLite lost-response пример: 299 recipes, 15 experimental, 284 reference; 196 SDK / 4 mock / 99 not_run. Schema 1 и прежние defaults/imports сохраняются; unknown context не означает все чаты. На телефоне дополнительные фильтры и пояснения свернуты.

  При проверке новой поставки воспроизведен timeout первого изолированного SDK import в свежем Windows consumer: старый лимит 10s заменен на 30s. Ошибки и превышение лимита сохраняют fail; проверки timeout и отсутствия секретов проходят. Consumer harness сохраняет причины/время tool probes для расследования таких сбоев.

- Пункт 014, 0.11.1: поименный API-справочник, 116 публичных символов и CLI/CSS, 18 полных примеров core/bot/Mini App. Переносимые references автономны. Генератор обнаруживает незадокументированные exports; отдельный consumer проверяет точные блоки документации, installed types, CLI, ESM и DOM. Runtime API не изменен; patch нужен для новых package README bytes.

- Пункт 013 / поставка 0.11.0: doctor сообщает машинные причины и команды исправления без исполнения рекомендаций. Ожидаемые ошибки target/manifest становятся failed checks, JSON shape проверяется, чтение ограничено и известные links отклоняются. Node probe получает системный env allowlist и не отражает raw output. Рекомендованные wheel/tarball repairs проверяются отдельно в новом окружении.

- Пункт 012 / поставка 0.10.0: выбор из 15 starter групп, auto-dependencies, минимальная версия API и preflight конфликтов шаблона/артефактов/файлов/команд/prefix. Выбранные модули исполняются через установленную библиотеку; generated Python distribution включает подключенные модули. Dry-run перечисляет все файлы, повторный запуск сохраняет пользовательский код.

- Пункт 011 / поставка 0.9.2: короткий первый запуск из локальных wheel/tarball 0.9.2 с offline-ботом и адаптивной формой. Команды руководства проверяются в новом внешнем consumer с пробелами в путях; переносимая копия навыка совпадает с руководством. Исправлен npm file spec для путей с пробелами: прежний percent-encoded URI приводил к ENOENT; Python URI и config URI сохранены. Browser preview и установка dependencies отделены от реального Telegram и backend auth.

- Пункт 010: фиксированы identity/launch/rights границы Bot API, Mini App, Business/Secretary и user-client; добавлена переносимая инструкция и SDK/native probes. Учтены современные guest/bot-to-bot исключения и расхождения FAQ/rights naming; пользовательская session не подключается автоматически. Runtime API и артефакты 0.9.1 сохранены.

- Пункт 009 / поставка 0.9.1: обязательный read-only archive contract — source/resources/RECORD, extra/CLI и полный набор JS/declarations/CSS/export map. Проверки подмены/пропуска/лишних файлов и небезопасных archive entries выполняются в настоящих temporary archives; installed consumers остаются отдельным runtime evidence. API 0.9.0 сохранен.

- Пункт 008 / исходники 0.9.0: структурные OnceStore/AsyncTransport/ProviderAdapter и optional RefundProvider; публичные TS KeyValueStorage/StorageFactory/FetchTransport без изменения прежних методов. Рабочий custom adapter проверяет SQLite replay, lost response и tampered fixture event; реальные provider workflows остаются отдельными задачами.

- Пункт 007 / исходники 0.8.0: единые ErrorReport/code/category/outcome/recovery в Python/TypeScript; безопасные сообщения, совместимые исключения и различимые preflight/permission/unsupported/timeout. Неизвестный результат записи требует сверки того же ключа; HTTP/отмена/ошибка feedback не запускают retry. Добавлены installed-core пример и проверки сохранения pending identity формы.

- Пункт 001: определены сценарии и границы 1.0, пользовательские задачи, точки входа и критерии приемки; добавлен регистр выполнения всех 100 пунктов.
- Пункт 002 / исходники 0.6.0: maturity групп и recipes, независимый фильтр RecipeCatalog/CLI/галереи, совместимое чтение старых records и переносимые инструкции. SDK/mock/browser evidence не повышает статус до stable автоматически.
- Пункт 003: полные семантические контракты root/aiogram/testing/CLI и TypeScript exports, включая DTO/types, ошибки, ресурсы и обязанности host.
- Пункт 004: правила SemVer, миграций, неизменности релиза и deprecation stable API (два minor и 90 дней); RC identity различает Python/npm форматы.
- Пункт 005: опубликованы support matrix и JSON snapshot с точными проверенными версиями, пропуском Windows symlink и явно непроверенными OS/Telegram clients.
- Пункт 006 / исходники 0.7.0: явные Python/TypeScript exports, Literal aliases и TextFieldControl, устранены 19 ошибок Mypy в SDK guards/middleware; consumer type checks проверяют wheel/tarball, migration случайных wildcard SDK imports документирована.

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
