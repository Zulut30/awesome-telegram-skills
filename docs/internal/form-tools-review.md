# Формы ботов 0.3.0

3 октября 2026 года. В библиотеку добавлена одна группа компонентов: TextField, InvalidField, FormSubmission и text_form_router. Всего 17 групп, два независимых локальных пакета; публикация в PyPI/npm не выполнялась. TypeScript API сохранен.

## Что делает компонент

Поля задаются списком, без собственного FSM framework. Router подключается к текущему aiogram Dispatcher с включенным FSM и actor-scoped event isolation. Ordinary private chat: /apply → поля → сводка → подтверждение. /back удаляет ответы с предыдущего шага, /cancel отменяет до отправки; /help идет к проектному Router. Неверный текст/медиа не меняют текущий шаг. Пределы компонента: до 10 полей, 256 UTF-16 units на значение, bounded labels/prompts. Ответы и сводка plain text.

Кнопка подтверждения связана с текущими owner, operation_id и review message_id. Все callbacks matching prefix ACK до сервиса, включая старые/чужие/недоступные. FormSubmission копирует values в immutable mapping и исключает их из repr. Повтор текста с тем же message_id не заполняет следующий шаг. Команды/состояние других dialogs не перехватываются; unrelated host FSM data сохраняются при завершении/отмене.

Перед первым service call сохраняется submission_started. При exception/cancellation ответы и operation_id остаются, изменение/отмена/новый /apply блокируются; повтор последней кнопки вызывает сверку той же операции. Сервис проверяет права до effect/replay, надежно сохраняет единственную запись и возвращает подтвержденный результат. Известный окончательный отказ без неизвестного effect тоже можно вернуть plain-text ответом: это завершает форму. Не выдавайте неопределенный исход за окончательный отказ. После успешного return форма очищается до feedback: сбой ответа не повторяет service call. Несовместимая schema состояния требует миграции/сверки, без автоматического сброса pending identity.

## Исполняемый пример

[form_bot.py](../../examples/python/form_bot.py) строит реальную композицию Router + Applications.submit + SQLiteOnce. Пользователь создает только свою заявку; сервис повторно проверяет actor/private scope и значения. SQL effect и replay result сохраняются в одной transaction, sync SQLite вынесен через asyncio.to_thread. Отдельный SQLite connection создания схемы и чтения результата закрывается явно, в том числе на Windows.

[offline_form.py](../../examples/python/offline_form.py) использует тот же create_app с настоящим Dispatcher и StubSession: invalid input → edit → review → submit → stale confirmation. Проверяется реальная SQLite строка, два ACK и очистка FSM. BOT_TOKEN/Telegram HTTP не нужны. Тестовый live entrypoint с BOT_TOKEN явно заменяет default command menu бота.

## Проверка

Предварительно на Python 3.12 с aiogram 3.31.0 прошли 56 package tests: 39 прежних и 17 новых. Проверены trim/Unicode/bounds, validator errors, immutable submission, review до effect, возврат/отмена, /help, две личности, повтор текста, старая/чужая/недоступная кнопка, настоящая гонка двух подтверждений с блокирующим callback, commit + потеря ответа + replay с прежним ID, task cancellation, сбой feedback, выключенный FSM/default isolation и несовместимая schema. Offline пример оставил одну строку приложения и закрыл session.

Полная проверка финального wheel/tarball прошла через `python scripts/verify_pattern_packages.py` после `npm.cmd ci`: 20 этапов, Python 3.13.12/aiogram 3.31.0, 56 Python tests, 15 TypeScript tests и 141 browser assertion в Chrome 154.0.8037.97 (7 размеров × 2 темы). Core установлен без aiogram; SDK и TypeScript пакеты установлены в отдельные свежие consumer-проекты вне checkout. Проверены public exports, strict declarations/CSS, существующий каталог и новая форма. Логи, артефакты и итоговый результат: distribution-report.json (`output/pattern-library-0.3.0/distribution-report.json`, локальный артефакт).

CLI скопировал только telegram-code-patterns в temporary project: все 5 файлов byte-identical, включая локальный form-recipes.md. Python snippet из скопированного recipe подключен к существующему Dispatcher через установленный wheel, /ping сохранился; запись появляется только после подтверждения, повтор оставляет одну строку. Отдельная проверка missing BOT_TOKEN завершилась до создания БД. SHA256 артефактов, source package files и README payload в wheel/tarball совпали с итоговым source: recipe-evidence.json (`output/pattern-library-0.3.0/recipe-evidence.json`, локальный артефакт), воспроизводимая проба (`output/pattern-library-0.3.0/check_release_evidence.py`, локальный артефакт).

Структура всех 41 навыка и 16 root tests прошли. Сценарии навыка обновлены в [evaluation.md](../evaluation.md); это исполнение готового recipe/contract, без нового независимого испытания решения агентом по запросу.

| Артефакт | Bytes | SHA256 |
| --- | --- | --- |
| Python wheel (`output/pattern-library-0.3.0/dist/awesome_telegram_patterns-0.3.0-py3-none-any.whl`, локальный артефакт) | 24885 | 7f09959d0c4d134d073d36e9c5ac0fbfc262a5ce0f1d5d62f9b4957278d4ee07 |
| TypeScript tarball (`output/pattern-library-0.3.0/dist/awesome-telegram-patterns-0.3.0.tgz`, локальный артефакт) | 10278 | e91be1e103413b672cf07c411d9229d0c77d88c12dc5b77a28b0313d450b876d |

## Границы

Form Router не выполняет durable acceptance updates, business ACL, внешний сетевой retry, storage migrations или автоматическую retention. SDK isolation не заменяет service idempotence. SimpleEventIsolation — один процесс, MemoryStorage — потеря формы после рестарта и отсутствие автоматического TTL. Если продукт требует восстановления/нескольких workers/retention, host задает подходящий storage, согласованный lock, durable operation record и recovery UI. Pending operation identity должна сохраняться до сверки независимо от TTL draft. Потеря FSM/сообщения в учебном примере не дает встроенного восстановления; бизнес-запись/ledger в SQLite сохраняются.

Группы, Business connections, media/contact steps и ветвящиеся процессы используют SDK проекта. Live Telegram delivery, Bot API permissions, физические клиенты и платежи в этом проходе не проверялись. Доказательство browser matrix относится только к Mini App примеру, не к Telegram UI формы. Прямые изменения других Telegram-навыков не выполнялись.

## Источники

Для перечисленных FSM контрактов 3 октября 2026 проверены [aiogram FSM](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/index.html), [storage](https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html) и [Dispatcher](https://docs.aiogram.dev/en/latest/_modules/aiogram/dispatcher/dispatcher.html). Код установленного aiogram 3.31.0 подтвердил default DisabledEventIsolation, actor-scoped storage key и чтение raw_state после взятия lock. Общая дата источников других компонентов не обновлялась.

Логи и снимки с путями `output/…` — локальные артефакты исторических проверок. Они не входят в Git и не доступны в свежем клоне. Для текущей принятой версии смотрите [сохраненную приемку 031](../v1-checks/031.json); для нового прогона выполните `python scripts/verify_pattern_packages.py`.
