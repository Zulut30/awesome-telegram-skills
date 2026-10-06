# Проверка расширения набора

Дата: 3 октября 2026 года (Europe/Warsaw). Добавлены восемь навыков; всего 33. Каждый новый навык содержит короткий SKILL.md, один тематический reference и agents/openai.yaml. Обязательных соседних навыков, внешних сервисов или привязки к компьютеру нет.

## Добавленные области

Device QA отвечает за доказательства в настоящих клиентах; performance — за измерение и устранение конкретной причины тормозов; design system — за переиспользуемые компоненты. Python backend задает серверные контракты и durable операции; native capabilities — поддержку client API, permission и fallback. Notifications охватывает фоновые задания/отписку, observability — безопасный связанный output, localization — согласованные языки и форматирование.

Descriptions различают библиотеку компонентов и отдельный экран, instrumentation и текущий сбой, фоновые уведомления и единичный ответ. Стек существующего проекта сохраняется; FastAPI, Redis, Storybook и OpenTelemetry не становятся обязательными зависимостями.

## Проверки

| Проверка | Результат | Материал |
| --- | --- | --- |
| Формат и переносимость | 33 навыка прошли валидатор коллекции; 33/33 прошли официальный quick_validate в UTF-8 режиме | official-validation.json (`output/quality-extension/official-validation.json`, локальный артефакт) |
| Тесты репозитория | 16/16, без пропусков | repository-tests.txt (`output/quality-extension/repository-tests.txt`, локальный артефакт) |
| Установка через CLI | 33 навыка, 97 файлов; побайтовое совпадение, чистый dry run, отказ перезаписи | installer-roundtrip.json (`output/quality-extension/installer-roundtrip.json`, локальный артефакт) |
| Независимый выбор по descriptions | 28 запросов; подходящий выбор для новых/старых задач и NONE для трех запросов вне Telegram | routing-results.json (`output/quality-extension/routing-results.json`, локальный артефакт) |
| TypeScript prototype | 17 значимых тестов, typecheck и production build прошли | frontend-tests-build.txt (`output/quality-extension/frontend-tests-build.txt`, локальный артефакт) |
| Независимая browser suite | 68 проверок взаимодействия и геометрии прошли; page errors не обнаружены | frontend-agent-browser.json (`output/quality-extension/frontend-agent-browser.json`, локальный артефакт) |
| Браузерная матрица | 8 размеров × 2 языка × 2 темы: 32 состояния без горизонтального переполнения, с сохранением формы/услуги | frontend-browser.json (`output/quality-extension/frontend-browser.json`, локальный артефакт) |
| Отказ и поздний callback | Ручной адрес сохраняется после отказа и после результата старого запроса; подтверждение и повторное закрытие диалога работают | Тот же browser JSON |
| Modal keyboard | Tab/Shift+Tab проходят цикл кнопок; Escape возвращает focus инициатору | dialog-focus.json (`output/quality-extension/dialog-focus.json`, локальный артефакт) |
| Выборочная визуальная проверка | По 38 текстовых образцов в теме, минимальный contrast 5,46/8,56; измеренные активные цели не меньше 44×44 px | frontend-visual.json (`output/quality-extension/frontend-visual.json`, локальный артефакт) |
| Python prototype | 27/27 тестов; реальные HTTP и файловая SQLite, отдельные backend/worker процессы | backend-tests.txt (`output/quality-extension/backend-tests.txt`, локальный артефакт) |
| Конечный log output | 191 событие в аудите, 11 искусственных canaries, утечек не обнаружено | backend-summary.json (`output/quality-extension/backend-summary.json`, локальный артефакт), backend-log-audit.txt (`output/quality-extension/backend-log-audit.txt`, локальный артефакт) |

Routing агент читал только name/description, запросы не выполнял. Для неполного контекста компонентной галереи/метрик/календаря отмечено предположение о Telegram-проекте. Это проверка различимости descriptions, а не автоматического загрузчика.

Frontend агент получил новые навыки и задачу небольшой компонентной галереи/формы: русский/английский, две темы, date/price, fake location и ручной адрес. Backend агент получил задачу записи с SQLite, общими операциями бота/API, напоминанием через fake transport и логами. Они работали отдельно, не читали результаты друг друга и не меняли канонические навыки. Родитель независимо выполнял browser/Node/Python проверки.

## Дефект, найденный дополнительной пробой

Первоначальная frontend реализация блокировала второй запрос, но dispose того же экземпляра adapter отменял первый. Фактический Node probe дал pending → timeout вместо accepted: до исправления (`output/quality-extension/native-duplicate-before.json`, локальный артефакт). Новая проверка использовала переиспользуемый adapter, который не был покрыт исходными 16 тестами.

В reference native capabilities уточнено: отказ повторному запросу не выполняет cleanup активной операции. Исправлен изолированный пример, добавлена регрессия, повтор родительского probe дал pending → accepted: после исправления (`output/quality-extension/native-duplicate-after.json`, локальный артефакт). Итог — 17 тестов. Самостоятельная браузерная проверка агента также привела к уточнению Tab/Shift+Tab в компоненте dialog; родитель повторил keyboard regression. Это исправления тестового примера, не production приложения пользователя.

Агент исправил промежуточный контраст кнопок при переключении темы и незакрытый dialog при повторном локальном подтверждении. Reference design system теперь явно требует проверять промежуточные состояния, если цвета анимируются. Последняя сборка повторно прошла тесты и родительскую матрицу, включая повторное подтверждение. Полный журнал исправлений: frontend-agent-results.txt (`output/quality-extension/frontend-agent-results.txt`, локальный артефакт).

## Серверные инварианты

Двенадцать одновременных HTTP клиентов с одним ключом получили один durable объект. Проверены другой payload с тем же ключом, чужой объект, срок ключа, rollback, утрата клиентом ответа и backend restart. Fresh/upgrade миграции проверены на реальной временной SQLite.

Два worker процесса согласованно получают job. Отписка/отмена/перенос после enqueue или claim меняют отправку; crash до dispatch допускает reclaim, после начала попытки — unknown. Проверены 429/shared throttle, ограниченные повторы и срок полезности. Отмена после начала внешнего запроса не обещает отозвать сообщение. Fake transport не обращается к Telegram; sender не обещает exactly-once при неизвестном ответе.

Проверены связанные HTTP/booking/worker события, изоляция async context и отказ sink. Canaries искусственные; конечный output проверен после сериализации. Эти проверки относятся к созданному allowlist logger и не гарантируют redaction всех сторонних SDK в будущем продукте.

## Измерение загрузки

На финальной production сборке выполнено по пять холодных запусков в Windows Chromium при размере 390×844. Browser cache отключен; данные одинаковые, URL локальный. Готовность доступной формы измерена custom mark после двух animation frames.

| Лабораторный профиль | Готовность формы: медиана, диапазон | Наблюдаемый LCP: медиана |
| --- | --- | --- |
| CPU×1, localhost без network throttling | 49,3 ms; 32,7–55,9 ms | 56 ms |
| CPU×4, latency 150 ms, down 1,6 Mbps / up 0,75 Mbps | 511,1 ms; 507,3–538,2 ms | 480 ms |

В наблюдаемом периоде CLS и long tasks равны нулю. Фактические encoded HTTP bodies трех ресурсов — 9800 bytes; JS/CSS получены с gzip. Сырые данные и наличие observers: frontend-performance.json (`output/quality-extension/frontend-performance.json`, локальный артефакт). Build hashes: frontend-build-artifacts.json (`output/quality-extension/frontend-build-artifacts.json`, локальный артефакт).

Custom mark не является LCP или INP. INP и backend latency не измерялись. Эти два профиля не являются сравнением до/после; исходного продукта и утверждения об ускорении нет. CPU throttling не доказывает производительность реального Android.

## Визуальные материалы и воспроизведение

Просмотрены телефон, русский (`output/playwright/extension-ru-light-390.png`, локальный артефакт) и широкий экран, английская темная тема (`output/playwright/extension-en-dark-1280.png`, локальный артефакт). Галерея использует те же компоненты, что форма; длинные подписи переносятся, семантика полей/выбора сохраняется. Контраст проверен выборочно по вычисляемым цветам, а не полным аудитом WCAG.

Артефакты находятся в игнорируемых Git каталогах output/quality-extension и output/playwright этой рабочей копии. backend-probe.zip (`output/quality-extension/backend-probe.zip`, локальный артефакт) и frontend-probe.zip (`output/quality-extension/frontend-probe.zip`, локальный артефакт) содержат код, тесты и инструкции; это локальные тестовые стенды. Целостность архивов проверена: archive-integrity.json (`output/quality-extension/archive-integrity.json`, локальный артефакт). Браузерные JS рядом с JSON воспроизводят проверки; при другом каталоге скорректируйте пути скриншотов.

Для backend после распаковки: `python -X utf8 test_probe.py`; подробные команды в README архива. Контракт principal явно тестовый, server слушает loopback и требует test-fixtures для fixture login. В production этот adapter использовать нельзя.

Для frontend после распаковки в новый каталог: `npm.cmd install`, `npm.cmd test`, `npm.cmd run typecheck`, `npm.cmd run build`, `npm.cmd run preview`. Архив не содержит node_modules; текущий тестовый runtime не нужен. Playwright команды приведены в README архива. frontend-device-qa.txt (`output/quality-extension/frontend-device-qa.txt`, локальный артефакт) содержит состояния проверок и сценарий для будущих реальных клиентов.

## Границы проверки

Физические Android/iOS/планшеты и Telegram Desktop/Web здесь не проверялись. Browser resize, keyboard events и fake LocationManager не подтверждают реальную экранную клавиатуру, native permissions, биометрию, sharing или storage. Device QA должен сохранять эти случаи как не выполненные до доступа к соответствующей среде.

SQLite/stdlib HTTP prototype не подтверждает транзакции PostgreSQL, framework middleware или Telegram auth. Реальные аккаунты, сообщения, платежи и внешние telemetry сервисы не использовались. Выборочные примеры проверяют полезность инструкций, но не все возможности каждого навыка и не готовность конкретного продукта к релизу.

Логи и снимки с путями `output/…` — локальные артефакты исторических проверок. Они не входят в Git и не доступны в свежем клоне. Для текущей принятой версии смотрите [сохраненную приемку 031](v1-checks/031.json); для нового прогона выполните `python scripts/verify_pattern_packages.py`.
