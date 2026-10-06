# Повторный аудит всех Telegram-навыков

Дата: 3 октября 2026 года, Europe/Warsaw. Проверены все 33 навыка. По качеству инструкций набор пригоден для разработки: области применения различаются, выбранный стек сохраняется, подробности доступны внутри переносимого каталога. Обнаружены и исправлены девять конкретных замечаний независимого аудита; дополнительно уточнены границы задач и несколько формулировок.

Это оценка написания и технического содержания навыков. Она не является обещанием, что все функции уже испытаны в Telegram или платежной среде.

## Объем и метод

Три независимых прохода охватили Mini Apps/локализацию, Python/backend/платежи и Bot API/профили/пользовательские клиенты. Аудиторы прочитали все SKILL.md, references и UI-метаданные своих каталогов, не читали предыдущие отчеты и не меняли канонические файлы. Родитель проверил находки, внес исправления и повторил исполняемые пробы.

Покрытие сверено по перечню файлов: 33 SKILL.md, 33 agents/openai.yaml, 29 Markdown references, один Python helper и один API index — всего 97 файлов без пропусков. Большой API index проверен по metadata/выборке и сравнением всей схемы с новым снимком; семантика каждого из 185 методов отдельно не испытывалась. Перечень покрытия (`output/quality-reaudit/read-coverage.json`, локальный артефакт).

Критерии: точность протокола, ясность действия, различимость description, соразмерность проверки, сохранение scope/стека, самостоятельность ссылок, полезность примеров и честность заявленного результата. Общую оценку не выводили из количества строк или числа passed тестов.

До исправлений аудиторы отметили 24 навыка без конкретных замечаний и девять требующих улучшения; P0/P1 не обнаружены. После исправлений подтвержденные замечания закрыты. Исходные оценки сохранены: frontend (`output/quality-reaudit/frontend-audit.json`, локальный артефакт), backend/payments (`output/quality-reaudit/backend-audit.json`, локальный артефакт), platform (`output/quality-reaudit/platform-audit.json`, локальный артефакт). Они относятся к прочитанной исходной версии; frontend hash inventory сформирован уже после части правок и явно помечен в JSON.

## Исправленные замечания

| ID | Приоритет | Проблема и исправление |
| --- | --- | --- |
| PLATFORM-01 | P2 | В справке профилей `can_change_*` заменены на фактические `BusinessBotRights.can_edit_*`. Учтено расхождение prose методов со схемой; поля подтверждены импортированными PTB и aiogram. [Схема](https://core.telegram.org/bots/api#businessbotrights). |
| BACK-01 | P2 | Уточнено 24-часовое окно идемпотентности ЮKassa и запрет слепого повтора неизвестной операции после него. [Формат API](https://yookassa.ru/developers/using-api/interaction-format#idempotence). |
| BACK-02 | P2 | Platega получила отдельную ветку СБП-подписки: subscription ID, ID списания, сверка и отмена будущего продления. Активация отделена от оплаты; повтор одного списания отделен от следующего периода. [Создание](https://docs.platega.io/создать-подписку-40029698e0), [callback списания](https://docs.platega.io/callback-по-списанию-40029713e0). |
| BACK-03 | P2 | Для уведомлений определена атомарная граница cancel/optout и `dispatching`. Подавление до начала попытки отделено от возможной текущей отправки; общей транзакции БД и Telegram не обещается. |
| BACK-04 | P2 | Надежный прием дополнен для polling: продвижение offset, фоновые handlers и ошибки SDK. Один потребитель и последовательная обработка не объявлены гарантией сохранения. [getUpdates](https://core.telegram.org/bots/api#getupdates), [dispatcher](https://docs.aiogram.dev/en/latest/_modules/aiogram/dispatcher/dispatcher.html). |
| BACK-05 | P2 | Диалоги явно подтверждают callback через `answerCallbackQuery`, включая отказ, повтор и старую кнопку. ACK отделен от результата операции. [CallbackQuery](https://core.telegram.org/bots/api#callbackquery). |
| BACK-06 | P2 | В цифровой оплате добавлены доступные условия и согласие до покупки. Сохранение версии условий оставлено модели продукта. [Live Checklist](https://core.telegram.org/bots/payments-stars#live-checklist). |
| FE-01 | P3 | У browser lifecycle появились точные источники pagehide/pageshow/BFcache вместо общей ссылки на Telegram bridge. Логика восстановления не менялась. |
| FE-02 | P3 | При локализации Python-бота без Mini App больше не требуются frontend typecheck/build и скриншоты. Проверки выбираются по затронутому компоненту. |

Backend-аудитор отдельно перечитал семь измененных файлов: BACK-01…06 закрыты, новых замечаний нет. Повторная проверка исправлений (`output/quality-reaudit/backend-post-fix-review.json`, локальный артефакт). Platform-аудитор подтвердил исправленные права в своем итоговом JSON. Две frontend правки проверены родительским перечитыванием.

Дополнительные правки родителя: архитектурный навык разделяет проектирование и реализацию; security review различает Telegram secret header и протокол платежного провайдера; в сценариях группы/история аккаунта отделены от Business private chats. Исправлены обращение «рассмотрите», неясная фраза о границе Telegram API и термин «многопоточность» для конкурентной обработки aiogram.

Изменены 14 файлов в 13 навыках; новые навыки и обязательные зависимости не добавлены. Точный diff (`output/quality-reaudit/skill-changes.diff`, локальный артефакт), hashes изменений (`output/quality-reaudit/changes.json`, локальный артефакт), исходный снимок (`output/quality-reaudit/skills-before.zip`, локальный артефакт).

## Качество написания

Входные файлы короткие и задают решение, существенные ограничения и проверяемый результат. Подробности размещены в references; aiogram/PTB/TeleBot являются альтернативами, большой API index предлагается искать по ключевому слову. После переноса отдельного каталога обязательной зависимости от соседних навыков нет.

Русский текст понятен для разработчика. API-идентификаторы и общепринятые термины сохранены на английском. Редакторские правки устранили несколько неточных фраз; массовая замена технических терминов не требовалась.

Повторы о серверных правах, неизвестном результате и секретах оправданы самостоятельностью навыков. Они не требуют React, Redis, Celery, отдельного monitoring сервиса или замены библиотеки. Близкие навыки различаются по результату: экран и библиотека компонентов; bridge и конкретная native capability; диагностика сбоя и внедрение telemetry; Telegram invoice и API выбранного провайдера.

Наиболее сильная часть Mini Apps — явные владельцы формы/навигации/геометрии, один источник серверного состояния, компактная и широкая компоновка, fallback действий, cleanup и восстановление. Безусловную реализацию при запросе только архитектурного плана убрали. Матрица размеров и контраст полезны для проверки, но не заменяют визуальную оценку и реальные клиенты.

## Оценка каждого навыка после правок

«Качественный» означает отсутствие оставшегося подтвержденного недостатка текста в этом аудите. Это не сертификация всех реализаций, которые агент может написать по навыку.

| Навык | Оценка и существенная особенность |
| --- | --- |
| [telegram-bot-api](../.agents/skills/telegram-bot-api/SKILL.md) | Качественный: поиск по API и сверка SDK, ограничения и ошибки доставки. |
| [telegram-bot-python](../.agents/skills/telegram-bot-python/SKILL.md) | Качественный, уточнен: альтернативные библиотеки, lifecycle и риск polling ACK. |
| [telegram-business-bots](../.agents/skills/telegram-business-bots/SKILL.md) | Качественный: connection/rights/revoke, ограниченные чаты, изоляция владельцев. |
| [telegram-buttons](../.agents/skills/telegram-buttons/SKILL.md) | Качественный: оформление, entitlement, payload SDK и действие кнопки. |
| [telegram-cryptopay](../.agents/skills/telegram-cryptopay/SKILL.md) | Качественный: raw-body HMAC, invoice dedup, режим валюты; давность источника обозначена. |
| [telegram-debugging](../.agents/skills/telegram-debugging/SKILL.md) | Качественный: локализация конкретного сбоя и проверка подтвержденной причины. |
| [telegram-deploy](../.agents/skills/telegram-deploy/SKILL.md) | Качественный, исправлен: надежный прием рассмотрен для webhook и polling. |
| [telegram-dialogs](../.agents/skills/telegram-dialogs/SKILL.md) | Качественный, исправлен: версии состояния, старые кнопки и явный callback ACK. |
| [telegram-groups](../.agents/skills/telegram-groups/SKILL.md) | Качественный: права бота/инициатора, темы, анонимность и миграция чата. |
| [telegram-inline-mode](../.agents/skills/telegram-inline-mode/SKILL.md) | Качественный: отдельный inline_query, cursor и персональный кеш. |
| [telegram-library-selection](../.agents/skills/telegram-library-selection/SKILL.md) | Качественный: первичные источники, совместимость и сохранение выбранного SDK. |
| [telegram-localization](../.agents/skills/telegram-localization/SKILL.md) | Качественный, исправлен: locale/timezone/валюта разделены; проверки учитывают Python-only задачу. |
| [telegram-mini-app-architecture](../.agents/skills/telegram-mini-app-architecture/SKILL.md) | Качественный, исправлен: границы, состояние, восстановление и соразмерный план/реализация. |
| [telegram-mini-app-auth](../.agents/skills/telegram-mini-app-auth/SKILL.md) | Качественный: HMAC/Ed25519 разделены, дубли/freshness и права не подменены подписью. |
| [telegram-mini-app-design-system](../.agents/skills/telegram-mini-app-design-system/SKILL.md) | Качественный: контракты компонентов, семантика, focus, токены и реальные экраны. |
| [telegram-mini-app-device-qa](../.agents/skills/telegram-mini-app-device-qa/SKILL.md) | Качественный: версии/launch/evidence и честные blocked/not-run для отсутствующей среды. |
| [telegram-mini-app-integration](../.agents/skills/telegram-mini-app-integration/SKILL.md) | Качественный: канал ответа зависит от запуска; общий серверный объект. |
| [telegram-mini-app-native-capabilities](../.agents/skills/telegram-mini-app-native-capabilities/SKILL.md) | Качественный: version/availability/init, callback semantics и полезный fallback. |
| [telegram-mini-app-performance](../.agents/skills/telegram-mini-app-performance/SKILL.md) | Качественный: baseline, сопоставимое измерение и разграничение метрик. |
| [telegram-mini-app-typescript](../.agents/skills/telegram-mini-app-typescript/SKILL.md) | Качественный, формулировка уточнена: adapter, runtime JSON и публичная конфигурация. |
| [telegram-mini-app-ui](../.agents/skills/telegram-mini-app-ui/SKILL.md) | Качественный: визуальная система, responsive, insets и доступность. |
| [telegram-notifications](../.agents/skills/telegram-notifications/SKILL.md) | Качественный, исправлен: dispatch gate, отмена, lease и политика неизвестной доставки. |
| [telegram-observability](../.agents/skills/telegram-observability/SKILL.md) | Качественный: корреляция, конечный output, ограниченные labels и отказ sink. |
| [telegram-payment-provider](../.agents/skills/telegram-payment-provider/SKILL.md) | Качественный: adapter отражает capabilities и собственный протокол провайдера. |
| [telegram-payments](../.agents/skills/telegram-payments/SKILL.md) | Качественный, исправлен: товар/Stars/provider, выдача, продление и условия покупки. |
| [telegram-platega](../.agents/skills/telegram-platega/SKILL.md) | Качественный, исправлен: transaction и subscription/charge разделены; неполная ветка обозначена. |
| [telegram-profiles](../.agents/skills/telegram-profiles/SKILL.md) | Качественный, исправлен: маршруты профиля и реальные BusinessBotRights. |
| [telegram-project-planner](../.agents/skills/telegram-project-planner/SKILL.md) | Качественный, редакторская правка: MVP и выбор формы продукта без обязательной инфраструктуры. |
| [telegram-python-backend](../.agents/skills/telegram-python-backend/SKILL.md) | Качественный: права, scoped idempotency, DB constraints, миграции и concurrent sessions. |
| [telegram-security-review](../.agents/skills/telegram-security-review/SKILL.md) | Качественный, уточнен: фактические границы доверия и разные webhook protocols. |
| [telegram-testing](../.agents/skills/telegram-testing/SKILL.md) | Качественный: значимые инварианты, реальные гонки и разделение уровней доказательств. |
| [telegram-user-client](../.agents/skills/telegram-user-client/SKILL.md) | Качественный: user session, allowlist/history/checkpoints без скрытых действий аккаунта. |
| [telegram-yookassa](../.agents/skills/telegram-yookassa/SKILL.md) | Качественный, исправлен: capture/status/authenticity и ограниченная provider idempotency. |

## Проверки этого прохода

| Проверка | Результат и граница |
| --- | --- |
| Валидатор коллекции и официальный quick_validate | 33/33; формат, метаданные и локальные ресурсы. |
| Тесты репозитория | 16/16, без пропусков; установщик и API parser. Вывод (`output/quality-reaudit/repository-tests.txt`, локальный артефакт). |
| Frontend contract models | 23/23, повторены родителем. HMAC на опубликованном искусственном векторе aiogram, строгий разбор/freshness, состояние и fake LocationManager. Это Python-модели, не UI/WebView. Результаты (`output/quality-reaudit/frontend-contract-tests.json`, локальный артефакт). |
| SDK/fake-client probe | 15/15, повторены родителем: PTB 22.8, aiogram 3.31.0, Telethon 1.45.0. Проверены реальные модели/сериализация и изолированные сценарии. Результаты (`output/quality-reaudit/platform-sdk-tests.json`, локальный артефакт). |
| Polling probe | Реальный aiogram 3.31.0 с fake BaseSession: offset 101 запрошен при незавершенном handler update 100; имитация остановки оставила 0 commits. Родитель повторил наблюдение. Telegram-сеть не использовалась. Трасса (`output/quality-reaudit/polling-probe.json`, локальный артефакт). |
| Свежая схема API | Bot API 10.3: 185 методов/400 типов; изменений entries относительно сохраненного индекса не обнаружено. Это проверка схемы, не всех методов. |

Все три ветви также подготовили по три конкретных решения сценариев. Backend сценарии являются контрактами/псевдокодом; они не объявлены выполненными платежами или HTTP-приложением. Предыдущие 17 TypeScript/27 Python и browser matrix приведены в [отчете расширения](skill-extension-review.md); в этом проходе они не запускались заново и не добавлены к новым счетчикам.

## Воспроизведение и ограничения

Архив материалов аудита (`output/quality-reaudit/reaudit-evidence.zip`, локальный артефакт) содержит исходники проб, результаты, три независимых отчета и сценарии. В архиве нет зависимостей, полных скачанных HTML-документаций или пользовательских credentials. Полные исходные пути в JSON относятся к месту выполнения; после распаковки исполняемые пробы сохраняют результат рядом с собой.

Из каталога соответствующей пробы:

```powershell
# frontend/probes.py: стандартная библиотека Python
python -X utf8 probes.py
# platform/scenario_probe.py: проверенные версии в отдельном uv окружении
uv run --with "python-telegram-bot==22.8" --with "aiogram==3.31.0" --with "Telethon==1.45.0" python -X utf8 scenario_probe.py
# backend/polling_probe.py: fake transport, без Telegram HTTP
uv run --with "aiogram==3.31.0" python -X utf8 polling_probe.py
```

Реальные Android/iOS/планшеты, Telegram Desktop/Web, клавиатура, native permissions, платежные sandbox и живые аккаунты здесь не испытывались. Нет нового свежего Telegram initData vector или исполняемой Ed25519 проверки. Офлайн-модели не измеряют красоту, мобильную производительность или качество конкретного production приложения.

Прямая документация Crypto Pay снова вернула 403; проверка использовала индексированную официальную страницу с обозначенной давностью. Тело Platega callback статуса подписки получить не удалось: перед использованием этой ветки нужна текущая схема. Эти границы сохранены в навыках и [sources.md](sources.md); неизвестные поля не были придуманы.

Логи и снимки с путями `output/…` — локальные артефакты исторических проверок. Они не входят в Git и не доступны в свежем клоне. Для текущей принятой версии смотрите [сохраненную приемку 031](v1-checks/031.json); для нового прогона выполните `python scripts/verify_pattern_packages.py`.
