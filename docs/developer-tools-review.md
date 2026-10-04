# Галерея и CLI библиотеки 0.5.0

Выполнены первые два пункта плана: поиск готового кода и подготовка нового проекта. Python и TypeScript поставляются локально; реестры PyPI/npm не используются для поиска нашей библиотеки. Галерея — обычные статические файлы: [открыть](../gallery/index.html), [инструкция](../gallery/README.md).

## Найти подходящий пример

```powershell
python -m pip install ./packages/python
telegram-patterns recipes "две кнопки"
telegram-patterns recipes "sendPhoto" --category bot-api
telegram-patterns recipes --show two-columns
```

Эквивалент команды: `python -m telegram_patterns`. `recipes` не требует aiogram, не исполняет найденный код и не обращается в Telegram. В wheel находится тот же снимок каталога, что и в галерее; по умолчанию показываются до 20 совпадений. Фильтры: `--category`, `--language`, `--verification`, `--limit`.

298 записей состоят из 11 клавиатур/сценариев ввода, 185 Bot API requests, 99 Mini App references и трех полных бот-примеров. Для каждого приведены код, источники и область проверки:

| Статус | Что сделано | Что остается у проекта |
| --- | --- | --- |
| `sdk` — 196 | Построены объекты установленного aiogram 3.31.0 | Реальные IDs/files, права, контекст и отправка запроса |
| `mock` — 3 | Исполнен настоящий Dispatcher с явным StubSession | Живой Telegram, durable state и нужная бизнес-логика |
| `not_run` — 99 | Справочный native фрагмент из каталога API | Аргументы, version/platform gates, permissions и реальное испытание |
| `live` — 0 | Ни одного сценария здесь не заявлено проверенным живьем | Проверка конкретного бота/клиента с отдельными credentials |

Веб-превью показывает строки, fixed styles и подсказку ввода. Оно не воспроизводит точный внешний вид Telegram. Все действия превью локальные; кнопки не оплачивают, не запрашивают контакт и не открывают Mini App. Код и названия выводятся как текст; нет выполнения HTML из каталога или удаленных assets. Копирование сообщает об успехе только после clipboard write; при отказе выделяет код для ручного копирования.

Публичный API core: `RecipeCatalog().search(...)`, `.get(id)`, `.recipes`, `.library_version`. `Recipe` неизменяем; `preview` возвращает отдельную JSON-копию. Поиск нормализует регистр/ё/Unicode, требует все слова и не трактует строку как regex/команду.

## Создать проект

Из корня библиотеки, после установки Python-пакета с extra aiogram:

```powershell
python -m pip install "./packages/python[aiogram]"
telegram-patterns init ../my-new-bot --library ./packages/python --dry-run
telegram-patterns init ../my-new-bot --library ./packages/python
python ../my-new-bot/offline.py
telegram-patterns doctor ../my-new-bot
```

Имя цели в примере должно еще не существовать; родительский каталог должен существовать. `--library` принимает локальную директорию пакета/репозитория или wheel. Публичный API: `create_starter(target, *, library, template='bot', typescript=None, dry_run=False)`, результат `StarterPlan`. Ни dry-run, ни init не устанавливают зависимости.

Для отдельного нового проекта с frontend возьми артефакты одной версии после проверки поставки:

```powershell
telegram-patterns init ../my-new-app --template bot-mini-app --library ./output/pattern-library-0.5.0/dist/awesome_telegram_patterns-0.5.0-py3-none-any.whl --typescript ./output/pattern-library-0.5.0/dist/awesome-telegram-patterns-0.5.0.tgz
```

Python dependency записывается как direct file URI с extra aiogram, npm dependency — как file URI tarball. Пути относятся к этой машине; при переносе проекта нужно предоставить артефакты и обновить пути. Существующий стек/проект не переводится на этот starter. В новом боте один Dispatcher, /start/help, кнопка помощи, явная установка default command menu при live запуске и offline.py с fake transport. Для live запуска требуется BOT_TOKEN в окружении; webhook не удаляется автоматически.

Frontend содержит plain DOM shell, поле, локальную валидацию и theme bridge. В Telegram принимает native theme; вне Telegram/при platform unknown следует системной теме и ее изменениям, сохраняя ввод. SPA host вызывает export disposeApp при unmount. Нет backend/session/initData integration; следующий полный сценарий авторизации относится к пункту 13 плана. Предусмотренные README команды install/typecheck/build работают с предоставленным tarball. Галерея и frontend starter не требуют отдельного приложения или обязательного сервиса.

`init` отказывается от существующего каталога, включая пустой; не следует output symlink/junction и открывает новые файлы в exclusive mode. Ошибка I/O может оставить часть нового проекта, без удаления чужих файлов или автоматической очистки. Проверка metadata артефакта не является проверкой его доверенности: устанавливай собственные проверенные пакеты.

## Диагностика

`doctor` возвращает JSON и exit code 0/1. Проверяет Python >=3.11, установленный пакет, совместимый aiogram и imports, TOML, наличие и локальный формат BOT_TOKEN из окружения. Для `mini-app/package.json` проверяет manifest, npm в PATH и фактический `node --version` >=20. Значение token и произвольные ошибки импортов не выводятся; .env не читается. Без `--require-token` отсутствующий token — предупреждение, что позволяет локальную проверку до настройки бота.

Не проверяет действительность token, webhook/polling consumer, deployment, backend auth, права, реальный Telegram или произвольные зависимости проекта. В отдельном процессе выполняется только фиксированная команда версии Node; код целевого проекта не импортируется. Импортируются наши adapters и установленный SDK. Шаблон можно создать из core без SDK, но запустить бот и успешно пройти SDK-check doctor получится после установки extra.

## Повторяемая проверка

```powershell
npm.cmd ci
python scripts/verify_pattern_packages.py
```

Помощник сохраняет [отчет поставки](../output/pattern-library-0.5.0/distribution-report.json), логи и скриншоты в `output/pattern-library-0.5.0`. Проверяет установленную console entrypoint и resources без SDK, bot/companion в новых каталогах, dry-run и отказ от перезаписи, install Python direct dependency, npm tarball dependency, strict typecheck/build и offline Dispatcher. Chrome matrix галереи: 7 размеров × 2 темы; starter: 3 размера × 2 темы. Проверяются фактические scheme/background, переключение системной темы без потери ввода, приоритет native theme, platform unknown и cleanup при unmount. Regression check прежнего starter воспроизводит ошибочную светлую тему. Дополнительно проверяются фильтры, no-match, local preview, clipboard refusal, вывод текста без HTML execution и отсутствие внешних запросов.

Исходные пакетные и Mini App проверки остаются частью поставки. `--skip-browser` оставляет все UI-проверки невыполненными. Browser viewports не доказывают поведение физических Android/iOS/Telegram Desktop. Исполнение контрактов и скопированных рецептов навыка не является независимой оценкой решений агента.

Результат 4 октября 2026: полная поставка прошла 35 этапов. Python: 82 теста, из них 81 выполнен и один symlink-тест пропущен из-за недоступности Windows directory links. TypeScript: 21 тест. Chrome: 141 проверка исходного Mini App, 175 галереи и 66 стартера (включая реальные CSS theme/background, смену темы и unmount). Снимки телефона и ПК просмотрены; дефект dark fallback воспроизведен на прежнем starter и исправлен. Установленная CLI, оба generated offline бота, direct wheel/tarball dependencies, strict TS build и три блока из переносимого навыка прошли. Validator проверил 41 навык; 16 корневых тестов прошли. SHA256 wheel/tarball и совпадение bundled recipe/template файлов с исходниками проверены отдельно. Это локальные доказательства; live Telegram/provider/device испытаний здесь нет.

Частичная сверка 4 октября 2026: [PyPA command-line tools](https://packaging.python.org/en/latest/guides/creating-command-line-tools/) — console entrypoint/argparse; [dependency specifiers](https://packaging.python.org/en/latest/specifications/dependency-specifiers/) — direct references. Для fallback темы: [MediaQueryList change](https://developer.mozilla.org/en-US/docs/Web/API/MediaQueryList/change_event) и [color-scheme](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/color-scheme). Telegram request/native поведение не изменено этим релизом; его источники и scope остаются в [обзоре 0.4.0](telegram-cookbook-review.md).
