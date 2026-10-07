# Первый запуск: бот и экран Mini App

Этот пример проверяется на Windows (PowerShell), Ubuntu и macOS (bash) с Python 3.13, Node.js 24 и локальной поставкой **0.24.0**. Каждый шаг дан в двух вариантах: PowerShell для Windows и bash для Linux и macOS; выполняйте один из них. Требуются Python >=3.11 и Node.js >=20; проверенные версии перечислены в матрице поддержки проекта. Пакеты пока не опубликованы в PyPI/npm: скачайте wheel и tarball из GitHub Releases или получите их от владельца проекта. Оба файла должны относиться к одной поставке.

До начала: установка Python/npm-зависимостей может использовать интернет. `init`, `offline.py` и локальная форма не требуют настоящего токена, аккаунта Telegram или платежных ключей. Бот выполняет настоящий aiogram Dispatcher через `StubSession`; экран проверяет ввод локально. Backend, серверная авторизация и отправка формы здесь еще не подключены.

## 1. Установить локальный CLI

Откройте PowerShell (Windows) или терминал (Linux, macOS). Замените путь `$tgArtifacts` / `TG_ARTIFACTS` на каталог с предоставленными файлами. `$tgWorkspace` / `TG_WORKSPACE` должен быть новым: если он уже существует, выберите другое имя. Команды не удаляют прежние проекты. Для порта, занятого другим приложением, задайте другое значение `$tgPreviewPort` / `TG_PREVIEW_PORT`. Каждый bash-блок — одна цепочка команд: при ошибке она останавливается и печатает подсказку, не закрывая терминал.

<!-- quickstart:parameters -->
```powershell
$tgArtifacts = 'C:\path\to\pattern-library-0.24.0\artifacts'
$tgWorkspace = Join-Path $env:TEMP 'telegram-first-run'
$tgPreviewPort = 4173
```

<!-- quickstart-bash:parameters -->
```bash
TG_ARTIFACTS="$HOME/Downloads/pattern-library-0.24.0/artifacts"
TG_WORKSPACE="${TMPDIR:-/tmp}/telegram-first-run"
TG_PREVIEW_PORT=4173
```

<!-- quickstart:setup -->
```powershell
$ErrorActionPreference = 'Stop'
$tgWheel = Join-Path $tgArtifacts 'awesome_telegram_patterns-0.24.0-py3-none-any.whl'
$tgTarball = Join-Path $tgArtifacts 'awesome-telegram-patterns-0.24.0.tgz'
if (!(Test-Path -LiteralPath $tgWheel -PathType Leaf) -or !(Test-Path -LiteralPath $tgTarball -PathType Leaf)) { throw 'Нужны оба локальных артефакта 0.24.0' }
if (Test-Path -LiteralPath $tgWorkspace) { throw 'Выберите новый каталог tgWorkspace' }
New-Item -ItemType Directory -Path $tgWorkspace | Out-Null
Set-Location -LiteralPath $tgWorkspace
python -m venv tools
if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать tools venv' }
& .\tools\Scripts\python.exe -m pip install --no-input --disable-pip-version-check $tgWheel
if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить локальный wheel' }
```

<!-- quickstart-bash:setup -->
```bash
TG_WHEEL="$TG_ARTIFACTS/awesome_telegram_patterns-0.24.0-py3-none-any.whl" &&
TG_TARBALL="$TG_ARTIFACTS/awesome-telegram-patterns-0.24.0.tgz" &&
test -f "$TG_WHEEL" && test -f "$TG_TARBALL" &&
mkdir "$TG_WORKSPACE" && cd "$TG_WORKSPACE" &&
python3 -m venv tools &&
tools/bin/python -m pip install --no-input --disable-pip-version-check "$TG_WHEEL" ||
{ echo 'Не удалось: нужны оба артефакта 0.24.0 и новый каталог TG_WORKSPACE' >&2; false; }
```

Окружение `tools` содержит CLI и ядро библиотеки; aiogram будет установлен в окружении созданного бота. Активация venv и изменение ExecutionPolicy не нужны. В Linux и macOS Python вызывается как `python3`, а файлы окружения лежат в `bin/` вместо `Scripts\`.

## 2. Создать новый проект

Первая команда показывает 11 создаваемых файлов с `created: false`. Вторая создает `my-bot` с Python-ботом и TypeScript-формой. CLI не устанавливает зависимости. В манифестах будут абсолютные локальные ссылки (Python file URI / npm file path): при переносе проекта нужно предоставить новые пути к артефактам.

<!-- quickstart:init -->
```powershell
& .\tools\Scripts\python.exe -m telegram_patterns init .\my-bot --library $tgWheel --template bot-mini-app --typescript $tgTarball --dry-run
if ($LASTEXITCODE -ne 0) { throw 'Не удалось проверить план проекта' }
& .\tools\Scripts\python.exe -m telegram_patterns init .\my-bot --library $tgWheel --template bot-mini-app --typescript $tgTarball
if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать новый проект' }
Set-Location -LiteralPath .\my-bot
```

<!-- quickstart-bash:init -->
```bash
tools/bin/python -m telegram_patterns init ./my-bot --library "$TG_WHEEL" --template bot-mini-app --typescript "$TG_TARBALL" --dry-run &&
tools/bin/python -m telegram_patterns init ./my-bot --library "$TG_WHEEL" --template bot-mini-app --typescript "$TG_TARBALL" &&
cd ./my-bot ||
{ echo 'Не удалось создать новый проект' >&2; false; }
```

## 3. Выполнить offline-бота

<!-- quickstart:offline -->
```powershell
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать окружение бота' }
& .\.venv\Scripts\python.exe -m pip install --no-input --disable-pip-version-check .
if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить проект и aiogram' }
& .\.venv\Scripts\python.exe offline.py
if ($LASTEXITCODE -ne 0) { throw 'Offline-сценарий не прошел' }
& .\.venv\Scripts\python.exe -m telegram_patterns doctor .
if ($LASTEXITCODE -ne 0) { throw 'Есть локальные ошибки: прочитайте checks в doctor' }
```

<!-- quickstart-bash:offline -->
```bash
python3 -m venv .venv &&
.venv/bin/python -m pip install --no-input --disable-pip-version-check . &&
.venv/bin/python offline.py &&
.venv/bin/python -m telegram_patterns doctor . ||
{ echo 'Offline-сценарий или doctor не прошли: прочитайте вывод выше' >&2; false; }
```

Ожидаемый результат `offline.py`: `passed: true`, `network: false`, методы `SendMessage`, `AnswerCallbackQuery`, `SendMessage`, затем `session_closed: true`. Это `/start`, нажатие «Помощь» и ответ того же бота. В `app.py` находится используемая композиция. Предупреждение `token-format` в `doctor` допустимо для этого запуска; `passed` не доказывает работоспособность настоящего токена или backend.

## 4. Открыть экран Mini App

<!-- quickstart:frontend -->
```powershell
Set-Location -LiteralPath .\mini-app
npm.cmd install --ignore-scripts --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить frontend dependencies' }
npm.cmd run typecheck
if ($LASTEXITCODE -ne 0) { throw 'Ошибка типов frontend' }
npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend не собрался' }
```

<!-- quickstart-bash:frontend -->
```bash
cd ./mini-app &&
npm install --ignore-scripts --no-audit --no-fund &&
npm run typecheck &&
npm run build ||
{ echo 'Frontend не собрался: прочитайте вывод npm' >&2; false; }
```

<!-- quickstart:preview -->
```powershell
& ..\.venv\Scripts\python.exe -m http.server $tgPreviewPort --bind 127.0.0.1 --directory .
```

<!-- quickstart-bash:preview -->
```bash
../.venv/bin/python -m http.server "$TG_PREVIEW_PORT" --bind 127.0.0.1 --directory .
```

Откройте **http://127.0.0.1:4173** в браузере; при смене порта используйте свое значение. Нужен HTTP, поскольку страница импортирует ES modules. Нажмите «Проверить форму» с пустым полем: появится «Введите имя.», фокус перейдет к полю. Введите имя и повторите: появится сообщение о локальной проверке и отсутствии отправки. Измените ширину окна и светлую/темную тему ОС: введенное имя сохраняется. Сервер слушает только loopback; остановите его `Ctrl+C` в этом окне.

## Когда понадобится Telegram

Для настоящего бота получите отдельный тестовый BOT_TOKEN через BotFather и передайте его в окружение процесса; `.env.example` сам не загружается. Из каталога `my-bot` запускается `.\.venv\Scripts\python.exe app.py` (Windows) или `.venv/bin/python app.py` (Linux, macOS). Этот запуск обращается к Telegram и явно устанавливает default command menu. Сначала проверьте отсутствие другого polling consumer и конфигурацию webhook; шаблон не удаляет webhook автоматически.

Для Mini App внутри Telegram понадобятся HTTPS-размещение, официальный WebApp SDK и выбранная точка запуска. До операций с пользовательскими данными подключите backend, проверку raw initData, сессию и объектные права. Локальная форма не выдает доступ и не подтверждает личность. Права Business и пользовательская MTProto-session не подключаются автоматически. Настоящие Telegram-клиенты и платежи проверяются отдельно.

Если существующий проект использует React, Vue, другую библиотеку бота или БД, подключайте нужные публичные API в его текущую архитектуру. Этот начальный шаблон нужен для нового небольшого примера; стабильность 1.0 для него еще не заявлена.

Для npm file path отдельно сверены [local paths](https://docs.npmjs.com/cli/v12/configuring-npm/package-json/#local-paths) и [tarball specs](https://docs.npmjs.com/cli/v12/using-npm/package-spec/#tarballs), 2026-10-04. Формат с буквальными пробелами проверен npm 12.0.2; percent-encoded URL в прежнем starter 0.9.1 давал ENOENT.
