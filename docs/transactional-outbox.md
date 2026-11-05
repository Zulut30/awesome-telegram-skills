# Transactional outbox и неизвестный результат отправки

Термины: квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта; **outbox** — события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик выполняет их позже; **неизвестный результат** — запрос мог выполниться, но ответа нет (таймаут, обрыв связи); повторять вслепую нельзя, сначала сверка; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

`SQLiteOutbox` сохраняет намерение внешней отправки **в той же транзакции**, что
и бизнес-запись. Отдельный worker получает durable claim, выполняет внешний
вызов и сохраняет подтверждённый результат. SDK и обязательных сервисов нет.
Outbox не выполняет HTTP и не обеспечивает exactly-once для Telegram `sendMessage`.

## Одна транзакция для бизнес-состояния и намерения

```python
from telegram_patterns import SQLiteOnce
from telegram_patterns.outbox import SQLiteOutbox

once = SQLiteOnce("project.sqlite")
outbox = SQLiteOutbox("project.sqlite", max_attempts=5)
once.initialize()     # либо миграции проекта
outbox.initialize()

def apply(connection):
    connection.execute("INSERT INTO orders(id) VALUES(?)", (order_id,))
    outbox.enqueue(connection, scope, notification_id, {
        "method": "sendMessage", "chat_id": verified_chat_id, "text": "Заказ принят",
    })
    return {"order_id": order_id}

result = once.run_guarded(
    actor_scope, order_id, verified_order_payload, apply, check=current_access_and_revision,
)
```

Здесь `apply` получает соединение `SQLiteOnce`; бизнес-запись, outbox intent и
business receipt фиксируются вместе. Callback `check` проверяет текущий actor,
контекст и ACL, а для нового эффекта — ожидаемую revision, как описано в
[concurrent-actions.md](concurrent-actions.md). Обработчик использует стабильные
серверные ID и существующие доменные ограничения. Очередь сама не подтверждает
личность и не проверяет права на отправку: worker также проверяет актуальный
consent/ACL перед внешним вызовом.

`enqueue(connection, scope, operation_key, payload)` требует активную транзакцию
на **том же main-файле SQLite**. Autocommit, in-memory database и соединение с
другой основной базой отвергаются. Метод не открывает второй connection и никогда
не делает commit/rollback. Возвращаемый `OutboxReceipt` предварителен до commit
владельца транзакции. Для собственного transaction manager передайте его
`sqlite3.Connection` и дайте исключению откатить всю бизнес-операцию. Не подавляйте
ошибку enqueue с последующим commit бизнес-изменения.

Повтор `(scope, operation_key)` с тем же строгим JSON возвращает
`duplicate=True`, сохраняя состояние и attempts. Другой payload вызывает
`OutboxConflict`. Deduplication намерения не отменяет произвольные повторные
бизнес-записи: используйте `SQLiteOnce.run_guarded` или доменный unique operation
ID в той же транзакции. Не генерируйте новый ключ при сетевом повторе.

Scope/key ограничены 256 UTF-8 байтами, worker ID — 128, evidence reference — 512.
Payload — JSON object без неоднозначных типов; receipt тоже строгий JSON.
По умолчанию каждый ограничен 1 MiB; лимит настраивается в диапазоне 128 байт —
8 MiB. Не храните токены и секреты в payload/receipt/evidence. Схема создаётся
явным `initialize`; несовместимая версия требует проверенной миграции.

## Отправка и durable fencing

```python
claim = outbox.claim(scope, worker_id, lease_seconds=30)
if claim is not None:
    # Claim уже committed. Передайте claim.payload адаптеру проекта.
    # Ограничьте время запроса; оставьте запас на сохранение результата.
    try:
        receipt = send_with_project_transport(claim.payload)
    except BaseException:
        outbox.mark_unknown(claim)
        raise
    else:
        outbox.confirm(claim, receipt)
```

Состояния и переходы:

| Исходное состояние | Действие | Результат |
| --- | --- | --- |
| pending, наступил available_at | claim | sending, attempt + 1, новый случайный token |
| sending, lease действует | confirm с окончательным успешным ответом | sent и receipt |
| sending | timeout/cancel/disconnect → mark_unknown | unknown |
| sending, lease истёк | recover_expired либо следующий claim в этом scope | unknown |
| unknown, актуальная revision | reconcile: sent + evidence | sent и подтверждённый receipt |
| unknown, актуальная revision | reconcile: unresolved + evidence | unknown |
| unknown, актуальная revision | reconcile: absent + evidence | pending с задержкой либо failed при лимите |

Claim фиксируется **до** внешнего вызова. Random token, worker identity и attempt
защищают переходы в БД от другого или прежнего worker. Два процесса не получают
один pending intent. Deadline сравнивается строго: при `now == lease_until`
claim уже истёк. Старый sender не может подтвердить новый attempt или обойти
unknown. Повтор `confirm` с тем же успешным receipt и ещё принадлежащим claim
идемпотентен; изменение receipt — конфликт.

`OutboxLeaseLost` наследует `UnknownOutcome`; его безопасный error report
имеет `outcome=unknown` и `recovery=reconcile`: потеря локального claim не означает
отсутствие внешнего эффекта. Некорректный receipt вызывает локальную
`ValidationFailure` и оставляет sending; это отказ сохранить receipt, а не
доказанный отказ отправки. Переведите его в unknown или восстановите после lease.

Fencing защищает локальные переходы, но не останавливает зависший внешний запрос.
Не продолжайте отправку после утраты владения. У API без server-side fencing
пауза процесса или истечение lease сами по себе не доказывают отсутствие эффекта.
Нет автоматического продления lease: задайте ограниченный timeout запроса и
достаточный lease с запасом на сохранение ответа. При позднем успешном ответе,
который уже не проходит `confirm`, восстановите unknown и сверяйте его явно.

## Сверка и разрешение повтора

```python
record = outbox.get(scope, notification_id)
# После проверки у провайдера / проверки окончательного отказа:
outbox.reconcile(
    scope, notification_id,
    expected_revision=record.revision,
    outcome="sent", evidence_ref="provider-audit:receipt-123",
    result={"message_id": 123},
)
```

Сверка разрешена только для `unknown` с текущей `expected_revision`. Revision
меняется при переходах; параллельное устаревшее решение получает `OutboxConflict`.
`get` сам ничего не восстанавливает: вызовите `recover_expired(scope)` явно или
пусть это сделает следующий `claim` этого scope.

`outcome="absent"` — явное утверждение доверенного кода, что **эффекта нет и
предыдущий attempt больше не может произвести поздний эффект**. Библиотека не
может проверить истинность внешнего evidence; проект сохраняет проверяемую
ссылку на аудит. Пустая выборка у eventually-consistent API, timeout, истёкший
lease или остановка клиента при запросе на сервере недостаточны. Если это не
доказано, используйте `unresolved` и оставляйте intent для дальнейшей сверки.
После доказанного отсутствия можно указать `retry_after` до 86400 секунд.
Attempts увеличиваются при claim и ограничены сохранённым `max_attempts`
(по умолчанию 5, допустимо 1–1000). При исчерпании `absent` переводит intent в
`failed`, а неизвестный исход остаётся `unknown` даже на последнем attempt.

Чтение обычно можно повторить в пределах deadline/backoff. Идемпотентную запись
можно повторять только по документированному контракту провайдера с тем же
устойчивым idempotency key и payload. Неидемпотентную запись с неизвестным
исходом сначала сверяют. Этот outbox выбирает консервативную границу: даже
истёкший sending автоматически не возвращается в pending.

При подтверждённом отказе Bot API с flood control поле
[`ResponseParameters.retry_after`](https://core.telegram.org/bots/api#responseparameters)
указывает время ожидания до допустимого повтора. Адаптер проверяет настоящий
ответ провайдера и отсутствие эффекта, сохраняет evidence и задержку. Один HTTP
status, exception name или timeout не заменяет такой проверки.

## Потерянный ответ и Telegram

Возможное окно: Telegram создал сообщение → ответ потерян → локальный receipt
не сохранён. Повтор `sendMessage` может создать дубль. Локальный operation ID
не является серверным idempotency key Telegram. В опубликованном контракте
[`sendMessage`](https://core.telegram.org/bots/api#sendmessage) нет общего параметра
idempotency key и метода поиска отправки по произвольному operation ID; это
ограничивает автоматическую сверку. При отсутствии достоверного подтверждения
оставьте unknown и предусмотрите проектный путь ручного разрешения.

[`Making requests`](https://core.telegram.org/bots/api#making-requests) описывает
успех через `ok=true` и `result`; при отправке метода прямо в webhook response
нельзя узнать успешность и получить результат. Для этого сценария outbox нужен
обычный контролируемый запрос, а не неотслеживаемая отправка в ответе webhook.
Не выводите «сообщение доставлено» из одного факта enqueue.

Сбой до business+intent commit откатывает оба. Сбой после commit сохраняет оба;
бизнес-операция восстанавливается по прежнему ID. Сбой после claim до отправки
консервативно даёт unknown: из одного outbox нельзя отличить его от сбоя после
внешнего эффекта. Сбой после `confirm` сохраняет sent. Храните ledger и intents
не меньше окна повторов; согласуйте retention и доступ к данным с проектом.
Синхронные методы вызываются через модель исполнения host, например thread
boundary в async backend. Отмена await не останавливает уже выполняемый поток.

## Пример и проверка

[offline_outbox.py](../examples/python/offline_outbox.py) выполняет настоящий
`SQLiteOnce.run_guarded` и `enqueue` на одном connection, перезапускает отдельный
sender через spawn и `os._exit` после эффекта. Второй SQLite-файл моделирует
полностью наблюдаемого провайдера без защиты от дублей. Пример проверяет unknown,
отсутствие автоматической отправки и сверку sent без второго сообщения. Такой
lookup доступен fake-провайдеру; он не заявляется возможностью Telegram.

```sh
python examples/python/offline_outbox.py
python -m unittest discover -s packages/python/tests -p test_outbox.py -v
```

`test_process_crash_before_business_commit_rolls_back_state_and_intent` и
`test_process_crash_after_business_commit_keeps_intent_and_replays_business`
проверяют реальные процессы до/после общей фиксации. Тесты
`test_two_processes_same_business_operation_commit_one_state_and_one_intent` и
`test_two_processes_cannot_claim_the_same_external_attempt` проверяют гонки.
`test_lost_external_response_remains_unknown_and_reconciles_without_duplicate_send`
фиксирует внешний эффект до аварии. Отдельные проверки покрывают fencing,
rollback, подмену payload, доказанное отсутствие, предел attempts и stale
reconciliation. Семь process-тестов помечены integration и пропускаются при
`TELEGRAM_PATTERNS_TESTS=unit`. Offline acceptance не доказывает доставку реальному
Telegram или надёжность конкретного диска при потере питания.

Источники проверены 2026-11-05:
[SQLite transactions](https://www.sqlite.org/lang_transaction.html),
[Bot API: requests](https://core.telegram.org/bots/api#making-requests),
[sendMessage](https://core.telegram.org/bots/api#sendmessage),
[ResponseParameters](https://core.telegram.org/bots/api#responseparameters).
