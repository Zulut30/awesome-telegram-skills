# Инструменты ботов 0.2.0

3 октября 2026 года. Расширена общая Python-библиотека для повседневного написания aiogram-ботов; текущий Dispatcher, бизнес-сервисы и инфраструктура проекта сохраняются. Теперь в каталоге 16 групп компонентов, шесть из них добавлены в этом выпуске. TypeScript API остается прежним; версии локальной поставки согласованы. Публикация в реестры не выполнялась.

## Новые возможности

| Задача | API | Результат |
| --- | --- | --- |
| Настройки | BotSettings.from_env | Формат token/отсутствие переменной проверяются, repr не показывает token; core без SDK |
| Несколько кнопок | ActionButton + action_menu | Строки из списка, уникальные keys, styles и emoji fallback |
| Каталог по страницам | paginated_menu + page_number | Markup/номер/число страниц, разные prefixes, отказ невалидным callback и clamp старой страницы |
| Статические команды | CommandReply + command_router/command_menu | Один список для обработчиков и BotCommand DTO; plain text и фильтрация чужого mention |
| Запуск | run_bot | Текущий Dispatcher, workflow data, явная установка menu, закрытие session и остановка polling при cancellation |
| Проверка | StubSession.respond | Реальные SDK модели/методы, explicit fixtures, calls/closed; неожиданный method не уходит в сеть |

Публичные импорты 0.1.1 сохранены. Action keyboard перенесен в keyboards.py с прежним экспортом telegram_patterns.aiogram.action_keyboard. [Python README](../../packages/python/README.md) содержит короткий запуск с двумя командами и точные contracts/limits. [Рецепты для навыка](../../.agents/skills/telegram-code-patterns/references/bot-recipes.md) копируются вместе с ним и не требуют соседних навыков.

## Наблюдения при разработке

Тест реальной asyncio cancellation обнаружил оставшуюся SDK polling child после прямого cancel внешней start_polling-задачи. Runner теперь shield-ит SDK task, запрашивает stop_polling и ждет завершения; startup/failure race и зависший startup ограничены shutdown_timeout (default 10 секунд). Проверки следят за завершением GetUpdates responder и закрытием session. Это управление polling/session; общий drain прикладных handler tasks и durable acceptance остаются у приложения.

Один [create_app](../../examples/python/bot.py) используется для live polling и [offline-сценария](../../examples/python/offline_bot.py). /start строит public catalog, navigation меняет страницу, selection отправляет plain-text ответ в исходный чат. Нет покупки, частного объекта или неявного DM. В offline варианте используются только synthetic actor и token fixture; реальные credentials не читаются.

## Проверка

Финальный wheel/tarball установлен в свежие consumer-проекты вне checkout. Все 19 этапов release helper завершились с exit_code=0: distribution-report.json (`output/pattern-library-0.2.0/distribution-report.json`, локальный артефакт).

| Проверка | Выполненный результат | Доказательство |
| --- | --- | --- |
| Python | 39/39 из установленного wheel: 18 новых bot-tool cases и 21 прежний regression case | Лог (`output/pattern-library-0.2.0/python-tests.log`, локальный артефакт) |
| Core без SDK | BotSettings и HMAC импортированы/выполнены в отдельном venv без aiogram; SQLite example повторен между процессами | Core (`output/pattern-library-0.2.0/core-smoke.log`, локальный артефакт), replay (`output/pattern-library-0.2.0/booking-replay.log`, локальный артефакт) |
| Offline бот | /start → catalog-page:1 → act:item-4; два ACK, edit и ответ в chat=42; session закрыта | Лог (`output/pattern-library-0.2.0/offline-bot.log`, локальный артефакт) |
| TypeScript | 15/15 через установленный tarball; strict typecheck примера и публичный CSS export прошли | Тесты (`output/pattern-library-0.2.0/typescript-tests.log`, локальный артефакт), typecheck (`output/pattern-library-0.2.0/consumer-typecheck.log`, локальный артефакт) |
| Mini App | 141 browser assertion, 14 viewport/theme cases на Chrome 154.0.8037.97; API сохранен | JSON (`output/pattern-library-0.2.0/browser/report.json`, локальный артефакт) |
| Навык | CLI установил только telegram-code-patterns в новый временный проект; все четыре файла совпали побайтово, включая bot-recipes | Копирование (`output/pattern-library-0.2.0/skill-install.json`, локальный артефакт) |
| Набор | 41 skill validation и 16/16 root helper tests прошли без пропусков | [Валидатор](../../scripts/validate_skills.py), [tests](../../tests) |
| Entry point без token | Пример завершился с exit_code=1 и Set BOT_TOKEN до сетевого запуска | Лог (`output/pattern-library-0.2.0/missing-token.log`, локальный артефакт) |

Среда финальных consumers: Windows, Python 3.13.12, aiogram 3.31.0, Node 24.19.0, npm 12.0.2, TypeScript 7.0.2, Playwright 1.63.0. Предварительные Python-пробы использовали 3.12.13. Все версии разрешенного dependency range отдельно не прогонялись.

| Локальный артефакт | Байты | SHA256 |
| --- | --- | --- |
| awesome_telegram_patterns-0.2.0-py3-none-any.whl | 18702 | f4a9a9232df5bc35f76abf4d03152feac2343ed7cb5c713a50c5c4ebaed08f66 |
| awesome-telegram-patterns-0.2.0.tgz | 10284 | c4b06dbff807af57bf260c5c230fe48e98b18fa8bc2b80c739895dc3228b6b65 |

Сверены байты Python/TypeScript модулей и package README с архивами, SHA256 с JSON, сохранность hashes 0.1.1 и UTF-8 текста offline evidence. Артефакты находятся в output/pattern-library-0.2.0/dist. Consumer-проекты оставлены по пути из отчета для просмотра.

Новые тесты проверяют результат SDK сообщений, markup и chat, сохранение старого Router, mention filtering, mutable keyboard snapshot, page round-trip/shrink, configuration failure, actual polling и cancellation, закрытие session при отказах, SDK response validation и отказ от файловой/HTTP fallback. [Тесты](../../packages/python/tests/test_bot_tools.py).

```powershell
npm.cmd ci
python scripts/verify_pattern_packages.py
uv run --with "PyYAML>=6,<7" python scripts/validate_skills.py
python -m unittest discover -s tests -v
```

Release helper собирает wheel/tarball и создает fresh consumers вне checkout. Python core ставится без SDK; SDK tests и offline-бот выполняются из установленного wheel, а TypeScript tests/typecheck/CSS — из tarball. Логи, SHA256 и browser matrix сохраняются в output/pattern-library-0.2.0. Версии 0.1.0/0.1.1 остаются отдельными историческими артефактами.

## Граница результата

Live Telegram messages, permissions, физические устройства, платежи и native capabilities не проверяются local transport. Меню — builders, handlers и авторизация остаются приложению. Статические commands не заменяют FSM/динамический сервис. Pagination принимает local sequence, без SQL cursor/tenant filtering. BotSettings repr redaction не защищает явный token/asdict от логирования. Run_bot предназначен для эксклюзивного использования одного Dispatcher одним polling entrypoint; commands opt-in устанавливает default scope, а другие scopes/languages и webhook/multibot остаются у SDK. Переданную session после preflight runner закрывает, ее нельзя делить с другим Bot.

Новые инструкции проверяются переносимостью ссылок и соответствующими executable сценариями; новый независимый агентный routing audit и автоматическая активация навыка этим прогоном не заявляются. Частичные официальные источники и проверенная версия SDK указаны в [sources.md](../sources.md).

Логи и снимки с путями `output/…` — локальные артефакты исторических проверок. Они не входят в Git и не доступны в свежем клоне. Для текущей принятой версии смотрите [сохраненную приемку 031](https://github.com/Zulut30/awesome-telegram-skills/blob/fe16ba3ea3a2b4d5bbdc69ba09e7b2ed50c0c215/docs/v1-checks/031.json); для нового прогона выполните `python scripts/verify_pattern_packages.py`.
