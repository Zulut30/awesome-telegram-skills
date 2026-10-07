# Изменения библиотеки компонентов

## Не выпущено

- План из 100 пунктов, пункт 1: шаблон стартера `resources/starter/.env.example.txt` снова входит в git и wheel. Правило `.env.*` в `.gitignore` скрывало его, поэтому `telegram-patterns init` падал с `FileNotFoundError` на любом свежем клоне.
- Пункт 2: видимые пользователю тексты `callback_router` и `dialog_form_router` снова читаются по-русски. 15 строк (подсказки шагов, кнопки, отмена, многоточие) были записаны в UTF-8, ошибочно прочитанном как CP1251. Тест сверяет тексты диалога с эталоном, а проверка репозитория ищет такие последовательности во всех текстовых файлах.
- Пункт 3: `download_media` больше не выпускает наружу ошибки потока с URL `.../file/bot<TOKEN>/...`. HTTP и транспортные ошибки становятся `TransportFailure` («Telegram file endpoint returned HTTP 404»), таймауты — `TimeoutError` с нейтральным текстом. Новое исключение поднимается вне обработчика, поэтому traceback в логе не содержит исходную ошибку aiohttp.
- Пункт 4: `ApiClient` разрешает путь внутри пути `baseUrl`. Раньше при `https://x/api/v1` запрос `/orders` уходил на `https://x/orders`, а `orders` — на `https://x/api/orders`. Теперь оба варианта дают `https://x/api/v1/orders`; выход за префикс и `//host` отклоняются до запроса. Для `baseUrl` без пути (например, `location.origin`) поведение не изменилось.
- Пункт 5: `ApiClient` точно классифицирует HTTP-статусы: 409 → `operation-conflict`, 408 → `timeout`, 429 → новый `rate-limited` с `retryAfterMs` из `Retry-After`, 5xx → новый `server-error`, прочие 4xx → `invalid-api-request`. Модель ошибок Python и TypeScript получила коды `rate-limited`/`server-error`, категории `rate-limit`/`server` и действие `retry-later`; их совпадение проверяет новый тест паритета. Ошибка записи по-прежнему `unknown` + `reconcile`, пока статус не объявлен в новом `rejectedBeforeEffect` клиента или запроса — тогда `rejected` и действие по таблице в README. Изменились типы `ApiError` (outcome `rejected`, поле `retryAfterMs`), `ClientOptions` и `RequestOptions` (`rejectedBeforeEffect`), а также `ErrorCode`, `ErrorCategory` и `RecoveryAction` в Python и TypeScript.
- Пункт 6: `ApiClient` отклоняет `timeoutMs` больше 2147483647 мс (раньше такой таймаут срабатывал через 1 мс), а ошибки до отправки становятся типизированными: исключение в `headers()` — `PatternError` `internal`/`rejected` без исходного текста, несериализуемое тело (BigInt, цикл, функция, Symbol) — `ValidationFailure`, в том числе случай, когда `JSON.stringify` возвращал `undefined` при уже выставленном `Content-Type`.
- Пункт 7: `split_formatted` возвращает только отправляемые части. Одинаковые стили после обрезки вложенных диапазонов схлопываются (раньше — «Duplicate entity» на корректном вводе), разрыв делается после перевода строки, затем после пробела, а часть из одних пробелов присоединяется к соседней. Если пробельная серия длиннее лимита, выбрасывается `ValueError` вместо неотправляемой части. Границы частей для текста с пробелами изменились; склейка частей по-прежнему равна исходнику.
- Пункт 8: `SQLiteOnce.run` и `SQLiteSlotStore` принимают payload только из JSON-значений со строковыми ключами. Раньше `{1: "a"}` и `{"1": "a"}`, tuple и list давали один hash, и второй вызов ошибочно считался повтором, а смешанные типы ключей падали с `TypeError`. Теперь такие payload — `ValidationFailure` до открытия БД; `timeout` должен быть конечным (раньше `nan` принимался).
- Пункт 9: `VerifiedLaunch` возвращает подписанные поля запуска `query_id`, `chat_type`, `chat_instance`, `start_param`, `can_send_after`, `chat`, `receiver` (новые поля имеют значения по умолчанию, прежний конструктор работает). `user`, `chat` и `receiver` теперь глубоко read-only: вложенные объекты — mapping, массивы — tuple; JSON-копию дает новый `.as_dict()`. NaN/Infinity в JSON и неверный `can_send_after` отклоняются как `InvalidInitData`.
- Пункт 10: ошибки CLI по умолчанию печатаются понятным русским текстом («Ошибка / Что сделать») с безопасной кодировкой для перенаправленной консоли. Прежний машинный формат — один ASCII JSON объект в stderr — включается флагом `--json` и получил поле `problem` (`input`, `artifact`, `target-exists`, `installation`, `filesystem`). Отсутствующий встроенный ресурс теперь `installation` с исходом `read-failed`, а не «внутренняя ошибка, результат неизвестен». Скрипты проверки поставки переведены на `--json`.
- Пункт 11: проект распространяется по лицензии MIT. `LICENSE` в корне и в обоих пакетах, `license = "MIT"` с `license-files` в pyproject (PEP 639, сборка требует setuptools ≥77), `"license": "MIT"` в package.json пакета и примеров, `license: MIT` во frontmatter всех 41 скилла. Контракт поставки проверяет файл лицензии и метаданные в wheel и tarball.
- Пункт 12: `SECURITY.md` с поддерживаемыми версиями, приватным каналом GitHub Private Vulnerability Reporting, областью, сроками ответа и правилами добросовестного исследования; шаблоны issues ведут уязвимости в приватный канал.
- Пункт 13: версии 0.5.0–0.24.0 и коммиты, которые их ввели, перечислены в `.github/release-tags.json`; ручной запуск workflow Release создает из этого списка аннотированные теги `vX.Y.Z`. `scripts/build_release.py` воспроизводимо собирает wheel, npm tarball и `SHA256SUMS` из дерева тега (`git archive`, `SOURCE_DATE_EPOCH`), а workflow Release публикует их в GitHub Release при пуше тега и по ручному запуску. Две независимые сборки каждой из 23 версий дали одинаковые SHA256. Порядок — в `docs/releasing.md`.
- Пункт 14: workflow Publish загружает файлы GitHub Release в PyPI и npm через trusted publishing (OIDC, provenance npm) после сверки `SHA256SUMS`; он выключен, пока владелец не настроит publishers и переменную `PUBLISH_TO_REGISTRIES`. README объясняет установку из GitHub Release на всех ОС.
- Пункт 15: `scripts/check_registry_names.py` проверяет без изменений, свободны ли имена пакетов в PyPI и npm, и показывает опубликованных мейнтейнеров занятого имени. На 7 октября 2026 оба имени свободны, scope `@awesome-telegram` не создан.
- Пункт 16: `CODE_OF_CONDUCT.md` на основе Contributor Covenant 2.1 с правилами модерации issues и обсуждений (секреты в сообщениях, публичные уязвимости, спам, личные споры) и шкалой последствий.
- Пункт 17: `scripts/check_api_compatibility.py` и job CI сравнивают публичные символы Python и TypeScript с предыдущим тегом или базовой веткой: удаленный или измененный символ без упоминания в верхнем разделе CHANGELOG валит проверку. Первый прогон относительно `main` нашел 11 измененных символов, из них 9 не были названы в CHANGELOG; запись пункта 5 дополнена.
- Пункт 18: каждый релиз содержит детерминированный CycloneDX 1.6 SBOM (`awesome-telegram-patterns-X.Y.Z.cdx.json`: оба артефакта с SHA-256, лицензия тега, необязательные зависимости extras), он входит в `SHA256SUMS`; workflow Release создает attestation происхождения для wheel, tarball и SBOM через `actions/attest`. Проверка: `gh attestation verify`.
- Пункт 19: `docs/versioning.md` содержит политику поддержки: версии библиотеки, Python 3.11–3.15, Node.js 20–26, aiogram и Bot API со сроками, сверенными с Python Developer's Guide и расписанием Node.js. Node.js 20 остается минимальным в `engines`, но upstream не поддерживает его с 30.04.2026.
- Пункт 20: в начале README таблица «Можно ли брать в production» простыми словами: что можно использовать, что экспериментально и что не проверено вживую, с числами из каталога.
- Пункт 21: README и `docs/quickstart.md` дают каждую команду для PowerShell (Windows) и bash (Linux, macOS); bash-блок — одна цепочка, которая при ошибке останавливается с подсказкой. На сайте соседние блоки PowerShell и bash показываются вкладками с запоминанием выбора. `verify_quickstart.py` выполняет PowerShell-блоки на Windows и bash-блоки на Linux и macOS, а job CI `quickstart` запускает его на ubuntu, macos и windows.
- Пункт 22: скрипты проверки больше не рассчитаны только на Windows. Общий `scripts/_environment.py` передает дочерним процессам системные переменные Windows и POSIX (`HOME`, `TMPDIR`, локаль), прокси и CA-сертификаты, но не секреты; `check_api_reference_browser.mjs` по умолчанию ищет установленный Chrome на любой ОС. CONTRIBUTING и AGENTS.md дают команды полной проверки для bash.
- Пункт 23: английский вход — `README.en.md` (статус, быстрый старт, установка из релиза, описания всех 41 скилла), `docs/en/quickstart.md` с английскими сообщениями в командах и `docs/en/for-agents.md`. Инструкции скиллов остаются на русском. `verify_quickstart.py --guide` проверяет любое руководство, а CI запускает оба на ubuntu, macos и windows; страницы `docs/en` на сайте получают `lang="en"`.
- Пункт 24: четыре стартовые страницы по ролям (`docs/start.md`): первый бот, уже есть бот на aiogram, Mini App, работа с ИИ-агентом — каждая на один экран с командами для обеих оболочек. Фрагмент для существующего бота выполняется тестом пакета и печатает документированный результат, TypeScript-фрагмент для Mini App компилируется против пакета.
- Пункт 25: `BotSettings.from_env(env_file=...)` читает `.env` (окружение важнее файла, плейсхолдер `REPLACE_WITH…` и неверные строки дают понятную ошибку без значения), а `run_bot(verify_token=True)` перед меню и polling вызывает getMe: отклоненный токен — `AuthenticationRequired`, недоступный API — `TransportFailure`, без токена в тексте. Стартер `init` читает `.env` рядом с `app.py` и печатает подсказку; `.env.example` и руководства описывают запуск за минуту.
- Пункт 76 (выполнен раньше пункта 26, которому он нужен): примеры service-bot, group-bot и shop переведены с библиотеки 0.13 на текущую (`>=0.24,<0.25`, frontend `0.24.0`) без изменений кода; скрипты проверки берут версию библиотеки из `pyproject.toml`, документация примеров дает команды для bash и сборку wheel через `build_release.py`, а job CI `examples` проверяет все три примера на текущей версии.
- Пункт 26: необязательный Docker для service-bot: `Dockerfile` (python 3.13-slim, пользователь без root, база на томе `/data`, зеркало через `PYTHON_IMAGE`, CA прокси секретом сборки), `compose.yaml` (токен из `.env`, именованный том, `restart: unless-stopped`) и `.dockerignore`, который не пускает `.env` в образ. Entrypoint примера печатает ошибки настройки и getMe одной строкой с кодом 2 вместо traceback. `scripts/verify_docker_example.py` и job CI `docker` собирают образ и проходят офлайн-фазы в разных контейнерах на одном томе; без Docker пример работает как раньше.
- Пункт 27: `doctor --webhook` (и `doctor(..., webhook=True)`) делает один read-only `getWebhookInfo` и превращает ответ в проверки с рекомендациями: отклоненный токен, недоступный Bot API, webhook мешает polling (409 Conflict, `--expect polling` делает это fail), webhook не установлен при `--expect webhook`, очередь updates, последняя ошибка доставки по типам (соединение, TLS, 401/403, 404, 5xx), ошибка синхронизации и отсутствие локального секрета для `secret_token`, который Bot API не показывает. Путь webhook URL и token в отчет не попадают; команды исправления читают BOT_TOKEN из окружения. С `--webhook` doctor берет BOT_TOKEN и секрет из окружения или `.env` проекта; без флага поведение прежнее. Новые параметры `doctor`: `webhook`, `expect`, `webhook_secret_env`; новые причины `token-placeholder` (раньше заглушка давала `token-format-invalid`) и `env-file-invalid`.
- Пункт 28: тестовое окружение Telegram. `BotSettings` получил поле `test_environment` (по умолчанию `False`), `BotSettings.from_env` читает его из `TELEGRAM_TEST_ENVIRONMENT` (`1/true/yes/on` или `0/false/no/off`, параметр `test_environment_var`). Новая функция `create_bot(settings, session=None)` и `run_bot` в тестовом окружении создают `AiohttpSession(api=TEST)` — запросы идут на `https://api.telegram.org/bot<token>/test/METHOD_NAME`; переданная session основного окружения отклоняется, отклоненный токен объясняется отдельным сообщением. `StubSession(api=...)` позволяет повторить это offline, `doctor --webhook` проверяет `getWebhookInfo` в выбранном окружении. Стартер, service-bot, group-bot и shop читают флаг; `docs/test-environment.md` описывает вход, тестового бота, запуск примеров, Mini App по HTTP и Stars.
- Пункт 29: страница `docs/troubleshooting.md` (и копия в скилле telegram-debugging): 37 ситуаций по схеме симптом → причина → проверка → решение — токен и окружение, polling и webhook (409 Conflict, ошибки доставки, secret_token, потеря и повтор updates, `allowed_updates`), группы и каналы (privacy mode, права, миграция в супергруппу), отправка (блокировка, 429, `message is not modified`, entities, длина), кнопки и callback, файлы, Mini App (пустой экран, SDK, initData) и Stars. Проверки только читают состояние: скрипт `tg.py` выполняет методы `get*` из закрытого списка без `getUpdates`, а 12 фрагментов кода исполняются тестом и печатают документированный вывод.
- Пункт 30: README, README.en.md и gallery/README.md ведут в опубликованную галерею рецептов (https://zulut30.github.io/awesome-telegram-skills/recipes/); локальный `gallery/index.html` остается для работы без интернета. Браузерный тест галереи добавил вьюпорт 360×740 (светлая и темная темы): поиск, фильтры, превью клавиатуры и кнопка «Копировать» помещаются по ширине, а код действительно попадает в буфер обмена.

## 0.24.0

- Пункт 31: atomic FSM snapshot contract и адаптер текущего project storage; state/data, версия, шаг и абсолютный срок формы согласованно сохраняются в одной CAS записи.
- Text/mixed формы сохраняют старый API; optional DialogLifetime требует atomic storage, resume не продлевает срок, unknown/pending operation не удаляется по draft TTL. Foreign host data, full StorageKey, Dispatcher и isolation сохраняются.
- Project-owned SQLite adapter, три отдельных процесса restart/reconcile, самостоятельные copied guide/API/offline recipe. MemoryStorage остается демонстрацией без долговечности; live и distributed effect acceptance отдельно.

## 0.23.0

- Пункт 30: experimental `platform-operations`, 18 public symbols и 51 reviewed native method — темы, реакции, заявки, Business, stories, gifts, managed bots. Current actor/resource/revision и native rights проверяются отдельно.
- Host authorize/atomic sending claim/receipt, SQLite actor/budget/intent example, scoped observers и user-confirmed managed flow. Unknown outcomes не повторяются; финансовые операции требуют согласия/quote, local budget не гарантирует atomic remote debit.
- Validated photo/video story upload bridge к обычному SDK multipart, secret-token sink и сохранение текущего Dispatcher/стека. Catalog, standalone API/reference/copied guides и installed fixtures синхронизированы; live/device/provider/human acceptance остается отдельной.

## 0.22.0

- Добавлен inline-поиск с явно shareable articles, текущими host правами, scoped pagination и раздельными public/personal cache policies; native answer не повторяется вслепую.
- Добавлены современные poll/quiz requests, persistent option IDs и scoped наблюдения собственных опросов с сохранением unknown fields и ограничений анонимности.
- Публичные API-примеры, самостоятельные guides, закрытые offline Dispatcher recipes и пример host SQLite intent/receipt. Experimental локальная поставка; live Telegram/device/provider и независимая приемка остаются отдельными.

## 0.21.0

- Добавлены immutable наблюдения пользователя, чата и фотографий профиля: неизвестные optional значения остаются None, источник и время сохраняются.
- Добавлены свежие локализованные чтения собственного бота и изменения с текущими host правами для каждого метода: omission/clear, новые JPG/MPEG4 аватары, удаление и сверка частичного неизвестного результата.
- Публичные типы, установленный API-пример, закрытая Dispatcher-композиция, самодостаточные guides и поиск галереи. Локальная experimental поставка; live privacy/codec/permissions и независимое использование принимаются отдельно.

## 0.20.0

- Добавлены optional aiogram media компоненты: typed byte uploads/same-bot file_id, literal captions/entities, compatible albums, guarded normal/inline replacement и bounded hosted download.
- Скачивание ограничивает actual bytes и общий deadline, закрывает stream при error/cancel и не читает Local API paths. Host остается владельцем session, content/codec validation, ACL и delivery/retry policy.
- Добавлены полный Dispatcher рецепт, closed offline fixture, девять публичных exports, API consumer и переносимый media guide; SDK/mock/browser evidence отделено от live.

## 0.19.0 — пункт 026

- SDK-free MessageBuilder/FormattedText/TextEntity, TypedDict payload и explicit parse_mode=None; UTF-16 scalars, nested spans и bounded metadata. Пользовательские вставки остаются literal.
- HTML и MarkdownV2 escaping по text/code/link context; lossless split сохраняет style/code coverage и metadata, atomic links/quotes/custom emoji, common combining/emoji sequences. Oversized atomic block возвращает error до отправки; full UAX29 не заявлена.
- Custom emoji по умолчанию regular fallback; host проверяет metadata/entitlement/context. Public/API consumer, copied full recipe и actual Dispatcher/SDK serialization; partial unknown delivery не повторяется автоматически.

## 0.18.0 — пункт 025

- NumberField/EmailField/PhoneField/DateField/FileField/ContactField/LocationField: ограниченный и нормализованный ввод, точные decimal-строки, реальные даты и flat metadata без download/DNS/проверки физического присутствия.
- FieldValue/DialogSubmission/dialog_form_router: immutable structured submission, current bot/actor/chat/FSM/schema/step guards, ForceReply correlation для текста/документа, отдельное подтверждение native candidate, возврат/отмена/возобновление и очистка reply keyboard.
- Unknown submission сохраняет operation_id и блокирует редактирование до явной сверки; success очищает форму перед feedback. Старые TextField/FormSubmission/text_form_router не требуют миграции. Host владеет durable FSM/isolation/ACL/эффектом/retention.
- Семь полей в готовом примере на текущем Dispatcher, one-effect SQLite receipt/replay, переносимый guide, закрытый offline recipe, полное API/каталог/галерея. Проверки SDK/mock/Chrome не заявляют live/device/independent usability либо production-ready.

## 0.17.0 — пункт 024

- SDK-free CalendarMonth/TimeSlot/resolve_local_time: immutable Monday-first calendar, unavailable dates, UTC intervals и явный fold для DST ambiguity. Gap/imaginary wall time отвергается; optional calendar extra предоставляет IANA data на Windows.
- SlotSchedule/SlotBooking/SQLiteSlotStore: current project ACL внутри file SQLite transaction до effect/replay, schedule CAS, interval/key availability и atomic booking + immutable receipt. Overlapping aliases, повтор и конкуренция shared-file процессов не создают двойную запись. Текущий booking status отличается от исходного receipt; owner cancel освобождает слот.
- calendar_keyboard/time_slot_keyboard и optional selection_router renderer: weekday fallback, host-verified native disabled grid, local offset labels и готовый one-message date/time/back/confirmation workflow. Explicit recovery сверяет intent, /book new начинает новый выбор; UI/session ephemeral, booking/receipt durable.
- API/examples/catalog/portable guide и pinned consumers проверяют composition, timezone, negative cases и real-process race. Live clients/devices, external storage и exactly-once Telegram delivery не заявлены.
- Справочник API отдельно сверяет исходные байты и исполняемый fenced-код с LF; CRLF и завершающие пустые строки покрыты регрессионной проверкой в временном дереве.

## 0.16.0 — пункт 023

- SelectionOption/Spec/Context/State/Result и SelectionMenu: server-owned toggle, multiselect, quantity и filters, immutable snapshots и атомарные проверки owner/bot/chat/thread/message/token/revision/TTL без SDK. Fresh server spec отзывает старые кнопки и confirmation.
- selection_keyboard/selection_router: композиция с текущим Dispatcher, capability fallback, ACK перед hooks/lock/edit и повторная проверка после async load. Опасное действие подтверждается отдельным короткоживущим ID; consumed local intent возвращает operation_id/resource_version для бизнес-транзакции host, без автоматического эффекта или retry.
- Готовый пример и закрытый offline recipe показывают все элементы выбора в одном сообщении. State остается в памяти одного процесса; durable storage, multiworker и live Telegram требуют отдельных проверок.

## 0.15.0 — пункт 022

- MessageNavigation, NavigationScreen/State/Result и navigation_router: экраны, history/back и refresh в одном owner/bot/chat/thread/message-bound сообщении. ACK до lock/edit, revision/graph/TTL guards и сериализация одного меню; stale/foreign action не меняет состояние.
- Unknown edit останавливает переходы; explicit owner /menu перерисовывает тот же message_id с новой revision. Unknown initial send не повторяется автоматически; local discard — отдельное решение host. State одного процесса, restart отклоняет старые tokens; durable FSM/multiworker не обещаются.
- Runnable composition, closed offline recipe и API reference через публичные exports; обычная локальная поставка Python/TypeScript, без публикации.

## 0.14.0 — пункт 021

- KeyboardLayout и KeyboardCapabilities, action_layout/inline_layout/reply_layout: flat buttons, mixed widths, last/cycle tail, immutable snapshot и проверка native context/actions до presentation fallback. Default новых helpers убирает непроверенные styles/emoji, сохраняя labels/actions; прежние builders не меняются. Entitlement/client hints передаёт host, live проверка не подменяется.
- Новые публичные exports, API reference/контракты, gallery layouts и installed SDK composition согласованы. Python/TypeScript поставка локальная; исторические applications используют принятые артефакты 0.13.0.

## Unreleased — подготовка 1.0

- Пункт 019: самостоятельное приложение `examples/group-bot` / `awesome-telegram-group-example` 0.1.0. Темы, свежие права bot/actor, context-bound confirmation, обычные/assigned заявки и десятиминутная модерация; file SQLite journal, миграции и membership invalidation. Повтор и crash после synthetic API-запроса не отправляют действие заново. Внешний consumer проверяет wheel/RECORD/entrypoint, типы, 19 тестов и четыре реальные процессные фазы. Live права/delivery не объявлены проверенными; публичный API библиотеки 0.13.0 не изменился.

- Пункт 018: отдельный `examples/shop` / application 0.1.0 связывает установленную библиотеку 0.13.0, TypeScript каталог/корзину и Python/aiohttp backend с реальной SQLite. Signed initData → hashed session/CSRF → owner ACL; цена/валюта/terms и order operation — серверные. Stars invoice, pre-checkout и атомарный receipt/paid/access подключены через публичные компоненты и trusted SDK Router. Invoice callback не выдаёт доступ. Pending ID переживает reload, unknown invoice не пересоздаётся; duplicate/second receipt сохраняются без двойной выдачи. Separate consumer tests и Chrome проверяют композицию; transport/native/launch остаются synthetic, live Stars/device acceptance отдельно. Пакеты библиотеки и их публичные exports не изменены.

- Пункт 017: отдельное приложение `examples/service-bot` / `awesome-telegram-service-example` 0.1.0 использует принятую библиотеку 0.13.0. Меню, запись через text_form_router, file SQLite FSM, owner-scoped доступ, transactional replay, согласие и durable намерение напоминания. Actual crash после commit сохраняет один эффект; crash после synthetic отправки оставляет unknown без автоматического дубля. OS process lock и join SQLite work при отмене предотвращают продолжение записи после освобождения базы. Внешний consumer устанавливает оба wheel, проверяет типы, восемь domain/lifecycle тестов и семь отдельных restart/crash фаз. Synthetic SDK transport не подтверждает live Telegram; общая библиотека и её public exports не изменились.

- Пункт 016, 0.13.0: у всех 299 cookbook recipes появились execution requirements. Публичные frozen RecipeRunPlan/RecipeRunResult, plan_recipe/run_recipe_offline и CLI run-recipe сначала показывают план, затем по --offline запускают закрытый fixture из установленного пакета. 200 Python сценариев выполняются без токена: 185 SDK requests, 11 markup builders, три Dispatcher-композиции и один SQLite lost-response. 99 native references дают явный отказ без host/аргументов.

  Изолированный child получает только системный env, owns temporary files и не выполняет recipe.code/user application. Real SDK HTTP и внешний Python DNS/connect запрещены; доверенный fixture worker не является OS sandbox. Сессия/FSM явно закрываются. Requirements panel отделяет offline readiness от live auth/ACL/entitlement; SDK can_* hints не объявляются полным permission engine. Предыдущие API/schema defaults сохранены; maturity/evidence не повышены. Каталог: 29 групп, справочник: 120 символов и 19 полных примеров. Поставка локальная.

- Пункт 015, 0.12.0: галерея и SDK-free RecipeCatalog/CLI ищут по задаче, контексту, SDK/снимку и версии API независимо от maturity/evidence. Источники и executable проверки связаны с каждой записью; standalone export копирует связанные файлы byte-exact. Добавлен существующий SQLite lost-response пример: 299 recipes, 15 experimental, 284 reference; 196 SDK / 4 mock / 99 not_run. Schema 1 и прежние defaults/imports сохраняются; unknown context не означает все чаты. На телефоне дополнительные фильтры и пояснения свернуты.

  При проверке новой поставки воспроизведен timeout первого изолированного SDK import в свежем Windows consumer: старый лимит 10s заменен на 30s. Ошибки и превышение лимита сохраняют fail; проверки timeout и отсутствия секретов проходят. Consumer harness сохраняет причины/время tool probes для расследования таких сбоев.

- Пункт 014, 0.11.1: поименный API-справочник, 116 публичных символов и CLI/CSS, 18 полных примеров core/bot/Mini App. Переносимые references автономны. Генератор обнаруживает незадокументированные exports; отдельный consumer проверяет точные блоки документации, installed types, CLI, ESM и DOM. Runtime API не изменен; patch нужен для новых package README bytes.

- Пункт 013 / поставка 0.11.0: doctor сообщает машинные причины и команды исправления без исполнения рекомендаций. Ожидаемые ошибки target/manifest становятся failed checks, JSON shape проверяется, чтение ограничено и известные links отклоняются. Node probe получает системный env allowlist и не отражает raw output. Рекомендованные wheel/tarball repairs проверяются отдельно в новом окружении.

- Пункт 012 / поставка 0.10.0: выбор из 15 starter групп, auto-dependencies, минимальная версия API и preflight конфликтов шаблона/артефактов/файлов/команд/prefix. Выбранные модули исполняются через установленную библиотеку; generated Python distribution включает подключенные модули. Dry-run перечисляет все файлы, повторный запуск сохраняет пользовательский код.

- Пункт 011 / поставка 0.9.2: короткий первый запуск из локальных wheel/tarball 0.9.2 с offline-ботом и адаптивной формой. Команды руководства проверяются в новом внешнем consumer с пробелами в путях; переносимая копия навыка совпадает с руководством. Исправлен npm file spec для путей с пробелами: прежний percent-encoded URI приводил к ENOENT; Python URI и config URI сохранены. Browser preview и установка dependencies отделены от реального Telegram и backend auth.

- Пункт 010: фиксированы identity/launch/rights границы Bot API, Mini App, Business/Secretary и user-client; добавлена переносимая инструкция и SDK/native probes. Учтены современные guest/bot-to-bot исключения и расхождения FAQ/rights naming; пользовательская session не подключается автоматически. Runtime API и артефакты 0.9.1 сохранены.

- Пункт 009 / поставка 0.9.1: обязательный read-only archive contract — source/resources/RECORD, extra/CLI и полный набор JS/declarations/CSS/export map. Проверки подмены/пропуска/лишних файлов и небезопасных archive entries выполняются в настоящих temporary archives; installed consumers остаются отдельным runtime evidence. API 0.9.0 сохранен.

- Пункт 008 / исходники 0.9.0: структурные OnceStore/AsyncTransport/ProviderAdapter и optional RefundProvider; публичные TS KeyValueStorage/StorageFactory/FetchTransport без изменения прежних методов. Рабочий custom adapter проверяет SQLite replay, lost response и tampered fixture event; реальные provider workflows остаются отдельными задачами.

- Пункт 007 / исходники 0.8.0: единые ErrorReport/code/category/outcome/recovery в Python/TypeScript; безопасные сообщения, совместимые исключения и различимые preflight/permission/unsupported/timeout. Неизвестный результат записи требует сверки того же ключа; HTTP/отмена/ошибка feedback не запускают retry. Добавлены installed-core пример и проверки сохранения pending identity формы.

- Пункт 001: определены сценарии и границы 1.0, пользовательские задачи, точки входа и критерии приемки; добавлен регистр выполнения всех 100 пунктов.
- Пункт 002 / исходники 0.6.0: maturity групп и recipes, независимый фильтр RecipeCatalog/CLI/галереи, совместимое чтение старых records и переносимые инструкции. SDK/mock/browser evidence не повышает статус до stable автоматически.
- Пункт 003: полные семантические контракты root/aiogram/testing/CLI и TypeScript exports, включая DTO/types, ошибки, ресурсы и обязанности host.
- Пункт 004: правила SemVer, миграций, неизменности релиза и deprecation stable API (два minor и 90 дней); RC identity различает Python/npm форматы.
- Пункт 005: опубликованы support matrix и JSON snapshot с точными проверенными версиями, пропуском Windows symlink и явно непроверенными OS/Telegram clients.
- Пункт 006 / исходники 0.7.0: явные Python/TypeScript exports, Literal aliases и TextFieldControl, устранены 19 ошибок Mypy в SDK guards/middleware; consumer type checks проверяют wheel/tarball, migration случайных wildcard SDK imports документирована.

## 0.5.0 — 4 октября 2026

Добавлены Recipe/RecipeCatalog и локальная галерея с поиском по 298 рецептам: 11 раскладок/ввода, 185 Bot API requests, 99 справочных Mini App фрагментов и три mock-сценария бота. Галерея показывает код, layout preview и точную область SDK/mock/reference проверки; live evidence не выдумывается.

CLI `telegram-patterns recipes/init/doctor` входит в wheel. `init` создает только новый каталог: минимальный aiogram-бот или бот с TypeScript frontend из согласованных локальных wheel/tarball. Поддерживаются dry-run, offline-сценарий и отказ от перезаписи. `doctor` не читает .env, не выводит token, не запускает проект и не обращается к Telegram. Mini App starter пока содержит локальную форму без backend auth.

Каталог содержит 24 группы; навык переиспользования, exports и шаблоны согласованы. Проверка поставки дополнена установленной CLI, созданными проектами, строгой TS-сборкой и Chrome проверками галереи/стартеров. TypeScript runtime API сохранен; версия пакета синхронизирована. [Контракт и проверка](docs/developer-tools-review.md).

## 0.4.0 — 4 октября 2026

Клавиатуры и библиотека рецептов: explicit inline/reply rows (по две/три и смешанные), styles/emoji fallback, request buttons, input prompt/remove, рабочий demo Router с ACK и owner-bound edit. Тот же Dispatcher проверяется offline. SDK method_catalog/build_request охватывает 185 Bot API методов; generated request-only recipes и индекс 400 типов отмечают границы SDK validation. UpdateObserver/event_router работают с native Update kinds без копирования raw данных.

TypeScript: каталог 99 native функций / 44 событий Mini App, TelegramNativeAPI с availability gates, native callback semantics и cleanup, popup/location recipes. Пакеты и переносимый code-patterns навык синхронизированы; release проверяется через wheel/tarball consumers. [Контракты и доказательства](docs/telegram-cookbook-review.md). Live Telegram/device/provider workflows не подменяются SDK/mock проверкой; поставка локальная.

## 0.3.0 — 3 октября 2026

Добавлены TextField/InvalidField, FormSubmission и text_form_router для текстовых форм в личных чатах aiogram. Поля описываются списком; Router проверяет ввод, сохраняет текущий FSM, поддерживает /back, /cancel и явное подтверждение сводки. SDK event isolation обязательна. Owner/operation/message checks отклоняют старые и чужие кнопки; ACK выполняется до сервиса.

Неизвестный результат отправки сохраняет operation_id и ответы; редактирование/отмена/рестарт блокируются до сверки той же операции. Авторизация, durable effect/replay, storage retention и восстановление после рестарта принадлежат приложению. Добавлены пример с настоящим SQLite effect и общий offline-сценарий, включая редактирование и повтор подтверждения. Windows SQLite соединения в примере закрываются явно.

Каталог содержит 17 групп. Публичные API 0.2.0 сохранены; API TypeScript без изменений, версия согласована. [Контракт и проверка](docs/form-tools-review.md). Поставка остается локальной.

## 0.2.0 — 3 октября 2026

Добавлены шесть групп Python-инструментов для повторяющихся задач бота: BotSettings, меню ActionButton/action_menu, paginated_menu/page_number, CommandReply/command_router/command_menu, run_bot и StubSession. Публичные импорты 0.1.1 сохранены; single-button builder перенесен внутрь keyboards.py и доступен через прежний telegram_patterns.aiogram.

Меню собирают строки с уникальными action keys и emoji fallback. Статические команды описываются один раз, Router сохраняет фильтрацию mention и plain text; установка command menu явная. Runner сохраняет Dispatcher/инъекции и закрывает Bot session при завершении/ошибке/cancellation. StubSession записывает реальные SDK методы, требует явные responses и не имеет сетевого fallback. Добавлен один Dispatcher-пример для live polling и offline command → page → selection проверки.

API TypeScript не менялся; версия пакета согласована с общей поставкой. [Контракты и проверка](docs/bot-tools-review.md). Registry publication не выполнялась.

## 0.1.1 — 3 октября 2026

Повторная проверка общего API с воспроизведением ошибок и проверкой собранных пакетов в новых проектах.

- SQLiteOnce блокирует преждевременные COMMIT/ROLLBACK и неявный commit от executescript до сохранения эффекта; savepoints разрешены. Некодируемый initData возвращает InvalidInitData.
- ApiClient принимает успешные HEAD/204/205 без JSON и отделяет обрыв чтения тела от некорректного JSON/decoder.
- Bridge удаляет неуспешную подписку, очищает частичную регистрацию SDK и допускает повторный start. Platform unknown корректно распознается для UI как запуск вне Telegram.
- SelectionDraftStore фиксирует scope/namespace/TTL при создании, защищая черновик от изменения переданного options-объекта.
- Shell использует семантические цвета Telegram и native color-scheme. ID поля/hint/error не конфликтуют с существующим DOM, включая fallback без window/randomUUID.
- Новый verify_pattern_packages.py собирает wheel/tarball, устанавливает их в свежие consumer-окружения, проверяет публичные imports/declarations/CSS и сохраняет логи, версии и SHA256. Browser matrix хранится отдельно для каждой версии.

[Отчет и границы проверки](docs/component-library-hardening.md). Поставка остается локальной, публикация в реестры не выполнялась.

## 0.1.0 — 3 октября 2026

Первый локальный выпуск двух импортируемых пакетов, десять групп компонентов. Python: Mini App HMAC, SQLite effect/replay, четыре aiogram adapters. TypeScript: bridge, HTTP, scoped selection draft, responsive shell/fields/CSS. Публичные типы, контрактные тесты, примеры и навык подключения. Публикация в package registries не выполнялась.

Версия относится к библиотеке компонентов; исторические отчеты навыков имеют собственную дату/область проверки.
