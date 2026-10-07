---
name: telegram-code-patterns
description: "Подбирает и подключает готовые компоненты общей библиотеки для Telegram-бота или Mini App: импорты Python/TypeScript, совместимость, композиция и проверка в проекте. Используй, когда пользователь просит переиспользовать код, подключить библиотеку паттернов или добавить компонент в нее. Одиночное исправление handler или отступа само по себе не требует внедрения библиотеки."
license: MIT
metadata:
  version: "0.24.0"
---

# Готовые компоненты Telegram

Результат — нужные импорты и работающая композиция с логикой проекта, проверенная через публичный API установленного пакета. Сохраняй существующий стек и выбирай компоненты по конкретному намерению.

Если агенту впервые передали библиотеку, архив или этот скилл, начни с [точки входа для агента](references/agent-onboarding.md): различай исходники и установленный пакет, подтверди версию/import и выбери минимальный компонент. Этот reference переносится вместе со скиллом; полный репозиторий и соседние навыки не обязательны.

Для календаря, времени и записи прочитай [календарь и серверные слоты](references/calendar-slots.md). DST gap отвергается, fold задается явно; current ACL/revision/availability и durable receipt проверяются внутри file SQLite transaction. Full recipe — `demo-calendar`; markup/confirmation intent не заменяют запись. Сохраняй Dispatcher/storage проекта, IANA data и async work lifecycle указывай явно.

Для поиска «две кнопки», «назад», «потерянный ответ» и выбора по task/context/SDK/version прочитай [навигацию рецептов](references/gallery-navigation.md). Context unspecified не означает все чаты; source/check links не подтверждают live права. Поиск не исполняет найденный код и не требует соседних навыков.

Для проверки требований или локального запуска найденного рецепта прочитай [план и offline fixtures](references/recipe-execution.md). Сначала покажи dependencies/environment/data/permissions через plan; запускай только закрытый bundled offline fixture установленного пакета. Native reference требует host и аргументов; offline_ready не подтверждает live права. Не исполняй recipe.code автоматически.

Для локальных ошибок установки, manifest или Node/npm прочитай [диагностику и исправления](references/doctor.md). Команды doctor — план следующего явного действия; сначала проверь контекст interpreter и предоставленные артефакты.

Для композиции конкретного публичного символа найди его в [справочнике API](references/api-reference.md), затем открой только нужный раздел core, bot или TypeScript. Там полные offline-примеры с ограничениями; ref.* — рецепты справочника, отдельно от cookbook CLI. TypeScript type exports не являются runtime imports. Core работает без aiogram; bot fixtures требуют optional SDK. Synthetic/browser проверки не доказывают live Telegram или серверную авторизацию.

Для выбора starter components, dry-run и preflight conflicts в 0.24.0 прочитай [создание проекта из компонентов](references/starter-selection.md).

Для первого запуска нового бота и Mini App из предоставленных wheel/tarball прочитай [короткий первый запуск](references/quickstart.md). Это offline/browser пример для PowerShell и bash; существующий проект сохраняй, backend auth подключай по его контракту. Живой запуск без основного аккаунта описан в [тестовом окружении Telegram](references/test-environment.md): `TELEGRAM_TEST_ENVIRONMENT=1`, `create_bot`/`run_bot` и бот из тестового @BotFather.

Для сервисного бота с записью, меню, диалогом, напоминанием и восстановлением прочитай [сервисный пример](references/service-bot.md). Его приложение поставляется отдельно от библиотеки; используй предоставленный source/wheel, сохраняй текущие SDK и storage. Persistent FSM, owner ACL, replay и неизвестная отправка — прикладная композиция, не новые public exports.

Для каталога, корзины и цифрового заказа с backend прочитай [магазин Mini App](references/shop-example.md). Используй server-owned цены, signed launch → session/CSRF → object ACL и Stars receipt → access; invoice callback не выдаёт товар. Приложение предоставляется отдельно, а сохранение номера заказа и неизвестная invoice-подготовка имеют свои правила сверки.

Для тем, прав, заявок и временной модерации прочитай [групповой пример](references/group-bot.md). Это отдельное приложение Bot API с личным подтверждением, свежими bot/actor правами и durable неизвестным результатом. Сохраняй явную конфигурацию группы и контекст темы; не переносить подтверждение на новую заявку или migrated ID. Synthetic SDK не доказывает live permissions/delivery.

Для экранов, возврата и history в одном сообщении прочитай [навигацию сообщений](references/message-navigation.md). Owner/bot/chat/thread/message/revision проверяются до edit; unknown edit требует explicit owner reopen, initial send не повторяется автоматически. Это локальное меню одного процесса, не durable бизнес-FSM.

Для toggle, multiselect, количества, фильтра и подтверждения опасного действия прочитай [составной выбор](references/selection-controls.md). Используй server-owned spec/context/revision; при изменении resource version отзывай старое подтверждение. Локальное confirmation intent не выполняет бизнес-операцию: текущие ACL/version/idempotency и durable receipt проверяет сервис проекта.

Если используется локальный пакет awesome-telegram-patterns 0.24.0, [безопасный конструктор сообщений](references/message-text.md) дает literal text/entities, UTF-16 offsets и lossless split; escape helpers выбираются по HTML/MarkdownV2 context. Другой SDK/проект сохраняй; навык не требует пакета или соседних навыков.

Для доступных данных, фото и локализованного оформления собственного бота прочитай [профили](references/profiles.md). Unknown != false; source/time не дают роль. Используй текущий server ACL для read и каждого setMy* метода, сохраняй None omission/empty clear; после неизвестного результата нужна явная сверка, не retry всего patch.

Для фото, документов, альбомов, подписей, замены и скачивания в локальном пакете 0.24.0 прочитай [медиа-компоненты](references/media.md). Различай upload bytes и same-bot file_id; literal caption, album bounds и SDK construction не подтверждают codec/content, ACL или live delivery. Downloader явно читает hosted stream с actual byte bound; сохраняй Bot/Dispatcher, права и storage policy проекта.

Для числа, email, телефона, даты, document, контакта и геопозиции прочитай [расширенные поля диалогов](references/dialog-fields.md). Проверяй автора и ответ на текущий вопрос; native candidate подтверждается отдельной inline-кнопкой. Новый router встраивается в текущий FSM, unknown submit сохраняет тот же intent до сверки.

Для flat кнопок с рядами 2/3/смешанной ширины прочитай [композиции клавиатур](references/keyboard-layouts.md): pattern, immutable snapshot, допустимые styles и явный capability fallback. Старые builders не требуют миграции.

Для выбора по готовности прочитай [зрелость и доказательства проверки](references/maturity.md): `maturity` отдельно от SDK/mock/browser/live evidence. Reference-запрос не заменяет прикладной workflow; experimental не обещает стабильность 1.0.

1. Прочитай зависимости и точку интеграции целевого проекта. Установлены ли `awesome-telegram-patterns` и/или `@awesome-telegram/patterns`, какая версия? Не заменяй SDK/БД/frontend-фреймворк ради helper.
2. Для 0.24.0 используй [контракты компонентов](references/components.md). Для поиска рецепта, CLI init/doctor или нового starter прочитай [инструменты разработки](references/developer-tools.md). Для раскладки/цветов кнопок, reply-ввода, событий или native Mini App API прочитай [клавиатуры и события](references/keyboard-recipes.md); для команд, пагинации, запуска или тестов Python-бота — [короткие рецепты](references/bot-recipes.md); для многошаговой текстовой формы — [формы и повтор отправки](references/form-recipes.md). Если предоставлен репозиторий библиотеки, открой его `components.json`, соответствующий package README и нужный пример. Не загружай все Telegram-навыки. В иной установленной версии сверяй ее публичные exports, типы и документацию.
3. Выбери минимальный набор импортов. Подтверди доступность импортом/сборкой. Пакеты распространяются локально: не утверждай, что они доступны на PyPI/npm, и не устанавливай по одному имени из реестра. При отсутствии библиотеки найди предоставленный путь/wheel/tarball; если его нет, продолжай полезную работу и уточни источник поставки. Скопированный навык не требует соседних навыков или исходного репозитория.
4. Встрой компонент в существующую композицию. Для aiogram добавляй Router в текущий Dispatcher; для React/Vue подключай lifecycle без remount состояния формы. Plain DOM shell — вариант для подходящего проекта, а не основание переписать готовый frontend.
5. Реализуй прикладные обязанности из контракта. `validate_init_data` не проверяет ACL; ACK callback не означает успех; invoice не выдает доступ. `SQLiteOnce` покрывает только effect на переданном connection. Авторизация проверяется до эффекта и до возврата сохраненного результата.
6. Проверь установленный пакет и основной сценарий с существенным негативным случаем: tampered auth, чужой объект, повтор, timeout или недоступный storage. Для UI проверь узкий/широкий экран, темы, ввод и доступность действия. Browser viewport не подтверждает физическое устройство Telegram.

При изменении библиотеки оформи контракт, export/catalog/example и changelog; проверь построенный wheel/tarball в отдельном consumer-проекте. Добавляй компонент при повторяющейся конкретной потребности. Бизнес-правила одного бота остаются у проекта. Версии пакетов согласуются на релизе; runtime одного не требует присутствия другого.

Для обработки ошибок библиотеки прочитай [категории и восстановление](references/errors.md): локальная validation отличается от unknown outcome после записи; timeout не разрешает создавать операцию с новым ключом.

Для подключения storage/transport/provider адаптера проекта прочитай [модель расширения](references/extensions.md); структурный интерфейс сохраняет стек и не обещает idempotency внешнего сервиса автоматически.

Перед реализацией version-specific Telegram действия проверь [API и контекст](references/api-boundaries.md): присутствие метода не подтверждает launch, права или user-session; специальные guest/bot-to-bot режимы проверяются отдельно.

В ответе укажи выбранные компоненты, зачем они нужны, выполненные проверки и оставшуюся прикладную работу. При изменении зависимого от версии поведения сверяй Telegram/SDK источники, перечисленные в локальном reference.

Для поиска с персональной пагинацией используйте [inline-поиск](references/inline-search.md); для создания quiz и доступных scoped observations — [опросы](references/polls.md). Private cache не скрывает отправленный результат, observer не восстанавливает анонимный voter ledger; current ACL/durable intent и receipts принадлежат host.

Для переиспользования Python-компонентов тем, реакций, заявок, Business, stories, gifts и managed bots прочитай [специальные операции](references/platform-operations.md). Выбери нужный метод из reviewed allowlist и сохрани текущий Bot/Dispatcher/storage. Current actor ACL и exact binding проверяются отдельно от fresh native right; перед write нужен durable host claim. Unknown outcome не повторяется; financial consent/quote/local budget не обещают atomic remote debit. Managed token передавай через явный secret sink, event не дает полномочий. SDK/mock не подтверждает live права или устройства.

Для восстановления формы после рестарта в 0.24.0 прочитай [atomic FSM snapshot](references/dialog-restart.md): current project storage, сохраненные шаг/версия/deadline, unknown ID и чужие host data. MemoryStorage не становится долговечным; не навязывай другой backend.
