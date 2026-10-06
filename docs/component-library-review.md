# Проверка библиотеки 0.1.0

3 октября 2026 года. Реализованы два импортируемых пакета с десятью группами компонентов и навык `telegram-code-patterns`. Текущий каталог содержит 41 навык. Это отдельная проверка новой библиотеки; исторический аудит прежних 40 навыков остается самостоятельным отчетом.

## Что выполнено

| Область | Результат | Доказательство |
| --- | --- | --- |
| Python core/aiogram | 17 unittest cases: published HMAC fixture/SDK, tamper/freshness/duplicates, SQLite concurrency/rollback/process restart, реальные Dispatcher synthetic updates, keyboard/ACK/Stars | [Тесты пакета](../packages/python/tests/test_components.py) |
| TypeScript | 10 Node tests: реальные HTTP/timeout/cancel/redirect, decoder, неизвестная запись, scopes/TTL/storage, bridge lifecycle | [Тесты пакета](../packages/typescript/tests/core.test.mjs) |
| Сборка Mini App | Strict tsc для библиотеки и импортирующего примера, exit 0 | [Workspace команды](../package.json) |
| Browser UI | 136 проверок, 14 viewport/theme cases на Chrome 154.0.8037.97; 14 screenshots | JSON (`output/pattern-library/browser/report.json`, локальный артефакт), [код проверки](../tests/patterns-browser.mjs) |
| Core distribution | Wheel установлен в новый venv без aiogram, auth/SQLite импортированы; второй отдельный процесс вернул replay | Consumer код (`output/pattern-library/core_consumer.py`, локальный артефакт), поставка (`output/pattern-library/final-distribution.json`, локальный артефакт) |
| Final SDK distribution | Финальный wheel установлен в новый Python 3.13.12 venv с aiogram 3.31.0; все 17 пакетных тестов прошли | Поставка/пути (`output/pattern-library/final-distribution.json`, локальный артефакт) |
| Final npm distribution | Финальный tarball установлен в новый consumer: strict tsc, публичные runtime imports, CSS и declarations на месте | Поставка/хеши (`output/pattern-library/final-distribution.json`, локальный артефакт), лог (`output/pattern-library/final-consumer.log`, локальный артефакт) |
| Независимый Python consumer | 17/17: текущий Dispatcher и /ping сохранены; SQLite effect/replay/ACL, callback/DM failures, auth и concurrent requests | Отчет (`output/pattern-library/python-consumer-report.md`, локальный артефакт) |
| Независимый TS consumer | 6/6 Node tests, strict build/typecheck и Chrome сценарии на 320/360/1280 px; unknown/reload recovery и storage error | Отчет (`output/pattern-library/ts-consumer-report.md`, локальный артефакт) |
| Примеры | Booking реально выполнен дважды в временном SQLite: один booking ID/row; файл затем переименован на Windows. Bot без BOT_TOKEN завершился до сетевого запуска | Результаты (`output/pattern-library/final-distribution.json`, локальный артефакт) |
| Навык/набор | 41 skill validation, официальный quick_validate для нового навыка, standalone CLI copy с совпадением трех файлов, 16 root helper tests | Копирование (`output/pattern-library/skill-install.json`, локальный артефакт) |

Среда: Windows; Python 3.12.13 (core/editable) и 3.13.12 (final wheel/independent), aiogram 3.31.0, Node 24.19.0, npm 12.0.2, TypeScript 7.0.2, Playwright 1.63.0. Core не импортирует SDK; TypeScript не имеет runtime dependencies. Dev dependency Playwright не попадает в npm tarball библиотеки.

Сохранен архив независимых consumer-проектов (`output/pattern-library/independent-consumers.zip`, локальный артефакт): исходный код, результаты, логи и lockfiles без node_modules/venv. Независимые отчеты сохраняют snapshot, на котором выполнена проверка; финальные артефакты дополнительно испытаны родительским consumer. Их SHA256 и размеры находятся в final-distribution.json.

## Наблюдения и исправления

В Chrome при потере ответа после POST browser transport повторно отправлял тот же запрос: независимый consumer измерил 1 JavaScript fetch, 2 HTTP POST и 1 effect. В родительском сценарии постоянного обрыва наблюдалось 5 HTTP arrivals и 1 effect. Уточнены API comment, README, каталог и skill reference: одна библиотечная попытка fetch не является гарантией одной доставки. Stable operation ID и серверная дедупликация остаются обязательствами приложения. Demo server сохраняет один effect для одинаковой операции, GET восстанавливает результат без нового прикладного POST.

Независимый Python consumer при переносе первоначальной формы `with sqlite3.connect(...)` получил Windows file-handle cleanup error. Сам SQLiteOnce закрывает connections; пример app schema исправлен через closing и отдельный transaction context. Исправление проверено реальной операцией и переименованием SQLite-файла.

Boundary test кнопки исправлен: prefix + key ровно 64 bytes допустим, 65 — отклоняется. Router validation согласована с допустимым префиксом keyboard. Финальный wheel прошел эту проверку. API-клиент дополнительно запрещает HTTP redirects до пересылки configured headers; реальный second-origin HTTP fixture не получил запрос.

При просмотре формы устранена старая ошибка поля после редактирования валидного телефона; storage failure теперь явно сообщается в demo. Browser matrix проверяет labels/error focus, отсутствие горизонтального overflow/перекрытия hint, кнопки не меньше 48px, сохранение ввода при theme/resize, reload выбора без контактов и unknown outcome.

В ходе разработки uv использовал закэшированный локальный wheel после изменения исходного модуля. Для итерационных тестов документирован editable install; финальное подтверждение выполнено через построенный wheel в свежем venv. Структурная проверка сама по себе не используется как доказательство поведения компонентов.

## Граница результата

Это local/runtime/consumer evidence, не live Telegram. Не запускались реальные callbacks/доставка сообщений, платежи, OIDC/Ed25519, native permissions, физические телефоны/планшеты/ПК с Telegram, soft keyboard и screen reader. Реальная геометрия/insets/theme contrast целевых клиентов требует device QA. React/Vue hooks здесь не реализованы и отдельно не проверены: текущий UI adapter — DOM, без основания менять выбранный framework.

SQLiteOnce покрывает только effect в переданном SQLite connection, не сеть/платежи/PostgreSQL. Auth/ACK/invoice builders не предоставляют ACL, платежную выдачу или reconciliation сервиса. SelectionDraftStore хранит только IDs выбора; durable recovery неизвестной операции организуется отдельно. Пример Mini App использует loopback mock backend и память, не production authentication/booking/payment. Исполняемых Crypto Pay/Platega/ЮKassa adapters в первом выпуске нет.

Пакеты построены для локальной поставки; публикация в PyPI/npm не выполнялась. [Инструкция использования и воспроизведения](component-library.md).

Логи и снимки с путями `output/…` — локальные артефакты исторических проверок. Они не входят в Git и не доступны в свежем клоне. Для текущей принятой версии смотрите [сохраненную приемку 031](v1-checks/031.json); для нового прогона выполните `python scripts/verify_pattern_packages.py`.
