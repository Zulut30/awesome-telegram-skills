# Проверка библиотеки 0.1.1

3 октября 2026 года, Windows. Выпуск исправляет воспроизведенные ошибки общего Python/TypeScript API и добавляет повторяемую проверку поставки. Десять групп компонентов и два независимых runtime-пакета сохранены. Публикация в PyPI/npm не выполнялась.

## Что исправлено

| Сценарий | Поведение до исправления | Проверенный результат 0.1.1 |
| --- | --- | --- |
| SQLite callback делает INSERT, затем commit | Ошибка обнаруживалась после commit: одна запись оставалась без ledger, повтор мог создать дубль | Authorizer запрещает управление транзакцией до commit; эффект и ledger откатываются вместе |
| Callback делает INSERT и executescript | Неявный COMMIT сохранял первый INSERT, скрипт добавлял второй; итоговая ошибка оставляла две записи | Неявный COMMIT запрещен, записей после отказа нет; обычные execute/executemany и вложенные savepoints работают |
| Сырой initData содержит одиночный surrogate | Наружу выходил UnicodeEncodeError | InvalidInitData без raw данных/токена в ошибке |
| Endpoint успешно отвечает HTTP 204/205 | Пустое тело объявлялось invalid-response | Decoder получает null; решение о допустимом результате остается в его контракте |
| Сервер обрывает тело после HTTP headers | Обрыв объявлялся ошибкой JSON | ApiError network; некорректный JSON и отказ decoder сохраняют invalid-response |
| Первый subscriber или частичная регистрация SDK падает | Неуспешная подписка/SDK listeners оставались активными, start нельзя было повторить | Подписки очищаются; последующий start выполняется без утечки |
| Вызывающий код меняет options.scope/ttlMs | Store записывал новый account scope под старым ключом и повреждал исходный черновик | Scope/TTL фиксируются при создании; новый аккаунт требует нового store |
| В DOM уже есть ID, который выбирает поле | Label фокусировал чужой input | Непрозрачные ID и проверка занятых input/hint/error; отдельно проверен fallback в Document без window/crypto |
| Telegram передает semantic theme colors | Секция, подсказка, разделитель и ошибка использовали прежние fallback colors | Применены соответствующие ThemeParams; native controls получают light/dark color-scheme |
| Официальный SDK загружен вне Telegram | Одного объекта WebApp было достаточно для insideTelegram=true | Platform unknown дает false; без platform сохранена совместимость прежних адаптеров. Snapshot не устанавливает личность |

Первые прогоны новых regression tests воспроизвели три проблемных Python-сценария и пять TypeScript-сценариев: Python baseline (`output/pattern-library-0.1.1/baseline-python.log`, локальный артефакт), TypeScript baseline (`output/pattern-library-0.1.1/baseline-typescript.log`, локальный артефакт). В UI baseline (`output/pattern-library-0.1.1/browser-baseline/component-contract.json`, локальный артефакт) сохранены ошибочный label focus, игнорируемые semantic colors и color-scheme=normal. Проверка fallback ID добавлена к финальному browser suite.

SQLite callback остается доверенным кодом приложения. Он не должен менять authorizer/режим транзакций, закрывать connection или выполнять внешний сетевой эффект. Authorizer защищает от случайного нарушения контракта; произвольный Python-код он не изолирует. Scope и права проверяются сервисом до эффекта и до replay.

## Выполненные проверки

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| Python core | Wheel установлен в новый venv без aiogram; публичный HMAC import и fixture выполнены | core-smoke.log (`output/pattern-library-0.1.1/core-smoke.log`, локальный артефакт) |
| SQLite example | Два отдельных процесса вернули одинаковый booking ID, второй с replayed=true | Первый вызов (`output/pattern-library-0.1.1/booking-first.log`, локальный артефакт), повтор (`output/pattern-library-0.1.1/booking-replay.log`, локальный артефакт) |
| Python SDK consumer | 21/21 тест из установленного финального wheel; aiogram 3.31.0, dependency check прошел | Тесты (`output/pattern-library-0.1.1/python-tests.log`, локальный артефакт), pip check (`output/pattern-library-0.1.1/sdk-dependencies.log`, локальный артефакт) |
| TypeScript consumer | 15/15 Node tests через bare import установленного tarball; реальные локальные HTTP endpoints, timeout/cancel, redirect и обрыв тела | Тесты (`output/pattern-library-0.1.1/typescript-tests.log`, локальный артефакт) |
| Публичные types/CSS | Реальный Mini App example прошел strict typecheck против установленных declarations; CSS subpath читается из пакета | Typecheck (`output/pattern-library-0.1.1/consumer-typecheck.log`, локальный артефакт), CSS (`output/pattern-library-0.1.1/packaged-style.log`, локальный артефакт) |
| Browser UI | 141 assertion, 14 viewport/theme cases на Chrome 154.0.8037.97; 14 screenshots | JSON (`output/pattern-library-0.1.1/browser/report.json`, локальный артефакт), component contract (`output/pattern-library-0.1.1/browser/component-contract.json`, локальный артефакт) |
| Переносимый навык | CLI скопировал только telegram-code-patterns в новый временный проект, все три файла совпали побайтово, local reference на месте | Копирование (`output/pattern-library-0.1.1/skill-install.json`, локальный артефакт) |
| Метаданные/ссылки набора | 41/41 навык, frontmatter/UI metadata, переносимые local references и Python syntax прошли валидатор | [validate_skills.py](../scripts/validate_skills.py) |
| Помощники набора | 16/16 root tests установщика/индекса, без пропусков | Команда ниже, [tests](../tests) |

Финальный consumer run использовал Python 3.13.12, aiogram 3.31.0, Node 24.19.0, npm 12.0.2, TypeScript 7.0.2, Playwright 1.63.0, uv 0.12.3. Это проверенная среда выпуска; все поддерживаемые версии Python/Node отдельно не прогонялись.

Consumer-проекты находятся вне checkout. Проверены installed module origin, core без SDK, настоящий Dispatcher с synthetic updates и чтение persistence между процессами. TypeScript suite использует установленный публичный package entrypoint; реализации компонентов в consumer не копируются. Browser suite проверяет собранный workspace-пример; это отдельная область проверки от Node consumer. Вручную просмотрены узкий экран 320px в темной теме и desktop 1440px в светлой: поля/подсказки не перекрываются, основное действие видно при прокрутке, широкая форма разделена на две колонки.

В финальном Chrome-прогоне потерянного ответа измерены четыре фактических HTTP POST и один серверный effect при одной прикладной попытке fetch. GET сверки восстановил тот же результат. Количество транспортных повторов зависит от браузера/сети; контракт не обещает одну доставку. Устойчивый operation ID и серверная дедупликация необходимы для записей.

## Поставка и воспроизведение

distribution-report.json (`output/pattern-library-0.1.1/distribution-report.json`, локальный артефакт) содержит итог passed=true, 18 этапов с exit_code=0, путь временных consumers, browser report и SHA256 финальных файлов:

| Артефакт | Байты | SHA256 |
| --- | --- | --- |
| awesome_telegram_patterns-0.1.1-py3-none-any.whl | 10218 | d24ea252a36f1928f38eac05f16aa4e7f5956a253cdf27dee9eb1fd30097847e |
| awesome-telegram-patterns-0.1.1.tgz | 10221 | 8c4a5e12818e78d1b1b7d5afac1b6fba0acff116fc100c16e38f40dc2e3254e3 |

Из корня репозитория:

```powershell
npm.cmd ci
python scripts/verify_pattern_packages.py
uv run --with "PyYAML>=6,<7" python scripts/validate_skills.py
python -m unittest discover -s tests -v
```

[Помощник проверки](../scripts/verify_pattern_packages.py) действительно собирает и устанавливает пакеты в свежие окружения, выполняет примеры/тесты и сохраняет логи каждого этапа. Нужны Python >=3.11, uv, Node/npm и установленный Chrome; можно задать CHROME_PATH. Артефакты лежат в output/pattern-library-0.1.1/dist. Consumer-проекты остаются по пути из JSON для просмотра; helper не удаляет чужие каталоги.

Опция --skip-browser явно записывает browser=skipped. Она проверяет пакетную поставку, UI требует отдельного запуска. Повторный запуск строит новые артефакты и обновляет отчет текущей версии; при несовпадении версий/каталога или неуспешном этапе проверка завершается ошибкой. Исторические артефакты/отчеты 0.1.0 сохранены отдельно.

## Границы результата

Новые сценарии выполнены основным агентом через regression/consumer/browser tests; отдельной новой независимой агентной оценки 0.1.1 не было. [Отчет 0.1.0](component-library-review.md) остается доказательством независимых consumers именно первого выпуска. Правки навыка обновляют локальный API snapshot; автоматическая активация навыка загрузчиком этим прогоном не проверена.

Живой Telegram, физические телефоны/планшеты/ПК с Telegram, настоящая soft keyboard, screen reader, payments и native permissions не проверялись. Browser viewport подтверждает локальную геометрию/ввод/темы; реальная inset policy и theme contrast требуют проверки целевых клиентов. Profile/MTProto/payment provider adapters не добавлялись. Mini App example по-прежнему использует loopback mock backend, память и fixture actor; production session/ACL и durable unknown-operation recovery остаются у приложения.

Первичные источники и точный контракт 0.1.1 указаны в [Python README](../packages/python/README.md), [TypeScript README](../packages/typescript/README.md) и [sources.md](sources.md). Дата относится только к перечисленным проверенным контрактам.

Логи и снимки с путями `output/…` — локальные артефакты исторических проверок. Они не входят в Git и не доступны в свежем клоне. Для текущей принятой версии смотрите [сохраненную приемку 031](v1-checks/031.json); для нового прогона выполните `python scripts/verify_pattern_packages.py`.
