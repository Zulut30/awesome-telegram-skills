# Полная проверка 40 Telegram-навыков

3 октября 2026 года. Проверка охватила все 40 навыков и 119 канонических файлов. Инструкции пригодны для выбранных практических сценариев после двух уточнений. P0/P1 не обнаружены; найденный P2 закрыт. Этот вывод относится к содержанию и указанным примерам, а не ко всем функциям Telegram или готовности неизвестного production-продукта.

## Как проверяли

Три независимых агента сначала прочитали свои навыки без прежних отчетов и ожидаемых ответов, затем выполнили отдельный узкий запрос для каждого. Пробы создавались во временных каталогах. Сверены scope, сохранение существующего стека, серверные проверки, повторы, источники и наблюдаемый результат. Для проектирования результатом является конкретный план; для недоступных устройств — честная QA-матрица, а не фиктивный runtime pass.

Покрытие чтения (`output/quality-full-check/read-coverage.json`, локальный артефакт): 119/119 файлов, пропусков нет. Исходные hashes и byte snapshot сохранены в inventory-before.json (`output/quality-full-check/inventory-before.json`, локальный артефакт) и skills-before.zip (`output/quality-full-check/skills-before.zip`, локальный артефакт). После правок сохранен отдельный финальный снимок; исходный не заменен.

| Проверка | Фактический результат |
| --- | --- |
| Коллекция и официальный quick_validate | 40/40; frontmatter, UI metadata, локальные ссылки, Python syntax |
| Репозиторий | 16/16 unittest, без пропусков |
| Переносимость | 40 отдельных установок без соседних навыков; полная копия 119 файлов побайтово равна; dry run ничего не создал, overwrite отклонен |
| Новые frontend-пробы | 25 Python tests; 44 browser assertions; typecheck/build; 14 снимков компоновки |
| Новые платформенные пробы | 46 SDK/fake-transport checks на aiogram 3.31.0, PTB 22.8, Telethon 1.45.0 |
| Новые backend-пробы | 15 focused contracts: SQLite, localhost HTTP, crypto/SDK, FFmpeg и subprocess restart |
| Дополнительная регрессия | 5 locally signed RSA/JWT случаев и SQLite classification статуса/списания; родитель повторил после правок |
| Прежний Mini App пример, свежий запуск | 53/53: 27 поведения/API и 26 сравнений скриншотов; baseline не обновлялся |

Числа обозначают разные уровни и не суммируются как количество функций Telegram. Для нового frontend harness 44 — assertions, а не 44 независимых пользовательских пути. Небольшие собственные adapters/ledger проверяют применение инструкций; они не входят в навыки как готовая платежная или серверная библиотека.

## Исправления

**P2 — полный OIDC audience-контракт.** PyJWT 2.15.1 принял локально подписанные fixtures с дополнительной недоверенной `aud` и чужой `azp`; узкая OIDC-проверка их отклонила. В [web-login reference](../.agents/skills/telegram-web-login/references/login.md) теперь явно различаются JWT membership и доверенные аудитории OIDC, задана политика authorized party для выбранного flow и добавлены отрицательные случаи. Требование наличия `azp` для любого массива не введено. Правило сверено с [OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation); это не доказательство уязвимости Telegram или выпуска таких реальных токенов.

**P3 — покрытие Platega.** Ранее недоступный [callback статуса подписки](https://docs.platega.io/callback-по-статусу-подписки-40030962e0) теперь прочитан. Обновлен [reference](../.agents/skills/telegram-platega/references/platega.md): `Id = SubscriptionId`, опубликованный пример активации не подтверждает оплату, повторяющийся subscription ID не является уникальным ID всех событий статуса. Полный enum не объявлен проверенным. В SQLite-пробе два status events дали 0 grants, два charge IDs — 2 grants.

**P3 — документация каталога.** В текущем чате видны все 40 имен; устаревшее сообщение о видимости только 33 исправлено. Видимость каталога не подтверждает автоматическое выполнение каждого навыка.

Исправления независимо перечитаны: post-review (`output/quality-full-check/backend-post-review.json`, локальный артефакт). Первичная дополнительная проба и повтор родителя хранятся отдельно: independent (`output/quality-full-check/backend-supplemental-independent.json`, локальный артефакт), parent (`output/quality-full-check/backend-supplemental-parent.json`, локальный артефакт). Только две references навыков изменены; точный diff (`output/quality-full-check/skill-changes.diff`, локальный артефакт) и changes.json (`output/quality-full-check/changes.json`, локальный артефакт) сохранены.

## Результат каждого навыка

«Проверен» в этой таблице означает прочитанные инструкции и выполненный указанный сценарий. Ограничения не превращены в passed. Полные запросы, критерии, исходящие payloads, результаты и команды находятся в frontend (`output/quality-full-check/frontend-report.json`, локальный артефакт), backend (`output/quality-full-check/backend-report.json`, локальный артефакт) и platform (`output/quality-full-check/platform-report.json`, локальный артефакт) отчетах.

| Навык | Проверенный результат | Практическая граница |
| --- | --- | --- |
| telegram-project-planner | Конкретный MVP записи, границы и первый сценарий | План, без незапрошенной реализации |
| telegram-bot-api | Photo/entities/UTF-16, callback права, ошибки, полный API index | SDK/fake transport; реальной отправки нет |
| telegram-bot-python | SDK ACK при обработке/исключении, durable local inbox | Офлайн SDK; транспорт Telegram не подключен |
| telegram-python-backend | Конкурентный POST, constraints/replay с SQLite и HTTP | Без PostgreSQL/ORM/migration production |
| telegram-dialogs | Stale/denied/duplicate callback ACK и атомарный переход | Без полного FSM и видимого Telegram spinner |
| telegram-inline-mode | Личные результаты, cache_time/is_personal и изоляция | Synthetic queries, не реальный @bot поиск |
| telegram-groups | Два чата/темы, права и анонимный инициатор | Fake transport, не модерация живой группы |
| telegram-business-bots | Connection/rights, два владельца, revoke/loops | Без подключенного Business аккаунта |
| telegram-buttons | Зеленая кнопка/custom emoji serialization и fallback | Entitlement смоделирован; реальный рендер не проверен |
| telegram-profiles | Optional Premium, маршруты профиля и bot bio | Synthetic SDK данные; личный аккаунт не читался |
| telegram-library-selection | Импорты/поля текущих SDK и сохранение framework | Сверка конкретных возможностей, не каждого метода |
| telegram-user-client | Allowlist истории, checkpoint и проверка session scope | Fake MTProto client; настоящая user session не создана |
| telegram-mini-app-architecture | Границы/источники истины, action contract и приемка | Planning-only; план не выдан за внедренный код |
| telegram-mini-app-typescript | Строгая сборка, subscriptions и восстановление lifecycle | Synthetic lifecycle; реальный BFcache/bridge не доказан |
| telegram-mini-app-auth | Опубликованный dummy HMAC vector, tampering/expiry/duplicates | Без свежих Telegram данных и Ed25519 live-пути |
| telegram-mini-app-integration | Launch SDK payload и один серверный эффект заказа | Fake receipt, без доставки сообщения в Telegram |
| telegram-mini-app-native-capabilities | Init/denied/cancel/late/repeat location + ручной путь | Fake native callback; физического location dialog нет |
| telegram-mini-app-network-recovery | Timeout/TTL/reload/account scope и один эффект | Собственный local HTTP/SQLite контракт, без production offline shell |
| telegram-mini-app-ui | Компактная/широкая темы, focus, modal и reduced motion | Chrome DOM; настоящая клавиатура и reader не проверены |
| telegram-mini-app-design-system | Общие поля/действия, tokens и измеренный contrast | Fixture компонентов; не полный дизайн-аудит продукта |
| telegram-mini-app-ux | Ошибка/исправление/back сохраняют ввод; обзор перед отправкой | Агентский walkthrough, без исследования с участниками |
| telegram-mini-app-performance | Повторяемый лабораторный render benchmark и сырые метрики | Не INP и не скорость реального слабого Android |
| telegram-mini-app-device-qa | Матрица с правильными not-run для недоступных клиентов | Устройства/Telegram аккаунты отсутствуют |
| telegram-mini-app-visual-regression | Expected/current/diff; управляемое обрезание CTA обнаружено, restored совпал | Chrome/Windows fixture; baseline не перезаписан |
| telegram-localization | Python-only Babel: plural/fallback/date/money | Без ненужного frontend; локализация всех экранов не заявлена |
| telegram-payments | Stars order/consent/payment checks и один grant | Synthetic updates; настоящей покупки/возврата нет |
| telegram-cryptopay | Raw-body HMAC и duplicate invoice handling | Без testnet; свежесть полного Help Center не подтверждена |
| telegram-platega | Отдельные subscription/charge IDs, callbacks/reconciliation | Fake provider + свежий опубликованный пример, без merchant |
| telegram-yookassa | Capture/unknown и предел 24h idempotency | Документация + fake provider; test shop не подключен |
| telegram-payment-provider | Настоящая SDK signature проверка отдельного provider adapter | Без provider sandbox/покупок и всех прочих платежек |
| telegram-subscription-access | Периоды, duplicate/out-of-order/refund старого grant | Собственная product policy; календарные/partial refund варианты не все проверены |
| telegram-web-login | State/nonce/JWKS/identity и дополнительные audience cases после уточнения | Локально подписанные JWT; live redirect/code exchange не выполнен |
| telegram-admin-panel | HTTP tenant scope, revoke/revision и один audit event | Backend контракт; полного операторского UI/bulk flow нет |
| telegram-media-processing | Настоящий FFmpeg output/cancel и subprocess cleanup | Узкое аудио; полный OS sandbox и Telegram download не доказаны |
| telegram-notifications | Eligibility/dispatch граница и отписка с SQLite/HTTP | Доставка/429/DST в этом focused сценарии не проверены |
| telegram-observability | Async correlation и отсутствие конкретных canaries в sink | Локальный logging; не все сторонние collectors/loggers |
| telegram-deploy | Durable acceptance/restart граница на localhost | Без VPS release, публичного TLS и setWebhook |
| telegram-debugging | Read-only диагноз по фактам, сохранение updates/настроек | Fake environment, без восстановления production-инцидента |
| telegram-security-review | Чужой order_id, concrete deny/allow evidence | Узкий endpoint; не полный security audit продукта |
| telegram-testing | Concurrent duplicate payment и один durable effect | Собственная тестовая модель, без живого платежа |

## Выбор навыков

Новый независимый агент получил только names/descriptions и 56 запросов, без bodies и ожидаемых ответов: routing report (`output/quality-full-check/routing-report.json`, локальный артефакт). Критерии были сохранены заранее. Сопоставление (`output/quality-full-check/routing-grading.json`, локальный артефакт): 55/56 совпадений основного выбора; во всех 56 наборах присутствует ожидаемый навык, запрещенных расширений нет. Все 40 навыков представлены в выборе.

В запросе stale callback основным выбран debugging, dialogs — дополнительным. Для исправления уже работающего диалога это разумное сочетание; основное имя не объявлено строгим совпадением. Отмечены еще пересечения по scope в исходном отчете. Это проверка различимости описаний, без запуска автоматического загрузчика и без выполнения этих 56 запросов.

## Доказательства и воспроизведение

Исходники новых проб, snapshots входов, runtime artifacts и неуспешные первые fixtures: independent-probes.zip (`output/quality-full-check/independent-probes.zip`, локальный артефакт), manifest (`output/quality-full-check/probe-archive-manifest.json`, локальный артефакт). Зависимости/венвы/node_modules исключены; версии и команды указаны в отчетах. Пробы используют пути этого Windows компьютера; для другой среды нужно настроить interpreter/browser/library paths. Внутри только synthetic/test accounts, keys, payments и contacts.

Прежний пример Mini App сохранен отдельно: browser-example.zip (`output/quality-full-check/browser-example.zip`, локальный артефакт), fresh browser result (`output/quality-full-check/browser-recheck.json`, локальный артефакт). Родитель просмотрел компактную светлую, широкую темную компоновку и error/diff состояния обеих проб. Screenshot comparison подтверждает конкретную среду/состояние; не измеряет субъективную красоту и удобство с участниками.

Команды репозитория:

```powershell
uv run --with "PyYAML>=6,<7" python scripts/validate_skills.py
python -m unittest discover -s tests -v
uv run --with "PyYAML>=6,<7" python -X utf8 output/quality-full-check/check_collection.py
```

Для отдельного повторения новых OIDC/Platega случаев: `python supplemental.py` в восстановленном backend probe с версиями зависимостей из отчета. Скрипт создает новый attempt directory; первичный результат и parent repeat сохранены раздельно. Исправления первых fixtures относятся к собственной реализации проверяющих: StripeObject/expiry, SDK shortcut duplicate thread argument, serialized string/int, DOM module globals, Windows handle cleanup, ESM paths и stale field rendering. Исходные результаты не скрыты и не названы дефектами канонических навыков.

В backend snapshot один первоначальный Platega файл был перезаписан повторным сборщиком: byte original восстановлен из root pre-edit ZIP, SHA проверен. Это явно записано в provenance; реконструкция не выдана за исходный снимок.

## Оставшиеся проверки

Живой Telegram, BotFather/OIDC exchange, реальные платежные test environments, физические телефоны/планшеты, настоящая клавиатура/bridge/safe areas/fullscreen, screen reader, производительность слабого устройства и deployment выбранного продукта — not-run. Автоматическая активация всех навыков загрузчиком не подтверждена.

Прямая текущая документация Crypto Pay оставалась недоступна; локальная криптографическая проба не решает актуальность полного provider protocol. Сценарии за пределами таблицы и полный перечень [evaluation.md](evaluation.md) не объявляются выполненными. Ошибок или заглушек, мешающих переносу этих 40 навыков, в проверенном снимке не найдено.

Логи и снимки с путями `output/…` — локальные артефакты исторических проверок. Они не входят в Git и не доступны в свежем клоне. Для текущей принятой версии смотрите [сохраненную приемку 031](v1-checks/031.json); для нового прогона выполните `python scripts/verify_pattern_packages.py`.
