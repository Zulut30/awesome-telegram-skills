# Сервисный бот: запись и напоминание

Пример пункта 017 использует публичные API локальной библиотеки 0.24.0 и aiogram 3.31.0: BotSettings, SQLiteOnce, TextField/text_form_router, command_router/command_menu, run_bot и StubSession. Это отдельное приложение `awesome-telegram-service-example` 0.1.0; его классы не входят в публичный API библиотеки. Python >=3.11; приемка — Windows/Python 3.13.12 и Linux/Python 3.13 с библиотекой 0.24.0; CI проверяет пример на текущей версии библиотеки.

Сценарий: `/start` → `/slots` → `/book` → код слота → комментарий → проверка → подтверждение → `/status`. Две услуги и четыре слота создаются один раз для демонстрации. Время показано в UTC; свободные слоты и срок проверяются сервером внутри транзакции. Рестарт не создаёт новые слоты вместо занятых. Для рабочего расписания подключите свой календарь; timezone UX — отдельная задача.

SQLite хранит шаг диалога, operation ID, записи, согласие и задания напоминаний. Проверка автора/личного чата и владельца объекта выполняется перед эффектом и возвратом сохранённого результата. Слот резервируется уникальным индексом; effect, replay result и намерение напоминания сохраняются одной транзакцией SQLiteOnce. Комментарий выводится plain text без parse mode. `/cancel_booking N` отменяет только свою запись; `/back` и `/cancel` работают до начала подтверждения.

## Локальная установка

В новом окружении укажите предоставленный wheel библиотеки и каталог этого примера:

```powershell
$patternWheel = 'C:\provided\awesome_telegram_patterns-0.24.0-py3-none-any.whl'
$serviceProject = 'C:\provided\service-bot'
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install "${patternWheel}[aiogram]" 'aiogram==3.31.0' $serviceProject
```

```bash
PATTERN_WHEEL=~/provided/awesome_telegram_patterns-0.24.0-py3-none-any.whl
SERVICE_PROJECT=~/provided/service-bot
python3 -m venv .venv
.venv/bin/python -m pip install "${PATTERN_WHEEL}[aiogram]" 'aiogram==3.31.0' "$SERVICE_PROJECT"
```

Пакеты пока локальные; installation может получать SDK из registry. Для существующего приложения сохраняйте его SDK/БД: используйте service contract и соответствующий адаптер проекта. SQLite и этот aiogram пример не требуют смены уже принятого стека.

## Проверка без Telegram

Из checkout библиотеки соберите wheel текущей версии и проверьте пример с ним:

```bash
python scripts/build_release.py --ref HEAD --output output/release
```

```bash
python scripts/verify_service_bot.py --wheel output/release/awesome_telegram_patterns-0.24.0-py3-none-any.whl --output output/service-bot-check
```

Output должен быть новым каталогом. Скрипт собирает и устанавливает приложение с wheel библиотеки в отдельный consumer вне репозитория. Проверяет origin, типы, девять тестов, живые SQLite-транзакции, отдельные процессы диалога, аварийный выход после commit, повтор того же подтверждения и напоминание после рестарта. Получатель напоминания сопоставляется с владельцем записи. Второй процесс на ту же базу отклоняется; после аварии OS освобождает lock. Project shadow modules/.env не исполняются и не читаются. Synthetic SDK/StubSession не имеет HTTP fallback; реальные Telegram delivery/device proof отсутствуют.

## Запуск с тестовым ботом

Только после отдельной настройки BOT_TOKEN в текущем окружении, проверки существующего webhook/getUpdates consumer и выбора постоянного пути БД:

```powershell
& .\.venv\Scripts\telegram-service-example.exe --database 'C:\service-data\service.sqlite'
```

```bash
.venv/bin/telegram-service-example --database ~/service-data/service.sqlite
```

Parent каталога БД должен существовать. Один процесс владеет одной базой и `.lock` файлом на локальном диске; известные links отклоняются. Дополнительные workers/сетевой диск не поддержаны. Процесс держит OS file lock до остановки уведомлений и FSM; память используется только для взаимного исключения событий в этом процессе. Состояние диалога хранится в SQLite без TTL, который мог бы уничтожить pending ID. Не удаляйте базу или данные неизвестной операции для повторного старта. При schema/corrupt данных выполните сверку и явную миграцию.

Live entrypoint явно заменяет command menu тестового бота и запускает polling. Автоматической смены webhook или удаления updates нет. Offline verifier не вызывает entrypoint и не читает BOT_TOKEN.

## Docker (необязательно)

Docker не нужен: установка, проверка и запуск выше работают без него. Если бот удобнее держать в контейнере, рядом лежат `Dockerfile` и `compose.yaml`. Контекст сборки — корень checkout библиотеки: образ устанавливает `packages/python` и этот пример, поэтому команды выполняются из корня. Нужен Docker Compose 2.24 или новее.

```bash
cp examples/service-bot/.env.example examples/service-bot/.env
# впишите токен тестового бота в examples/service-bot/.env
docker compose -f examples/service-bot/compose.yaml up --build
```

```powershell
Copy-Item examples\service-bot\.env.example examples\service-bot\.env
# впишите токен тестового бота в examples\service-bot\.env
docker compose -f examples/service-bot/compose.yaml up --build
```

`.env` не попадает ни в образ (`.dockerignore`), ни в git; Compose передаёт BOT_TOKEN в окружение процесса. Без файла `.env` Compose откажется запускаться. С незаменённой заглушкой процесс завершится сообщением `Replace the BOT_TOKEN placeholder with the token issued by @BotFather`; неверный токен или недоступный Bot API дают такое же короткое сообщение после getMe. Процесс работает от пользователя без прав root (uid 10001).

База SQLite и её `.lock` лежат в именованном томе `service-data` (`/data` в контейнере) и переживают пересборку образа. Одна база — один контейнер: не используйте `--scale`, не подключайте том ко второму контейнеру и не кладите базу на сетевой том — OS lock надёжен только на локальном диске. `docker compose -f examples/service-bot/compose.yaml down` сохраняет том; `down -v` удаляет базу с записями без возможности восстановления.

`restart: unless-stopped` поднимает процесс после сбоя сети и перезапуска Docker; ошибка конфигурации тоже будет повторяться, поэтому смотрите `docker compose -f examples/service-bot/compose.yaml logs`. Контейнер работает через polling, не открывает портов и не меняет webhook: перед запуском убедитесь, что у бота нет webhook и другого getUpdates consumer. Webhook-режим требует HTTPS и reverse proxy, в этом примере его нет.

Если Docker Hub недоступен, задайте зеркало базового образа: `PYTHON_IMAGE=mirror.gcr.io/library/python:3.13-slim docker compose -f examples/service-bot/compose.yaml up --build`. За прокси с собственным CA передайте сертификат секретом сборки: `docker build --secret id=ca,src=ca.pem -f examples/service-bot/Dockerfile .`. Секрет доступен только шагу `pip install` и не сохраняется в слоях образа.

Проверка контейнера без Telegram: `python scripts/verify_docker_example.py` из корня собирает образ, ожидает понятную ошибку заглушки токена, проходит офлайн-фазы `start` и `review` в разных контейнерах на одном томе и удаляет проект, том и образ. Существующий `.env` скрипт не читает и не перезаписывает: при его наличии он останавливается. Для зеркала или прокси добавьте свой override: `--compose-file my-override.yaml`. CI выполняет эту проверку на Ubuntu.

## Напоминания и неизвестный результат

`/reminders_on` даёт согласие; `/reminders_off` выключает и убирает не начатые задания. Повторное согласие активирует только ещё не попытанные будущие задания. До начала отправки проверяются согласие, статус записи и время; уже начатую отправку отозвать нельзя.

Задание проходит `pending → sending → sent`. Claim сохраняется до SDK запроса. Timeout/невалидный ответ/cancellation или авария между отправкой и сохранением результата переводят его в `unknown`, сохраняя ID. После рестарта такое задание автоматически не отправляется повторно: Bot API sendMessage не предоставляет ключ idempotency, поэтому может потребоваться ручная сверка. `/status` показывает, если доставка не подтверждена.

Forbidden прекращает отправки этому пользователю. Явный flood rejection учитывает retry_after, не более трёх попыток; другие неоднозначные ошибки не повторяются. Просроченное или отменённое задание пропускается. Это небольшой single-process пример, не универсальная очередь/rate limiter или готовая production эксплуатация. Восстановление accepted updates, общий outbox, multiworker FSM, мониторинг, backups и device/live приемка закрываются отдельными пунктами плана.

5 октября 2026 частично проверены [BaseStorage/MemoryStorage](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html), установленный aiogram 3.31.0 (StorageKey и порядок startup/shutdown), [Bot API ResponseParameters](https://core.telegram.org/bots/api#responseparameters), sendMessage и [Python SQLite transactions](https://docs.python.org/3.13/library/sqlite3.html#transaction-control). Эти источники относятся к примеру, не обновляют полный API/payment каталог.

Остановка дожидается SQLite-операции в потоке даже при повторной отмене worker; только затем освобождает process lock. Отмена `asyncio.to_thread` сама по себе не прекращает запись. Проверено отдельным тестом остановки на операции claim. Освобождение lock не означает, что неизвестная отправка стала успешной: после старта она остаётся `unknown`.

Дополнительно проверено 2026-10-05: [asyncio shield и to_thread, Python 3.13](https://docs.python.org/3.13/library/asyncio-task.html#asyncio.shield).

Docker-часть сверена 2026-10-07: [Compose services: env_file, restart](https://docs.docker.com/reference/compose-file/services/), [Compose build: args, secrets, network](https://docs.docker.com/reference/compose-file/build/), [optional env_file с Compose 2.24.0](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/).
