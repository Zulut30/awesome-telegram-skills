# Первый запуск: бот и экран Mini App

Этот пример проверен на Windows с PowerShell, Python 3.13, Node.js 24 и локальной поставкой **0.16.0**. Требуются Python >=3.11 и Node.js >=20; проверенные версии перечислены в матрице поддержки проекта. Пакеты пока не опубликованы в PyPI/npm: получите wheel и tarball от владельца проекта. Оба файла должны относиться к одной поставке.

До начала: установка Python/npm-зависимостей может использовать интернет. `init`, `offline.py` и локальная форма не требуют настоящего токена, аккаунта Telegram или платежных ключей. Бот выполняет настоящий aiogram Dispatcher через `StubSession`; экран проверяет ввод локально. Backend, серверная авторизация и отправка формы здесь еще не подключены.

## 1. Установить локальный CLI

Откройте PowerShell. Замените путь `$tgArtifacts` на каталог с предоставленными файлами. `$tgWorkspace` должен быть новым: если он уже существует, выберите другое имя. Команды не удаляют прежние проекты. Для порта, занятого другим приложением, задайте другое значение `$tgPreviewPort`.

<!-- quickstart:parameters -->
```powershell
$tgArtifacts = 'C:\path\to\pattern-library-0.16.0\artifacts'
$tgWorkspace = Join-Path $env:TEMP 'telegram-first-run'
$tgPreviewPort = 4173
```

<!-- quickstart:setup -->
```powershell
$ErrorActionPreference = 'Stop'
$tgWheel = Join-Path $tgArtifacts 'awesome_telegram_patterns-0.16.0-py3-none-any.whl'
$tgTarball = Join-Path $tgArtifacts 'awesome-telegram-patterns-0.16.0.tgz'
if (!(Test-Path -LiteralPath $tgWheel -PathType Leaf) -or !(Test-Path -LiteralPath $tgTarball -PathType Leaf)) { throw 'Нужны оба локальных артефакта 0.16.0' }
if (Test-Path -LiteralPath $tgWorkspace) { throw 'Выберите новый каталог tgWorkspace' }
New-Item -ItemType Directory -Path $tgWorkspace | Out-Null
Set-Location -LiteralPath $tgWorkspace
python -m venv tools
if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать tools venv' }
& .\tools\Scripts\python.exe -m pip install --no-input --disable-pip-version-check $tgWheel
if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить локальный wheel' }
```

Окружение `tools` содержит CLI и ядро библиотеки; aiogram будет установлен в окружении созданного бота. Активация venv и изменение ExecutionPolicy не нужны.

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

<!-- quickstart:preview -->
```powershell
& ..\.venv\Scripts\python.exe -m http.server $tgPreviewPort --bind 127.0.0.1 --directory .
```

Откройте **http://127.0.0.1:4173** в браузере; при смене порта используйте свое значение. Нужен HTTP, поскольку страница импортирует ES modules. Нажмите «Проверить форму» с пустым полем: появится «Введите имя.», фокус перейдет к полю. Введите имя и повторите: появится сообщение о локальной проверке и отсутствии отправки. Измените ширину окна и светлую/темную тему ОС: введенное имя сохраняется. Сервер слушает только loopback; остановите его `Ctrl+C` в этом окне.

## Когда понадобится Telegram

Для настоящего бота получите отдельный тестовый BOT_TOKEN через BotFather и передайте его в окружение процесса; `.env.example` сам не загружается. Из каталога `my-bot` запускается `.\.venv\Scripts\python.exe app.py`. Этот запуск обращается к Telegram и явно устанавливает default command menu. Сначала проверьте отсутствие другого polling consumer и конфигурацию webhook; шаблон не удаляет webhook автоматически.

Для Mini App внутри Telegram понадобятся HTTPS-размещение, официальный WebApp SDK и выбранная точка запуска. До операций с пользовательскими данными подключите backend, проверку raw initData, сессию и объектные права. Локальная форма не выдает доступ и не подтверждает личность. Права Business и пользовательская MTProto-session не подключаются автоматически. Настоящие Telegram-клиенты и платежи проверяются отдельно.

Если существующий проект использует React, Vue, другую библиотеку бота или БД, подключайте нужные публичные API в его текущую архитектуру. Этот начальный шаблон нужен для нового небольшого примера; стабильность 1.0 для него еще не заявлена.

Для npm file path отдельно сверены [local paths](https://docs.npmjs.com/cli/v12/configuring-npm/package-json/#local-paths) и [tarball specs](https://docs.npmjs.com/cli/v12/using-npm/package-spec/#tarballs), 2026-10-04. Формат с буквальными пробелами проверен npm 12.0.2; percent-encoded URL в прежнем starter 0.9.1 давал ENOENT.
