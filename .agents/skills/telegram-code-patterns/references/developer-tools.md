# Поиск рецепта и подготовка проекта

Доступно с 0.5.0, проверено на 0.24.0.

Этот обзор сохраняет исторические 0.5.0 defaults. Для 0.12.0 добавлены [task/context/SDK/version filters и source/check links](gallery-navigation.md): 299 recipes, без исполнения при поиске; неопределенный контекст не означает любой чат. Прежний API ниже сохраняется.

Используйте только при намерении найти готовый пример, создать новый проект или проверить локальное окружение. Существующий PTB/React/БД сохраняйте. Пакеты поставляются локально; сначала проверьте импорт/версию и предоставленный путь/wheel/tarball, а не ищите наше имя в registry. Этот reference работает без соседних навыков и исходного репозитория.

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

CLI эквивалент: `telegram-patterns recipes "две кнопки"`, `telegram-patterns recipes --show two-columns`; также `python -m telegram_patterns`. Поиск не выполняет найденный код. Прочитайте `scope`: sdk означает construction, mock — synthetic Dispatcher, not_run — reference с недостающими аргументами, live — явно подтвержденный live сценарий. Snapshot 0.5.0 содержит 196 sdk, 3 mock, 99 references, 0 live. Выбор recipe не подтверждает права/доставку/действительность платежа. Кнопочное веб-превью не является Telegram device QA.

## Новый проект

`telegram-patterns init <NEW_PATH> --library <LOCAL_SOURCE_OR_WHEEL> --dry-run` показывает список файлов без записи. Та же команда без dry-run создает каталог. Родитель должен существовать; target не должен существовать, даже пустой. Не запускайте init в текущем готовом проекте: используйте [контракты](components.md) для точечных импортов. Init не устанавливает dependencies, не читает token и не обращается в Telegram.

Для `--template bot-mini-app` дополнительно передайте `--typescript <LOCAL_TARBALL>` той же версии. В pyproject путь к пакету записывается как file URI; с 0.9.2 package.json хранит обычный путь файловой системы с пробелами как есть. При переносе проекта обновите оба пути. В метаданных `typescript_uri` остается URI. Шаблону на Python для запуска нужен extra `aiogram`; в нем есть команда, меню, обработчик кнопок и `offline.py`. Шаблон frontend — форма на TypeScript без фреймворка и мост темы; авторизация на backend, сессии и права доступа не реализованы. Сообщите об этом в описании результата и не называйте шаблон готовым Mini App для продакшена.

Публичный core API: `create_starter(target, *, library, template='bot', typescript=None, dry_run=False)` возвращает `StarterPlan(target,template,library_version,files,created)`. Не перезаписывает существующие файлы. При I/O ошибке может остаться частично созданный новый каталог; не удаляйте его автоматически вместе с чужими файлами.

## Doctor

`telegram-patterns doctor <PROJECT>` только читает локальное окружение: импортирует Python, пакет и aiogram, разбирает TOML, проверяет Node и npm для `mini-app/package.json` и формат `BOT_TOKEN` в окружении. `.env` не читается, токен не печатается. Код выхода 0 означает, что локальных fail нет; warn допустим. `--require-token` превращает отсутствие токена или неверный формат в fail. Ядро без aiogram найдет рецепты и создаст шаблон, но doctor сообщит fail: SDK не готов.

В 0.12.0 причины, контексты и команды исправления описаны в [самостоятельном reference](doctor.md). Проверяйте `name`/`reason`, показывайте remediation и выполняйте отдельное согласованное действие. Недоступный target/read failure становятся failed checks; manifests ограничены 256 KiB, известные links/junctions отклоняются. Doctor не устанавливает зависимости и не выполняет предлагаемые команды.

Doctor не запускает проект: он выполняет только `node --version` и пробный импорт установленного адаптера и SDK в изолированном Python (`-I -B`). Известная подмена импорта aiogram отклоняется; каталог проекта, `PYTHONPATH` и user-site в пробный импорт не попадают. Doctor не подтверждает, что токен действителен, что polling получает только один процесс, а также не проверяет webhook, авторизацию backend, развертывание, другие зависимости и реальный Telegram. Перед живым polling отдельно убедитесь, что нет второго получателя updates и не установлен webhook. Запускайте `offline.py` до настройки токена; подтверждайте установленную библиотеку, а не случайный импорт из исходников.

Частично проверенные 4 октября 2026 источники: [PyPA CLI](https://packaging.python.org/en/latest/guides/creating-command-line-tools/) и [direct dependency references](https://packaging.python.org/en/latest/specifications/dependency-specifiers/). API Telegram/SDK не менялся в этом reference; [границы кнопок и событий](keyboard-recipes.md) остаются применимыми.

Для первого запуска предоставленных wheel/tarball используйте [проверенные команды](quickstart.md). Исправление npm path подтверждено настоящим consumer install с пробелами; npm local path/tarball документация сверена 2026-10-04, источники в этом reference.

В 0.10.0 выбор starter групп через --component и init --list-components описан в [самостоятельном reference](starter-selection.md). Прежние default композиции сохранены; partial I/O failure не разрешает удалять чужие файлы.
