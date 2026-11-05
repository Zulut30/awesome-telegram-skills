# Shop backend: границы identity, sessions и recovery

5 ноября 2026; локальное дополнение к пунктам 41–44 и серверной части 49. Действующий aiohttp/SQLite/Python backend `examples/shop` сохранен; frontend transport использует сгенерированный из OpenAPI TypeScript client. Это experimental example, не production certificate, не приемка live Telegram и не основание автоматически закрыть целиком 41–44/49.

## API и полномочия

| Маршрут | Личность/права | Результат и отказ |
| --- | --- | --- |
| `POST /api/session` | Exact same-origin, JSON только `initData`; серверная HMAC/age/user validation по configured bot token | `{token,scope,expires_in:600}`; forged/wrong-bot/expired/future/malformed launch → 401, extra/duplicate body fields → 422 |
| `POST /api/session/rotate` | Exact Origin, единственный bearer, JSON `{}`; live session ищется внутри write transaction | Новый token с тем же server-derived scope; старый сразу invalid. Повтор/expired/revoked → 401 |
| `POST /api/session/revoke` | Те же guards; только текущая session, без actor/scope body | `{revoked:true}`; повтор → 401. Другие session tokens остаются действительными |
| `GET /api/catalog`, `GET /api/policy`, static/index | Публичные данные | Никаких персональных DTO или session secrets |
| Orders/create/list/by-ID/operation lookup/invoice, content | Server bearer identity на каждом запросе; SQL bot+actor scope и текущая серверная роль/права товара/заказа | Чужой order/content/invoice → 403; чужая operation → 404; чужой actor не видит order в списке |

Bearer хранится в памяти frontend, не cookie/localStorage/sessionStorage. `scope=bot_id:user_id` помогает выбирать pending storage, но не авторизует. DB сохраняет только token hash/bot/actor/expiry; ни raw token, ни initData. Session issue/rotation/revoke долговечны, схема SQLite версии 2 добавляет таблицу серверных ролей атомарной миграцией из версии 1: существующие сессии, заказы, квитанции и доступ сохраняются, неизвестная версия отклоняется. DELETE старого token и INSERT нового выполняются в одной `BEGIN IMMEDIATE` transaction; ошибка INSERT откатывает DELETE. Конкурентный rotate одного token имеет одного победителя.

Expiry сравнивается с серверными часами: `expires > now`. Rotation выдает TTL 600 секунд заново; absolute lifetime сверх этого не вводится. Revoke не отменяет уже авторизованные in-flight запросы, другие устройства/сессии и подписанную Telegram initData. Свежая initData может выдать новую сессию; это session logout, а не блокировка Telegram пользователя/кражи launch data. Для инцидентного account ban/глобального logout нужен отдельный полномочный контракт, которого этот пример не заявляет.

## Same-origin и вход

Mutating endpoints требуют один точный configured `Origin`. Private GET без Origin допускается для обычного same-origin чтения; явно foreign/duplicate Origin отклоняется. Единственный `Authorization: Bearer ...` обязателен, cookies/query/body не используются для identity. Нет permissive CORS/ACAO; cross-origin preflight не разрешается. CORS не заменяет bearer/ACL. JSON имеет строгие поля, duplicate-key refusal, Content-Type `application/json` и общий лимит body 32768 bytes. Ответы сохраняют `no-store`, CSP, nosniff и no-referrer.

Configured origin требует HTTPS; только явный loopback fixture допускает `http://127.0.0.1:port`. Это выбранная политика этого same-origin demo, не универсальная политика стороннего API.

## Текущие роли и объектные права

Таблица `shop_roles` привязана к bot/actor. Без переопределения действует обычная роль `customer`; `viewer` читает только собственные заказы и оплаченный контент, но не создает заказы/счета и не подтверждает pre-checkout. `blocked` не читает и не изменяет личные бизнес-объекты. Только доверенная конфигурация владельца вызывает `Store.configure_role`; browser/body/query не назначает роль, HTTP-маршрута смены ролей нет. Роль перечитывается в каждой бизнес-операции, а не кешируется в session. Ротация/отзыв собственной сессии сохраняются доступными независимо от роли.

Создание заказа использует `SQLiteOnce.run_guarded`: роль проверяется в writer-транзакции до нового эффекта и до возврата сохраненного повтора. Подготовка счета проверяет роль и владельца в своей writer-транзакции до внешней отправки; pre-checkout делает это до подтверждения. Отзыв роли не отменяет уже начавшийся сетевой эффект. Поэтому сохранение результата ранее начатого invoice и прием подлинного платежного факта остаются возможными: платеж после ограничения роли записывается как `review`, без новой выдачи доступа. Это не клиентская бизнес-операция и не основание игнорировать реальную оплату.

## Потерянный ответ, restart и смена аккаунта

Session lifetime независим от business operation identity. Если ответ создания заказа потерян после commit, новый вход и `GET /api/operations/{originalOperation}` возвращают исходный order ID. Повтор исходного POST с тем же actor/key/payload дает тот же заказ; другой payload → 409. При новом actor тот же UUID находится в другой principal scope и не открывает старый заказ.

Если потерян ответ rotation, старый token остается invalid, response replay/grace token не сохраняется. Клиент заново обменивает свежую initData и сверяет исходную business operation. Недоступный клиенту новый token истекает через TTL. Потерянный revoke response проверяется отказом старого token; повтор endpoint не становится новой business operation.

Restart после invoice `creating` переводит его в `unknown` через существующий `Store.recover`; новая invoice автоматически не отправляется. HTTP клиент может читать этот статус и ждать операторской сверки. Неизвестный исход внешней отправки не превращается в доказанный failure.

После серверного этапа действующий `main.ts` подключен к `ShopDomainState` через отдельные `shop-api.ts` и `telegram-adapter.ts`. `reconcile()` и загрузка страницы при 404 никогда не отправляют новый POST: только явное нажатие повторяет сохраненные ID/товары/условия. Новая версия условий блокирует этот повтор. Корзина, согласие, заказ, связанный запрос и личность отделены от отображения; ротация/отзыв, обновление при возобновлении и смена аккаунта используют серверные маршруты. Перед новым входом прежние видимые данные и кеш очищаются; поздний ответ прежнего аккаунта не меняет новый контекст. Подробный контракт — в каноническом `docs/mini-app-state.md`. Нельзя переносить чужие незавершенные запросы или создавать новый ID для невыясненного старого заказа. Локальная связанная проверка HTTP/SQLite/Chrome не заменяет клиентскую приемку на реальных устройствах.

## Проверки и предел evidence

Новые `examples/shop/tests/test_backend_sessions.py` используют реальные loopback TCP requests, aiohttp AppRunner, file SQLite и новые Store/app instances после restart. Отдельный тест трижды запускает существующий offline runtime в настоящем subprocess, дважды принудительно завершает процесс и проверяет session/order/revoke через HTTP после следующего запуска. Offline runtime блокирует внешнюю сеть и настоящий Bot API transport. Fault middleware существует только внутри теста: он обрывает настоящую TCP connection после успешного business handler, чтобы клиент действительно не получил ответ. Telegram/Stars transport и launch vectors синтетические; прежний тест дополнительно сверяет HMAC vector независимым aiogram parser. Реальная Telegram initData, устройства/пилот/платежные кабинеты не заявляются и не требуются для выполнения этой локальной работы.

| Requirement | Evidence |
| --- | --- |
| Durable issue/rotation/current revoke, bot/actor binding, hash storage | `test_rotation_and_current_session_revoke_are_durable_and_actor_bound` |
| TTL до/в момент expiry; expired rotate/revoke | `test_rotation_renews_ttl_and_expired_sessions_cannot_rotate_or_revoke` |
| Concurrent rotation и atomic rollback при INSERT failure | `test_concurrent_rotation_consumes_token_once_and_failed_insert_rolls_back` |
| Forged/wrong-bot/expired/future/duplicate/malformed launch; client identity refusal | `test_http_launch_refuses_forgery_wrong_bot_expiry_ambiguity_and_client_identity` |
| Origin/CORS/bearer duplicates/body/Content-Type limits | `test_http_origin_headers_content_type_and_body_limits_fail_closed` |
| Все private object ACL/server price/principal-scoped operation; нет HTTP payment grant | `test_every_private_object_route_uses_server_actor_and_owner_acl` |
| Реально потерянные order/rotation replies, SQLite restart, прежний opID, unknown invoice | `test_lost_order_and_rotation_replies_reconcile_same_operation_after_restart` |
| Настоящее process death, повторный HTTP запуск, сохранность session/order/revoke и invoice recovery | `test_http_session_order_and_revoke_survive_actual_process_death` |
| Роли на чтении/записи/повторе/счете/pre-checkout; новая initData не снимает запрет | `test_current_roles_gate_reads_writes_invoice_and_saved_replay` |
| Отзыв перед ожидающим writer, поздний платеж в review без выдачи | `test_role_revocation_precedes_queued_writer_and_late_receipt_is_reviewed` |
| Миграция v1→v2 сохраняет заказы/receipt/access/session; неизвестная версия остается без изменения | `test_additive_v1_role_migration_preserves_sessions_orders_and_access` |
| HTTP routes/DTO соответствуют OpenAPI, включая два новых endpoints | `test_routes_and_responses_follow_the_openapi_contract` в `test_shop.py` |

Команда из checkout с установленными dependencies: `$env:PYTHONPATH=(Resolve-Path 'examples/shop/src').Path; & output/production-run-2026-11-05/root-env/Scripts/python.exe -m unittest discover -s examples/shop/tests -v`. `root-env` — существующая локальная Python 3.13 среда с aiohttp 3.14.5/aiogram 3.31.0 и текущим editable core. Это source checkout acceptance, не установка нового wheel/tarball. OpenAPI client обновляется существующим `python scripts/build_openapi_types.py`; центральный generator не изменен.

Первичные источники сверены 5 ноября 2026: [Telegram Mini App validation](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app), [aiohttp JSON/handlers](https://docs.aiohttp.org/en/stable/web_quickstart.html#json-response), [SQLite transaction/BEGIN IMMEDIATE](https://www.sqlite.org/lang_transaction.html). Алгоритм core validator и версии библиотечных packages здесь не менялись. Результаты/команды локальных запусков сохраняются в ignored `output/production-run-2026-11-05/shop-backend/`; эти проверки не выпускают релиз.
