# Поиск рецепта и подготовка проекта — API 0.5.0

Используй только при намерении найти готовый пример, создать новый проект или проверить локальное окружение. Существующий PTB/React/БД сохраняй. Пакеты поставляются локально; сначала проверь импорт/версию и предоставленный путь/wheel/tarball, а не ищи наше имя в registry. Этот reference работает без соседних навыков и исходного репозитория.

## Поиск

После установки предоставленного Python-пакета работает core без aiogram:

```python
from telegram_patterns import RecipeCatalog

catalog = RecipeCatalog()
recipe = catalog.search("две кнопки", category="keyboards")[0]
assert recipe.id == "two-columns"
assert recipe.verification == "sdk"
assert [len(row) for row in recipe.preview["inline_keyboard"]] == [2, 2]
print(recipe.code)
```

CLI эквивалент: `telegram-patterns recipes "две кнопки"`, `telegram-patterns recipes --show two-columns`; также `python -m telegram_patterns`. Поиск не выполняет найденный код. Прочитай `scope`: sdk означает construction, mock — synthetic Dispatcher, not_run — reference с недостающими аргументами, live — явно подтвержденный live сценарий. Snapshot 0.5.0 содержит 196 sdk, 3 mock, 99 references, 0 live. Выбор recipe не подтверждает права/доставку/действительность платежа. Кнопочное веб-превью не является Telegram device QA.

## Новый проект

`telegram-patterns init <NEW_PATH> --library <LOCAL_SOURCE_OR_WHEEL> --dry-run` показывает список файлов без записи. Та же команда без dry-run создает каталог. Родитель должен существовать; target не должен существовать, даже пустой. Не запускай init в текущем готовом проекте: используй [контракты](components.md) для точечных импортов. Init не устанавливает dependencies, не читает token и не обращается в Telegram.

Для `--template bot-mini-app` дополнительно предоставь `--typescript <LOCAL_TARBALL>` той же версии. В pyproject сохраняется Python file URI; с 0.9.2 package.json использует npm file filesystem path с буквальными пробелами. При переносе обновляй пути. Metadata typescript_uri остается URI. Python template требует aiogram extra для запуска, содержит command/menu/callback и offline.py. Frontend template — TypeScript plain DOM форма/theme bridge; backend auth/session/ACL не реализованы. Сохраняй это в описании результата; не называй шаблон готовым production Mini App.

Публичный core API: `create_starter(target, *, library, template='bot', typescript=None, dry_run=False)` возвращает `StarterPlan(target,template,library_version,files,created)`. Не перезаписывает существующие файлы. При I/O ошибке может остаться частично созданный новый каталог; не удаляй его автоматически вместе с чужими файлами.

## Doctor

`telegram-patterns doctor <PROJECT>` выполняет read-only local checks: Python/package/aiogram imports, TOML, Node/npm для `mini-app/package.json`, формат BOT_TOKEN в окружении. `.env` не читается, token не печатается. Exit 0 означает отсутствие локальных fail; warn допустим. `--require-token` превращает отсутствие/невалидный формат token в fail. Core без aiogram найдет рецепты/создаст template, но doctor вернет fail SDK readiness.

Doctor не запускает проект; fixed `node --version` и импорты нашего adapter/SDK — единственные code checks. Не подтверждает token validity, единственный polling consumer, webhook, backend auth, deployment, другие зависимости или реальный Telegram. Перед live polling отдельно проверь отсутствие конкурирующего consumer и наличие webhook. Запускай offline.py до настройки token; подтверждай установленную библиотеку, а не случайный source import.

Частично проверенные 4 октября 2026 источники: [PyPA CLI](https://packaging.python.org/en/latest/guides/creating-command-line-tools/) и [direct dependency references](https://packaging.python.org/en/latest/specifications/dependency-specifiers/). API Telegram/SDK не менялся в этом reference; [границы кнопок и событий](keyboard-recipes.md) остаются применимыми.

Для первого запуска предоставленных 0.9.2 wheel/tarball используй [проверенные команды](quickstart.md). Исправление npm path подтверждено настоящим consumer install с пробелами; npm local path/tarball документация сверена 2026-10-04, источники в этом reference.
