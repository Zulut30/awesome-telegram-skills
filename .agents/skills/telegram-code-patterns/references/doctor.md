# Локальная диагностика и исправления — 0.11.0

`python -m telegram_patterns doctor .` проверяет окружение нашего aiogram starter и принятую структуру `mini-app/package.json`. В существующем PTB/React/Vue проекте сохраняйте стек: отсутствие aiogram означает отсутствие readiness этого adapter, а не необходимость переписать приложение. Doctor читает локальные manifests и установленные package metadata, проверяет источник aiogram import и запускает фиксированную проверку установленного adapter в отдельном Python `-I -B` с cwd окружения. Каталог проекта, PYTHONPATH и user-site не входят в этот import probe. Для обнаруженного Mini App дополнительно выполняется `node --version`.

Doctor возвращает JSON. Он не читает `.env`, не исполняет приложение, не устанавливает зависимости, не правит файлы проекта и не выполняет HTTP-запросы. SDK probe `-B` также не создает bytecode caches. Команды исправления — рекомендации для следующего явного действия. Установщики при отдельном запуске могут использовать registries. Сетевого режима doctor в этой версии нет.

## Как читать результат

Сохраняются `passed`, `network`, `checks`, `limits` и поля проверки `name`, `status`, `detail`. Новые поля: `schema_version: 1`, `suggestions_executed: false`, `tool_probes_attempted` и `reason`/`remediation` у каждой проверки. Список probes означает попытку фиксированного локального запуска, а не его успех. Изменение сравнению с 0.10.0: недоступный target и ожидаемые ошибки чтения сообщаются как failed checks, а не пробрасываются из `doctor`.

`status` — `pass`, `warn` или `fail`. `passed` означает отсутствие `fail`; предупреждения допустимы. Exit codes CLI: 0 при отсутствии fail, 1 при failed doctor, 2 при ошибке CLI arguments. Успех не подтверждает Telegram identity, отсутствие другого polling consumer, webhook, backend auth, реальные устройства или установку всех зависимостей.

`reason` — машинная причина, связанная с `name`. Текст `detail` предназначен для человека. Не разбирайте сообщение регулярным выражением; используйте причины. Для предупреждений и ошибок `remediation.summary` объясняет требуемое действие, а `remediation.commands` содержит массивы `argv`, контекст `cwd` (`project` или `mini-app`) и `requires_substitution`. Команды не содержат пользовательский token, путь из ошибочного ввода или содержимое manifest. Их нельзя запускать автоматически только по наличию поля.

`python` в рекомендации означает interpreter окружения, из которого вы запустили doctor. Используйте его явный путь, если shell выбирает другой Python. На Windows npm-команды используют `npm.cmd`. Каждый `argv` — отдельные аргументы, не shell-строка: пути с пробелами передаются одним аргументом. `<PROVIDED_WHEEL>` и `<PROVIDED_TARBALL>` замените предоставленными локальными артефактами согласованной версии. Имена нашей библиотеки не означают публикацию в PyPI/npm. Поле `requires_substitution` не является проверкой подлинности артефакта.

```python
from telegram_patterns.cli import doctor

report = doctor('.', require_token=False)
for check in report['checks']:
    if check['status'] != 'pass':
        print(check['name'], check['reason'], check['remediation']['summary'])
        # Показываем план человеку; commands здесь не исполняются.
        for command in check['remediation']['commands']:
            print(command['cwd'], command['argv'])
```

## Что исправлять

| Проверка / reason | Действие и предел |
| --- | --- |
| `project-unavailable`, `project-not-directory`, `linked-project` | Укажите доступный настоящий каталог проекта. Doctor отказывается читать дерево через известный symbolic link или Windows junction; создание нового проекта не требуется. |
| `python-too-old` | Выберите Python >=3.11 и отдельное окружение приложения; установка Python не выполняется. |
| `library-not-installed`, `library-version-invalid` | Установите предоставленный wheel в тот же interpreter. Source import без metadata не считается корректной установкой. |
| `sdk-missing`, `sdk-incompatible` | Нужен aiogram >=3.31,<4 для нашего starter. План предлагает pip check и предоставленный wheel с extra; ограничения существующего приложения проверяются перед установкой. Если pip отсутствует, первая рекомендация — `python -m ensurepip`. |
| `sdk-not-tested`, `node-not-tested` | Проверьте выбранную версию отдельно. Проверенный SDK — 3.31.0, Node — 24; технический minimum Node >=20 не рекомендует EOL версию для production. |
| `adapter-origin-unverified` | Aiogram import разрешается не в установленный SDK, например из локального aiogram.py. Проверьте имена и sys.path, сохраните собственный код. SDK не импортируется из такого пути. |
| `adapter-import-failed` | Проверьте целостность установленной библиотеки и совместимость SDK. Изолированный probe требует пакеты в окружении interpreter; source-only/user-site installation не подтверждается. С 0.12.0 первый импорт ограничен 30 секундами: в новом Windows consumer прежних 10 секунд оказалось недостаточно. Зависание или ошибка по-прежнему дают fail, raw exception и его конфигурационные данные не выводятся. |
| `missing-manifest` у `pyproject` | Предупреждение: допустим другой формат зависимостей; миграция на pyproject не обязательна. |
| `missing-manifest` у `mini-app-manifest` | Ошибка: каталог Mini App присутствует, но его package.json отсутствует. Для другого frontend layout используйте проверки проекта. |
| `manifest-not-file`, `linked-manifest`, `manifest-unreadable`, `manifest-encoding`, `manifest-too-large` | Нужен обычный доступный UTF-8 файл до 256 KiB. Чтение ограничено; link не служит способом читать другую конфигурацию. Существующие файлы не удаляются. |
| `toml-invalid`, `json-invalid` | Исправьте синтаксис в редакторе и повторите doctor. Payload не включается в сообщение. |
| `token-missing`, `token-format-invalid` | Для offline token не нужен; для live задайте BOT_TOKEN через механизм секретов приложения. `--require-token` превращает эту проверку в fail. Формат не доказывает действительность token. |
| `mini-app-dependency-missing` | `dependencies` должен быть object, а значение `@awesome-telegram/patterns` — непустая строка. Рекомендация установки предоставленного tarball применяется отдельно в mini-app; doctor сам не подтверждает installed version/build. |
| `npm-missing`, `node-missing`, `node-too-old`, `node-probe-failed` | Проверьте PATH и поддерживаемую Node LTS. Probe имеет timeout 10 секунд; stdout/stderr не отражаются при ошибке. В child передаются только PATH и системные переменные, без BOT_TOKEN, NODE_OPTIONS и payment secrets. |

Причины pass: `python-supported`, `library-installed`, `sdk-supported`, `adapter-ready`, `toml-valid`, `token-format-valid`, `mini-app-dependency-declared`, `npm-on-path`, `node-supported`. API пока experimental; новые проверки и причины могут добавляться вместе с версией. Отчет не является sandbox: используйте доверенные установленный SDK/Node и стабильное дерево проекта; проверка link перед чтением не гарантирует защиту от конкурентной замены файла другим процессом. Перед запуском doctor используйте установленный entry point, которому доверяете: диагностика не контролирует код, уже загруженный самим вызывающим приложением. Чистый SDK probe не исполняет приложение и не подтверждает его зависимости/sys.path во время настоящего запуска.

Проверка поставки исполняет doctor из SDK-free wheel, затем в отдельном новом venv выполняет рекомендованные ensurepip/pip check/local-wheel installation и npm local-tarball installation. Повторный doctor проверяет исправленное окружение. Payload canaries, отсутствие/неверный token, неверная структура JSON, поврежденный TOML, отсутствующий PATH и недоступный target не раскрывают секреты. Локальные aiogram.py и aiohttp.py с намеренным файловым эффектом не исполняются: первая подмена отклоняется до probe, зависимость загружается из установленного окружения. Сохранность файлов сравнивается вокруг каждого диагностического запуска. Это исполняемые проверки, без утверждения о независимом агенте или человеческом исследовании удобства.

Проверенные 2026-10-04 источники: [pip install: local archives и interpreter](https://pip.pypa.io/en/stable/cli/pip_install/), [ensurepip: локальная установка pip](https://docs.python.org/3.13/library/ensurepip.html), [Python -I и -B](https://docs.python.org/3.13/using/cmdline.html#cmdoption-I), [Node --version](https://nodejs.org/api/cli.html#--version). Установленный SDK и runnable consumers проверяются отдельно; Telegram API этой диагностикой не меняется.
