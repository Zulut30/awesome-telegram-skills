# Awesome Telegram Skills

Набор навыков для AI-агентов, которые помогают разрабатывать Telegram-ботов и Mini Apps: от выбора архитектуры до проверки работающего приложения.

Каждый навык описывает конкретную задачу, важные ограничения Telegram, ожидаемый результат и способы проверки. Инструкции написаны на русском; названия навыков, библиотек и API сохранены на английском для удобного вызова.

Основной стек проекта: **Python для ботов и backend, TypeScript для Mini Apps**.

Есть [общая библиотека готовых компонентов](docs/component-library.md): два импортируемых пакета Python/TypeScript, 29 групп компонентов и работающие примеры. ИИ подключает нужный API через `telegram-code-patterns`; пакеты пока распространяются локально.

[Требования и offline запуск](docs/recipe-execution.md): планы всех 299 рецептов и 200 Python fixtures без токена; native references требуют host/аргументов.

[Поиск и фильтры галереи](docs/gallery-navigation.md): 299 рецептов, задачи, контекст, SDK/версии, зрелость и доказательства проверки; ссылки на исходники и проверяющий код. Standalone export включает связанные файлы.

Проверена локальная поставка 0.13.0: [статус зрелости API](docs/v1-maturity.md) отдельно от SDK/mock/browser/live evidence. Каталог, Python API, CLI и галерея различают experimental/reference; стабильные сценарии 1.0 пока не заявлены.

[Публичные контракты Python/TypeScript](docs/public-api.md) описывают параметры, результаты, ошибки, побочные эффекты и владение ресурсами для всех документированных API.

[Справочник API](docs/api-reference.md): 116 публичных Python/TypeScript-символов, CLI и CSS; 18 полных примеров с импортами и ограничениями. Проверка исполняет код из документации через установленные wheel/tarball в отдельном consumer.

[Doctor и исправления](docs/doctor.md) объясняет локальные ошибки установки и manifests, показывает команды следующего действия и сохраняет конфигурацию проекта.

[Версии и совместимость](docs/versioning.md): SemVer, migrations, неизменность принятой поставки и окно deprecation стабильного API.

[Матрица поддержки](docs/support-matrix.md) отделяет dependency constraints от проверенных версий SDK, runtime, браузера и устройств.

[Границы Telegram API](docs/telegram-api-boundaries.md): Bot API, Mini App, Business и user-client, launch/rights и специальные guest/bot-to-bot режимы.

[Выбор компонентов нового проекта](docs/starter-selection.md): CLI init, dependency closure, preflight conflicts и полный dry-run.

[Первый запуск](docs/quickstart.md): локальная установка, offline-бот и экран Mini App без настоящего токена.

[Контракт поставки](docs/distribution-contract.md): проверенный состав wheel/tarball, exports, typing, CSS и bundled resources.

[Модель расширения](docs/extension-model.md): протоколы storage/transport/provider и проверенный custom adapter без обязательной инфраструктуры.

[Ошибки и восстановление](docs/error-model.md): безопасные категории, unknown outcome и сверка того же operation_id.

[Структура API и именованные типы](docs/api-structure.md): явные exports, migration wildcard imports и статические consumer-проверки Python/TypeScript.

В 0.5.0 появились [галерея с поиском по 298 рецептам](gallery/index.html) и CLI `telegram-patterns recipes/init/doctor`: найти код, создать новый проект и проверить окружение. Галерея работает локально без токенов. [Как использовать и что проверено](docs/developer-tools-review.md). Выполнены первые два пункта [плана развития](docs/library-roadmap-25.md).

[План к версии 1.0 — 100 пунктов](docs/library-roadmap-100.md): стабильный API, удобные компоненты ботов, архитектура и интерфейс Mini Apps, надежность, платежи, реальные устройства и выпуск. [Обоснование приоритетов](docs/library-v1-research.md) отделяет проверенные факты и пользовательские отчеты от предлагаемых решений.

[Сценарии и границы 1.0](docs/v1-scope.md) фиксируют целевые примеры и критерии приемки; [регистр выполнения 100 пунктов](docs/v1-progress.json) отражает подтвержденный прогресс. Каждый завершенный пункт оформляется отдельным коммитом.

[Рецепты 0.4.0](recipes/README.md): две/три кнопки в ряд, цвета и emoji fallback, reply-клавиатуры, ввод, callback/редактирование и Update events. [Готовый бот](examples/python/keyboards_bot.py) и [offline-сценарий](examples/python/offline_keyboards.py) исполняют одну композицию. [Каталог возможностей](catalog/telegram-capabilities.json) охватывает 185 методов / 400 типов Bot API и 99 native функций / 44 события Mini Apps: request construction и mock verification отмечены отдельно от live сценариев.

[Инструменты ботов 0.2.0](docs/bot-tools-review.md): меню кнопок, пагинация, общие описания команд, polling lifecycle и тесты без Telegram. Есть готовый [offline-бот](examples/python/offline_bot.py). Повторить проверку поставки и Mini App: `python scripts/verify_pattern_packages.py` после `npm.cmd ci`.

[Формы 0.3.0](docs/form-tools-review.md): поля с проверкой, возврат/отмена, подтверждение и стабильный ID заявки при повторе после ошибки. [Готовый бот заявки](examples/python/form_bot.py) и [его offline-сценарий](examples/python/offline_form.py) используют одну композицию.

## Каталог

| Навык | Когда использовать |
| --- | --- |
| [telegram-project-planner](.agents/skills/telegram-project-planner/SKILL.md) | Спроектировать новый бот или Mini App, выбрать стек и границы MVP |
| [telegram-mini-app-ux](.agents/skills/telegram-mini-app-ux/SKILL.md) | Улучшить первый запуск, навигацию, формы и путь покупки |
| [telegram-bot-api](.agents/skills/telegram-bot-api/SKILL.md) | Добавить сообщения, медиа, кнопки или новый метод Bot API |
| [telegram-bot-python](.agents/skills/telegram-bot-python/SKILL.md) | Создать или изменить бот на aiogram / python-telegram-bot / pyTelegramBotAPI |
| [telegram-python-backend](.agents/skills/telegram-python-backend/SKILL.md) | Реализовать Python API, БД, миграции, права и надежные серверные операции |
| [telegram-mini-app-architecture](.agents/skills/telegram-mini-app-architecture/SKILL.md) | Спроектировать структуру, состояние и адаптивные экраны для телефона, планшета и ПК |
| [telegram-mini-app-performance](.agents/skills/telegram-mini-app-performance/SKILL.md) | Измерить и улучшить загрузку, отзывчивость, списки и запросы Mini App |
| [telegram-mini-app-network-recovery](.agents/skills/telegram-mini-app-network-recovery/SKILL.md) | Сохранять допустимые черновики и восстанавливать запросы при плохой сети |
| [telegram-mini-app-typescript](.agents/skills/telegram-mini-app-typescript/SKILL.md) | Подключить bridge/SDK, типы, API-клиент и сборку Mini App на TypeScript |
| [telegram-mini-app-native-capabilities](.agents/skills/telegram-mini-app-native-capabilities/SKILL.md) | Подключить геолокацию, биометрию, QR, storage, sharing и скачивание с fallback |
| [telegram-dialogs](.agents/skills/telegram-dialogs/SKILL.md) | Сделать многошаговый диалог, FSM, меню и восстановление сценария |
| [telegram-notifications](.agents/skills/telegram-notifications/SKILL.md) | Добавить напоминания и рассылки с очередью, отпиской и управляемыми повторами |
| [telegram-inline-mode](.agents/skills/telegram-inline-mode/SKILL.md) | Реализовать поиск и отправку результатов через `@bot query` |
| [telegram-groups](.agents/skills/telegram-groups/SKILL.md) | Работать с группами, каналами, модерацией и темами |
| [telegram-mini-app-ui](.agents/skills/telegram-mini-app-ui/SKILL.md) | Создать красивый адаптивный UI Mini App с темами, safe areas и доступностью |
| [telegram-mini-app-design-system](.agents/skills/telegram-mini-app-design-system/SKILL.md) | Создать переиспользуемые компоненты, токены, темы и согласованные UI-состояния |
| [telegram-mini-app-visual-regression](.agents/skills/telegram-mini-app-visual-regression/SKILL.md) | Настроить сравнение скриншотов с просмотренными эталонами |
| [telegram-mini-app-auth](.agents/skills/telegram-mini-app-auth/SKILL.md) | Проверять `initData` на сервере и создавать пользовательскую сессию |
| [telegram-web-login](.agents/skills/telegram-web-login/SKILL.md) | Подключить Telegram Login OIDC к сайту и безопасно связать аккаунты |
| [telegram-mini-app-integration](.agents/skills/telegram-mini-app-integration/SKILL.md) | Связать бот, Mini App и backend; настроить запуск и deep links |
| [telegram-payments](.agents/skills/telegram-payments/SKILL.md) | Добавить Stars, оплату физических товаров, подписки или возвраты |
| [telegram-subscription-access](.agents/skills/telegram-subscription-access/SKILL.md) | Выдавать и прекращать оплаченный доступ по периодам и событиям оплаты |
| [telegram-admin-panel](.agents/skills/telegram-admin-panel/SKILL.md) | Реализовать операторские действия с ролями, scope и журналом |
| [telegram-media-processing](.agents/skills/telegram-media-processing/SKILL.md) | Принимать, проверять и преобразовывать медиа, создавать превью и фоновые jobs |
| [telegram-testing](.agents/skills/telegram-testing/SKILL.md) | Проверить обработчики, интеграции и реальные сценарии в Telegram |
| [telegram-mini-app-device-qa](.agents/skills/telegram-mini-app-device-qa/SKILL.md) | Провести приемку в целевых Telegram-клиентах на доступных реальных устройствах |
| [telegram-deploy](.agents/skills/telegram-deploy/SKILL.md) | Запустить бот и Mini App, настроить webhook и эксплуатацию |
| [telegram-debugging](.agents/skills/telegram-debugging/SKILL.md) | Найти причину пропавших updates, ошибок API или проблем WebView |
| [telegram-observability](.agents/skills/telegram-observability/SKILL.md) | Внедрить связанные события, метрики и безопасные логи frontend/backend/worker |
| [telegram-security-review](.agents/skills/telegram-security-review/SKILL.md) | Проверить авторизацию, платежи, загрузки и обращения к внешним сервисам |
| [telegram-buttons](.agents/skills/telegram-buttons/SKILL.md) | Цвет кнопок, custom emoji icons и ограничения клавиатур |
| [telegram-profiles](.agents/skills/telegram-profiles/SKILL.md) | Данные профиля, Premium, фото, bio и разрешенное изменение профиля |
| [telegram-localization](.agents/skills/telegram-localization/SKILL.md) | Согласовать языки, plural forms, даты, суммы и длинные надписи бота и Mini App |
| [telegram-user-client](.agents/skills/telegram-user-client/SKILL.md) | Чтение выбранных чатов и истории авторизованного аккаунта через Telethon |
| [telegram-business-bots](.agents/skills/telegram-business-bots/SKILL.md) | Официальное подключение бота к разрешенным чатам аккаунта |
| [telegram-library-selection](.agents/skills/telegram-library-selection/SKILL.md) | Выбор SDK и проверка поддержки новых функций |
| [telegram-code-patterns](.agents/skills/telegram-code-patterns/SKILL.md) | Подключить готовые компоненты общей Python/TypeScript-библиотеки |
| [telegram-cryptopay](.agents/skills/telegram-cryptopay/SKILL.md) | CryptoBot / Crypto Pay: invoices, signatures и сверка оплаты |
| [telegram-platega](.agents/skills/telegram-platega/SKILL.md) | Platega.io: ссылки, callbacks, статусы, возвраты и подписки |
| [telegram-yookassa](.agents/skills/telegram-yookassa/SKILL.md) | ЮKassa: API, provider invoices, capture, refunds и уведомления |
| [telegram-payment-provider](.agents/skills/telegram-payment-provider/SKILL.md) | Stripe, Robokassa и другие провайдеры через отдельный adapter |

## Использование

В этом проекте навыки лежат в `.agents/skills`. Codex поддерживает этот каталог для локальных навыков; если новые навыки не появились в списке, перезапустите чат или приложение. Подробности: [официальная документация навыков](https://developers.openai.com/codex/skills/).

Примеры запросов:

```text
$telegram-project-planner Спроектируй бот записи на консультации с Mini App.
$telegram-mini-app-architecture Реализуй структуру Mini App для телефона, планшета и ПК с сохранением формы и надежной навигацией.
$telegram-mini-app-design-system Создай общие компоненты для нескольких экранов Mini App.
$telegram-mini-app-performance Найди причину медленной загрузки и сравни результат до/после.
$telegram-mini-app-device-qa Проверь основной путь в доступных клиентах Telegram.
$telegram-mini-app-ux Упрости запись и исправление ошибок без потери формы.
$telegram-mini-app-visual-regression Добавь проверку скриншотов экранов в двух темах.
$telegram-mini-app-network-recovery Обработай потерянный ответ заказа и восстановление черновика.
$telegram-web-login Подключи Telegram Login к обычному сайту с Python backend.
$telegram-admin-panel Сделай поиск и отмену заказа для оператора своего магазина.
$telegram-media-processing Добавь обработку аудиофайла и закрытую выдачу результата.
$telegram-subscription-access Реализуй оплаченные периоды, продление и истечение доступа.
$telegram-python-backend Добавь API записи с правами доступа и безопасными повторами.
$telegram-notifications Добавь напоминание о записи с возможностью отписаться.
$telegram-localization Добавь русский и английский с согласованными датами и ценами.
$telegram-bot-python Сделай обработчики записи на aiogram с PostgreSQL.
$telegram-dialogs Добавь выбор даты, подтверждение и отмену записи.
$telegram-mini-app-ui Сделай экран доступных слотов на React.
$telegram-mini-app-auth Добавь проверку initData в backend.
$telegram-payments Добавь оплату цифровой подписки через Stars.
$telegram-debugging Разберись, почему webhook перестал получать updates.
$telegram-buttons Сделай зеленую кнопку подтверждения с custom emoji.
$telegram-profiles Добавь доступные данные Premium и фото профиля.
$telegram-user-client Подготовь чтение выбранных чатов через Telethon.
$telegram-business-bots Добавь обработку сообщений подключенного аккаунта.
$telegram-platega Подключи Platega для подходящего платежного сценария.
```

Можно описать задачу обычными словами: у каждого навыка есть отдельное описание для автоматического выбора. Для большой задачи агент может использовать несколько подходящих навыков. Доступность автоматического выбора зависит от агента и его настройки.

Общие навыки не привязаны к языку. Для ботов есть отдельный навык Python, для Mini Apps — TypeScript и UI. Уже выбранные библиотеки сохраняются; для нового проекта без предпочтений отправной вариант — aiogram для бота и TypeScript для Mini App. Frontend-фреймворк и Python web-framework выбираются по проекту.

## Подключить к другому проекту

Скопируйте нужные каталоги из `.agents/skills` в такой же каталог проекта бота. Каждый навык переносится целиком вместе со своими references и UI-метаданными. Ссылок на соседние навыки, обязательных MCP-серверов и привязок к этому компьютеру нет.

Или воспользуйтесь установщиком из корня этого набора:

```powershell
python scripts/install_skills.py --project "C:\path\to\my-bot" --dry-run
python scripts/install_skills.py --project "C:\path\to\my-bot"
```

Для отдельных навыков повторяйте аргумент `--skill`:

```powershell
python scripts/install_skills.py --project "C:\path\to\my-bot" --skill telegram-bot-python --skill telegram-dialogs
```

Целевой проект должен существовать. Скрипт предварительно проверяет весь выбранный набор и отказывается перезаписывать существующие навыки. Он не меняет глобальные настройки агента. Для других агентов используйте их документированный каталог навыков; совместимость их загрузчиков отдельно не проверена.

## Проверка и развитие набора

Для проверки формата, UI-метаданных, локальных ссылок и синтаксиса Python:

```powershell
uv run --with "PyYAML>=6,<7" python scripts/validate_skills.py
python -m unittest discover -s tests -v
```

Без uv установите `requirements-dev.txt` в отдельное виртуальное окружение и запустите `python scripts/validate_skills.py`.

При добавлении навыка укажите узкую область применения, ссылки на официальные источники и проверяемый результат. Детали, нужные только в части задач, выносите в `references/`. Вспомогательные скрипты добавляйте для повторяющихся операций и проверяйте их поведение.

Источники и порядок обновления: [docs/sources.md](docs/sources.md). Сценарии проверки качества навыков: [docs/evaluation.md](docs/evaluation.md). Результаты проверок: [docs/verification.md](docs/verification.md). Независимая проверка поведения и адаптивных Mini Apps: [docs/quality-review.md](docs/quality-review.md). Проверка восьми новых навыков: [docs/skill-extension-review.md](docs/skill-extension-review.md). Полный повторный аудит 33 навыков до последнего расширения: [docs/skill-quality-audit.md](docs/skill-quality-audit.md). Семь продуктовых навыков и расширение UI: [docs/skill-product-extension-review.md](docs/skill-product-extension-review.md).

Последний [полный аудит всех 40 навыков](docs/skill-full-check.md) содержит отдельный результат каждого навыка, свежие исполняемые пробы, 56 слепых запросов выбора, исправления OIDC/Platega и границы live-проверки.

Набор содержит 41 навык. [Карта возможностей Bot API](.agents/skills/telegram-bot-api/references/features.md) и [машиночитаемый индекс](.agents/skills/telegram-bot-api/references/api-index.json) охватывают 185 методов и 400 типов снимка Bot API 10.3. Индекс содержит имена и поля; конкретные ограничения читаются по официальным ссылкам записей. Для обновления:

```powershell
python .agents/skills/telegram-bot-api/scripts/update_api_index.py
```

Работа с пользовательским аккаунтом отделена от обычного Bot API. Telethon использует авторизованную user session; Business/Secretary Bot получает отдельные разрешения владельца. Функции профиля показывают доступные данные, сохраняя различие между отсутствием информации и отрицательным результатом.

Платежные навыки выбирают маршрут по товару и правилам платформы: цифровые товары внутри Telegram используют Stars, а внешние providers применяются к подходящим сценариям. В наборе описаны протоколы интеграции, а production adapters и merchant accounts создаются в конкретном проекте.

Проверка файлов и установщика не означает, что каждый сценарий уже испытан на реальном боте: такие испытания проводятся на отдельном тестовом боте, Mini App и в платежных test environments.
