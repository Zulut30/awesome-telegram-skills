# Локальная диагностика и исправления — 0.11.0

`python -m telegram_patterns doctor .` проверяет окружение нашего aiogram starter и принятую структуру `mini-app/package.json`. В существующем PTB/React/Vue проекте сохраняйте стек: отсутствие aiogram означает отсутствие readiness этого adapter, а не необходимость переписать приложение. Doctor читает локальные manifests и установленные package metadata, проверяет источник aiogram import и запускает фиксированную проверку установленного adapter в отдельном Python `-I -B` с cwd окружения. Каталог проекта, PYTHONPATH и user-site не входят в этот import probe. Для обнаруженного Mini App дополнительно выполняется `node --version`.

Doctor возвращает JSON. Без `--webhook` он не читает `.env`, не исполняет приложение, не устанавливает зависимости, не правит файлы проекта и не выполняет HTTP-запросы. SDK probe `-B` также не создает bytecode caches. Команды исправления — рекомендации для следующего явного действия. Установщики при отдельном запуске могут использовать registries. Единственный сетевой режим — явный `--webhook`, описанный ниже.

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
| `token-missing`, `token-format-invalid`, `token-placeholder`, `env-file-invalid` | Для offline token не нужен; для live задайте BOT_TOKEN через механизм секретов приложения. `--require-token` и `--webhook` превращают эту проверку в fail. `token-placeholder` — в BOT_TOKEN осталась заглушка из `.env.example`; `env-file-invalid` — `.env` проекта (читается только с `--webhook`) не разбирается как строки KEY=VALUE до 64 KiB. Формат не доказывает действительность token. |
| `mini-app-dependency-missing` | `dependencies` должен быть object, а значение `@awesome-telegram/patterns` — непустая строка. Рекомендация установки предоставленного tarball применяется отдельно в mini-app; doctor сам не подтверждает installed version/build. |
| `npm-missing`, `node-missing`, `node-too-old`, `node-probe-failed` | Проверьте PATH и поддерживаемую Node LTS. Probe имеет timeout 10 секунд; stdout/stderr не отражаются при ошибке. В child передаются только PATH и системные переменные, без BOT_TOKEN, NODE_OPTIONS и payment secrets. |


## Webhook и очередь updates: `--webhook`

```bash
python -m telegram_patterns doctor . --webhook --expect polling
```

`--webhook` добавляет к локальным проверкам один read-only запрос `getWebhookInfo`. BOT_TOKEN берется из окружения, а если его там нет — из `.env` каталога проекта, как в `app.py` стартера; known link на `.env` не читается. Doctor не вызывает `setWebhook`, `deleteWebhook` и `getUpdates`, не обращается к вашему серверу и ничего не меняет. В отчете `network: true`, в `tool_probes_attempted` — `getWebhookInfo`. Token и путь webhook URL в отчет не попадают: показываются только схема, хост и порт, потому что путь часто содержит секрет. Запрос идет через `HTTPS_PROXY` и системные сертификаты, timeout — 10 секунд.

`--expect polling|webhook` говорит, как этот бот должен получать updates; без него конфликт дает предупреждение, а не fail. `--webhook-secret-env NAME` задает переменную с секретом для `secret_token` (по умолчанию `WEBHOOK_SECRET`), ее значение тоже ищется в окружении и затем в `.env`. Команды исправления читают BOT_TOKEN из окружения процесса, поэтому token не оказывается в argv и истории shell.

| Проверка / reason | Ситуация и действие |
| --- | --- |
| `token-valid`: `token-accepted`, `token-rejected` | Telegram принял или отклонил BOT_TOKEN (HTTP 401/404). При отклонении проверьте токен или выпустите новый в @BotFather — старый перестанет работать. |
| `webhook`: `token-required` | Запрос не отправлялся: сначала исправьте `token-format`. |
| `webhook`: `api-unreachable`, `api-error` | Bot API недоступен (сеть, DNS, прокси, сертификат прокси) или вернул не JSON Bot API. Проверьте доступ к api.telegram.org и `HTTPS_PROXY`, повторите. |
| `webhook`: `polling-available` | Webhook не установлен: polling через getUpdates доступен одному процессу. |
| `webhook`: `webhook-blocks-polling` (fail при `--expect polling`), `webhook-active` (warn без `--expect`) | Webhook установлен, поэтому getUpdates отвечает 409 Conflict. Если updates должен получать polling и сервер по этому адресу их больше не принимает, вызовите `deleteWebhook` без `drop_pending_updates` — очередь сохранится. Иначе запускайте бот в режиме webhook. |
| `webhook`: `webhook-set`, `webhook-not-set` | При `--expect webhook`: установлен (показаны хост, IP, `max_connections`, собственный сертификат) или нет. Для `webhook-not-set` команда `setWebhook` с `<WEBHOOK_URL>` и `secret_token`; порт 443, 80, 88 или 8443. |
| `webhook-pending`: `queue-empty`, `webhook-queue-ok`, `updates-waiting`, `webhook-backlog` | Сколько updates ждут. Без webhook очередь ждет polling процесс; при webhook предупреждение от 100 updates или при свежей ошибке доставки. Telegram хранит updates не дольше 24 часов; не удаляйте очередь ради диагностики. |
| `webhook-error`: `webhook-unreachable`, `webhook-tls`, `webhook-auth-rejected`, `webhook-path-not-found`, `webhook-server-error`, `webhook-bad-response`, `webhook-error` | Последняя ошибка доставки за 24 часа с текстом Telegram: нет соединения или DNS, сертификат, ответ 401/403 (не совпадает `secret_token` или мешает firewall/WAF), 404 (путь не обслуживается), 5xx (падает обработчик или proxy), другой не-2xx ответ, прочее. Более старая ошибка — `webhook-error-old`, без ошибок — `webhook-no-errors`. |
| `webhook-sync`: `sync-error` | Telegram сообщил об ошибке синхронизации updates за 24 часа; обычно временная, повторите позже и убедитесь, что updates получает один процесс. |
| `webhook-secret`: `secret-not-found`, `secret-invalid`, `secret-configured` | `getWebhookInfo` не сообщает, передан ли `secret_token`, поэтому проверяется только локальный секрет. Нет секрета — запросы к webhook нельзя отличить от чужих: сгенерируйте его (`secrets.token_urlsafe(32)`), передайте в `setWebhook` и отклоняйте запросы без совпадающего `X-Telegram-Bot-Api-Secret-Token`. Допустимы 1–256 символов `A-Z`, `a-z`, `0-9`, `_`, `-`. |

Вне `--webhook` поведение doctor не изменилось: сеть и `.env` не используются. Флаги `--expect` и `--webhook-secret-env` без `--webhook` — ошибка аргументов (код 2).

Причины pass: `python-supported`, `library-installed`, `sdk-supported`, `adapter-ready`, `toml-valid`, `token-format-valid`, `mini-app-dependency-declared`, `npm-on-path`, `node-supported`. API пока experimental; новые проверки и причины могут добавляться вместе с версией. Отчет не является sandbox: используйте доверенные установленный SDK/Node и стабильное дерево проекта; проверка link перед чтением не гарантирует защиту от конкурентной замены файла другим процессом. Перед запуском doctor используйте установленный entry point, которому доверяете: диагностика не контролирует код, уже загруженный самим вызывающим приложением. Чистый SDK probe не исполняет приложение и не подтверждает его зависимости/sys.path во время настоящего запуска.

Проверка поставки исполняет doctor из SDK-free wheel, затем в отдельном новом venv выполняет рекомендованные ensurepip/pip check/local-wheel installation и npm local-tarball installation. Повторный doctor проверяет исправленное окружение. Payload canaries, отсутствие/неверный token, неверная структура JSON, поврежденный TOML, отсутствующий PATH и недоступный target не раскрывают секреты. Локальные aiogram.py и aiohttp.py с намеренным файловым эффектом не исполняются: первая подмена отклоняется до probe, зависимость загружается из установленного окружения. Сохранность файлов сравнивается вокруг каждого диагностического запуска. Это исполняемые проверки, без утверждения о независимом агенте или человеческом исследовании удобства.

Проверенные 2026-10-04 источники: [pip install: local archives и interpreter](https://pip.pypa.io/en/stable/cli/pip_install/), [ensurepip: локальная установка pip](https://docs.python.org/3.13/library/ensurepip.html), [Python -I и -B](https://docs.python.org/3.13/using/cmdline.html#cmdoption-I), [Node --version](https://nodejs.org/api/cli.html#--version). Установленный SDK и runnable consumers проверяются отдельно; Telegram API этой диагностикой не меняется.

Webhook-режим сверен 2026-10-07 с [Bot API 10.3](https://core.telegram.org/bots/api): [getWebhookInfo и WebhookInfo](https://core.telegram.org/bots/api#getwebhookinfo), [setWebhook: secret_token, порты](https://core.telegram.org/bots/api#setwebhook), [deleteWebhook](https://core.telegram.org/bots/api#deletewebhook), [getUpdates: хранение 24 часа, не работает при webhook](https://core.telegram.org/bots/api#getting-updates).
