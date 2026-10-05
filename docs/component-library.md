# Общая библиотека компонентов

Текущая локальная поставка 0.20.0: 38 групп компонентов, 174 публичных Python/TypeScript-символа и 305 рецептов. 206 Python fixtures имеют закрытый executor, 99 native references требуют host/аргументов. [Медиа](media.md) дает typed bytes/file_id, literal captions, compatible album, edit и bounded hosted stream. [Приемка 027](v1-checks/027.json) привязана к wheel/tarball; historical reports сохраняют свои версии.

[Формы 0.3.0](form-tools-review.md) добавляют поля с проверкой, возврат, отмену и подтверждение со стабильным ID заявки. Готовый [бот формы](../examples/python/form_bot.py) и [offline-проверка](../examples/python/offline_form.py) используют один create_app; backend сохраняет заявку и replay result в SQLite.

Агент импортирует поддерживаемые компоненты и добавляет бизнес-логику проекта. Версия 0.5.0 содержит 24 группы компонентов в двух независимых пакетах. [components.json](../components.json) — каталог; [telegram-code-patterns](../.agents/skills/telegram-code-patterns/SKILL.md) учит агента подключать API. Установка навыка не устанавливает пакеты.

[Галерея и CLI 0.5.0](developer-tools-review.md): поиск 298 рецептов, готовые новые проекты и read-only doctor. [Открыть галерею](../gallery/index.html). Starter Mini App — frontend companion без backend auth; recipe scope различает SDK/mock/reference и live.

[Рецепты 0.4.0](../recipes/README.md) добавляют explicit native rows/reply/input, поиск и request construction всех 185 методов Bot API, UpdateObserver/event_router, native Mini App facade с version/presence gates. [Обзор и границы](telegram-cookbook-review.md). API каталог не объявляет все права/продуктовые сценарии проверенными в Telegram.

[Инструменты ботов 0.2.0](bot-tools-review.md): меню, команды, пагинация, запуск и локальный тестовый транспорт. [Проверка 0.1.1](component-library-hardening.md) фиксирует исправленные ошибки предыдущей версии; [историческая проверка 0.1.0](component-library-review.md) — независимые consumer-сценарии первого выпуска. Границы live/device проверки указаны в отчетах.

| Пакет | Что готово | Документация |
| --- | --- | --- |
| Python awesome-telegram-patterns / telegram_patterns | Настройки, HMAC, SQLite; aiogram menus/pagination/commands/forms/callback/Stars/polling; test transport | [Python README](../packages/python/README.md) |
| TypeScript @awesome-telegram/patterns | Bridge, HTTP, черновик выбора, адаптивный shell/поля | [TypeScript README](../packages/typescript/README.md) |

Core не привязан к инфраструктуре. Aiogram — extra; DOM shell подходит для легкого Mini App без frontend-фреймворка. Уже выбранные PTB/PostgreSQL/React сохраняются: подключается подходящий компонент. Python и TypeScript связываются через API конкретного проекта; runtime пакетов независим.

[Навигация сообщений](message-navigation.md): готовые экраны/history/back/refresh с owner/bot/chat/thread/message/revision checks и explicit unknown edit recovery. State локальный для одного процесса; предоставленный пример добавляет Router к существующему Dispatcher.

## Примеры

Из корня библиотеки, после передачи BOT_TOKEN своего тестового бота в окружение:

```powershell
uv run --with "./packages/python[aiogram]" python examples/python/bot.py
```

[Код бота](../examples/python/bot.py) читает настройки без вывода токена, связывает команды, страницы каталога и выбор элемента. Это публичный каталог без покупок/частных объектов. Пример явно устанавливает default command menu тестового бота; без token завершается до сетевого запуска. Исходящие ответы остаются в исходном чате.

Тот же Dispatcher можно проверить без Telegram, credentials и сети:

```powershell
uv run --with-editable "./packages/python[aiogram]" python examples/python/offline_bot.py
```

[Offline-пример](../examples/python/offline_bot.py) применяет StubSession, выполняет /start → следующая страница → выбор и проверяет исходящие методы. Новый SDK запрос без явно заданного ответа провалит проверку. Для старта с двумя текстовыми командами достаточно короткого примера из [Python README](../packages/python/README.md).

Offline пример SQLite не требует Telegram:

```powershell
uv run --with ./packages/python python examples/python/booking.py ./demo.sqlite
uv run --with ./packages/python python examples/python/booking.py ./demo.sqlite
```

Второй вызов вернет прежнюю запись с replayed=true. Actor 42 — fixture; реальный сервис сначала устанавливает личность и права. [Код операции](../examples/python/booking.py).

Mini App:

```powershell
npm.cmd ci
npm.cmd run demo
```

Открой http://127.0.0.1:4173. [Пример](../examples/mini-app/src/index.ts) импортирует общий пакет: форма, темы, scoped выбор и потерянный ответ. Loopback server без Telegram-аутентификации/оплаты/календаря, store в памяти очищается при перезапуске. Контакты остаются в форме и не отправляются mock endpoint. Recovery неизвестной записи работает до закрытия страницы; production reload/account switch требует отдельного durable operation record. Для реального Mini App host подключает выбранный SDK и свой backend.

Пакеты пока распространяются локально, без публикации на PyPI/npm. Полная проверка ниже сама строит артефакты; для отдельной сборки из корня:

```powershell
npm.cmd ci
npm.cmd run build
New-Item -ItemType Directory -Force ./output/pattern-library-0.5.0/dist | Out-Null
uv build --wheel --out-dir ./output/pattern-library-0.5.0/dist ./packages/python
npm.cmd pack --ignore-scripts -w @awesome-telegram/patterns --pack-destination ./output/pattern-library-0.5.0/dist
```

В другом проекте устанавливай Python из предоставленного пути/wheel (extra [aiogram] для SDK), TypeScript из построенного tarball. Сохраняй версию/lockfile. Public API 0.x развивается с changelog.

## Задачи для ИИ

```text
$telegram-code-patterns Добавь /start и зеленую кнопку в существующий aiogram-бот.
Python-библиотека доступна по указанному локальному пути. Сохрани Dispatcher.

$telegram-code-patterns Подключи bridge и API-клиент к моему TypeScript Mini App.
Используй установленный пакет. После timeout сверяй результат с сервером.
```

Агент читает строку каталога, API и пример; импортирует компонент и выполняет обязанности продукта. Навык помогает выбрать и проверить код, библиотека предоставляет исполняемый API. Для другой версии ее документация имеет приоритет над snapshot 0.5.0 в навыке.

## Проверка и развитие

Полный выпуск проверяется одной командой после установки dev dependencies:

```powershell
npm.cmd ci
python scripts/verify_pattern_packages.py
```

Нужны Python >=3.11, uv, Node/npm и установленный Chrome; CHROME_PATH задает иной путь к браузеру. Помощник проверяет версии/каталог, собирает пакеты, создает временные проекты вне checkout, устанавливает core без aiogram и SDK отдельно, выполняет пакетные тесты и offline-сценарии бота через установленный публичный API, strict typecheck примера и CSS export. Проверяет console CLI, packaged resources, новые стартеры, direct local dependencies, перенесенные reference-рецепты и Chrome matrix примера/галереи/стартера. Артефакты, логи этапов и distribution-report.json сохраняются в output/pattern-library-0.5.0; временные consumer-проекты остаются по пути из отчета для просмотра. Ничего не публикуется.

На машине без Chrome допустим `python scripts/verify_pattern_packages.py --skip-browser`: отчет явно содержит browser=skipped. Такая проверка подтверждает поставку пакетов, UI требует отдельного запуска. Для итерационной разработки:

```powershell
uv run --with-editable "./packages/python[aiogram]" python -m unittest discover -s packages/python/tests -v
npm.cmd test
npm.cmd run build
npm.cmd run test:browser
uv run --with "PyYAML>=6,<7" python scripts/validate_skills.py
python -m unittest discover -s tests -v
```

Для нового компонента: конкретная повторяющаяся задача, контракт и границы; API и meaningful effect/негативная проверка; export/catalog/example/changelog; сборка и consumer install. Бизнес-правила одного проекта остаются у него. Crypto Pay/Platega/ЮKassa пока представлены навыками интеграции; исполняемых provider adapters в 0.5.0 нет.

Playwright — только dev dependency проверки, не runtime приложения. Проверяются 7 viewport размеров и 2 темы; это не physical device QA. При разработке editable install использует актуальный исходный код, не закэшированный uv wheel. При обновлении версии синхронизируй оба package manifest, examples/mini-app/package.json, lockfile и components.json; документация установленной версии должна соответствовать артефактам.

Составные элементы выбора: `SelectionOption/Spec/Context/State/Result/SelectionMenu` из SDK-free root и `selection_keyboard/selection_router` из optional aiogram. [Server rules и confirmation](selection-controls.md) описывают границы локального намерения и бизнес-транзакции host.

[Медиа 0.20.0](media.md): requests/bytes/file_id/album/edit и bounded explicit read; optional aiogram, без нового обязательного сервиса. Полная приемка — [027](v1-checks/027.json).
