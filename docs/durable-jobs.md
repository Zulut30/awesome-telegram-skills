# Durable jobs и управляемые уведомления

Термины: **CAS** — сравнение с заменой: запись сохраняется, только если версия не изменилась с момента чтения; **outbox** — события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик выполняет их позже; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

`telegram_patterns.jobs.SQLiteJobQueue` хранит отдельные намерения уведомлений в
локальной SQLite. Компонент не требует SDK, очереди-сервиса или фонового демона и сам
ничего не отправляет. Приложение запускает worker, проверяет его полномочия и связывает
исходы своего transport с API очереди. Основа поведения взята из
[service-bot](../examples/service-bot/README.md); существующий пример не изменен.

## Намерение, получатель и расписание

```python
from telegram_patterns.jobs import SQLiteJobQueue

jobs = SQLiteJobQueue("private-data/jobs.sqlite", max_active_jobs=10000)
jobs.initialize()
# Только после проверки явного opt-in и возможности писать в данный chat.
jobs.set_recipient(123456789, 987654321, subscribed=True, reachable=True)
jobs.schedule(
    123456789, "booking:42:reminder:v1", 987654321,
    {"text": "Напоминание о записи"},
    due_at=1800000000, deadline_at=1800003600, max_attempts=3,
)
```

Ключ — `(bot_id, job_id)`. Повтор с теми же recipient, JSON, due/deadline и бюджетом
возвращает существующий статус; изменение любого из этих полей вызывает `JobConflict`.
Повтор после deadline также читает ранее сохраненное задание. Для переноса времени
отмените прежнее намерение и создайте новое с новым logical ID: старый идентификатор
не используется для другого содержания. Повторное создание не сбрасывает attempts.

`bot_id` — положительное точное целое, recipient — ненулевое signed целое;
`abs(id) <= 2**53-1`, `bool` исключен. Отрицательные group/channel chat IDs допустимы.
`job_id`, `worker_id`, `evidence_ref` соответствуют
`[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}`. Это opaque идентификаторы: не помещайте в них
секреты, текст сообщения или персональные сведения. Ограничение не заменяет
авторизацию вызывающего приложения.

Без recipient policy выдача работы запрещена. `subscribed` и `reachable` — разные
признаки: opt-in не доказывает доступность chat. `set_recipient()` сохраняет политику
и подавляет scheduled/claimed задания получателей без разрешения на доставку. `claim()` и `start()`
снова проверяют ее. При opt-out текущие sending получают `cancel_requested=True`;
уже начатая отправка может закончиться. Повторный opt-in не оживляет skipped jobs.
Host отвечает за актуальность consent, доступность chat, кампанию и деловую причину
уведомления. Открытие Mini App само по себе не является разрешением писать.

Времена — UTC Unix seconds, конечные числа от 0 до 253402300799. При создании deadline
должен быть в будущем и позже due; due может быть уже наступившим. Deadline запрещает
новый dispatch, но не отзывает начатый внешний запрос. Локальный timezone, DST,
повторяющееся расписание и генерация logical occurrence IDs принадлежат приложению.

## Claim, начало отправки и исход

```python
claim = jobs.claim(123456789, "worker-1", lease_seconds=30)
if claim is not None:
    dispatch = jobs.start(claim)
    if dispatch.state == "sending":
        # Только здесь разрешен один вызов transport с сохраненным payload.
        # Подтвержденный успех: finish(..., outcome="sent", message_id=...).
        # Подтвержденный 429: finish(..., outcome="flood", retry_after=...).
        # Недоступный recipient: finish(..., outcome="permanent-failure").
        # Потерянный ответ/timeout/disconnect: finish(..., outcome="unknown").
        send_and_record_outcome(claim, dispatch)
```

| Состояние | Смысл |
|---|---|
| `scheduled` | Durable намерение, ожидающее due/cooldown |
| `claimed` | Worker владеет подготовкой; внешняя отправка еще запрещена |
| `sending` | Начало внешней попытки зафиксировано; эффект уже возможен |
| `sent` | Приложение подтвердило успех, optional message_id сохранен |
| `cancelled` | Доставка подавлена до эффекта либо после подтвержденного flood rejection |
| `expired` | Новый dispatch не укладывается в полезный deadline |
| `skipped` | Нет policy, opt-out или recipient недоступен |
| `failed` | Окончательный отказ, исчерпание бюджета либо reviewed failed |
| `unknown` | Эффект возможен; требуется сверка, автоматической отправки нет |

Все мутации сериализуются `BEGIN IMMEDIATE`. `start()` проверяет текущий claim token,
worker, attempt, lease, state, deadline и eligibility в одной транзакции с резервом
rate interval. Только его возвращенное `state="sending"` разрешает один внешний вызов.
`scheduled`, `skipped`, `expired` или исключение запрещают dispatch. Повторный `start()`
уже начавшегося claim отклоняется. Ошибка commit/cancellation ожидающего async task
также не дает разрешения отправлять: попытка могла попасть в sending и затем потребует
сверки. DB-транзакция не удерживается на время сети.

`JobLeaseLost` наследует `UnknownOutcome`: общий `safe_error_report(..., operation="write")`
возвращает unknown/reconcile, поскольку после утраты sending lease внешний эффект
может уже существовать. `JobConflict` и `JobQueueFull` остаются локальными rejected.

`JobClaim` имеет token, attempt и lease; `renew()` продлевает живой claimed/sending и
не сокращает срок. На точной границе lease владение уже истекло. Старый worker не
может начать, завершить или продлить чужую попытку. `finish()` принимается только для
живого sending; его повтор после завершения отклоняется. Если подтверждение SQLite
записи потерялось, прочитайте `get()`, не вызывайте transport повторно.

После restart `recover(bot_id)` или следующий `claim(bot_id, ...)` переводит истекший
claimed в scheduled в пределах бюджета. Истекший sending становится unknown, включая
`cancel_requested=True`; он не повторяется даже после deadline. Это сохраняет
неопределенность и в случае crash до фактического HTTP-вызова после COMMIT start.
`get()` и `counts()` ничего не восстанавливают. Просроченные scheduled jobs становятся expired
во время recovery. Бюджет 1…100 хранится в каждой строке; потерянный pre-dispatch claim
расходует попытку. Отложенный до отправки rate конфликт возвращает попытку в бюджет.

## Отмена и сверка

`cancel(bot_id, job_id)` переводит scheduled/claimed в cancelled и отзывает token.
Повтор отмены идемпотентен. Для sending/unknown сохраняется только `cancel_requested`:
этот ответ не означает remote cancellation. Если Telegram затем подтвердил успех,
задание становится sent с сохраненным флагом; потерянный ответ остается unknown.
Отмена уже terminal задания не меняет его исход.

Для unknown нужна реальная проверка результата или явное решение владельца приложения:

```python
observed = jobs.get(123456789, "booking:42:reminder:v1")
reviewed = jobs.reconcile(
    observed.bot_id, observed.job_id,
    expected_revision=observed.revision,
    evidence_ref="incident:2026-11-05:42",
    outcome="sent", message_id=123,
)
```

`expected_revision` обеспечивает compare-and-set, `evidence_ref` хранит ссылочный
идентификатор host-owned audit record. Приложение обеспечивает reviewer authorization,
само доказательство, его сохранность и историю. Две конкурирующие сверки не могут
переписать друг друга; новая отмена также меняет revision. Допустимы только terminal
`sent` или `failed`. Reviewed failed не создает новую попытку. Компонент не придумывает
поиск исходящего сообщения по logical job ID и не обещает exactly-once внешней доставки.

## Flood control и пределы

В `finish(outcome="flood")` передавайте только подтвержденный Telegram 429 rejection с
`retry_after`, а не timeout или произвольное исключение. Telegram определяет этот
параметр как срок ожидания перед повтором.
[ResponseParameters](https://core.telegram.org/bots/api#responseparameters)

Бот и recipient имеют durable `next_at`. Успешный start резервирует оба интервала;
конкурирующий start отложится до разрешенного времени. Flood продлевает оба cooldown,
включая bot-wide ограничение других получателей. Worker не спит в ожидании retry:
задание снова scheduled с новым due, либо становится terminal при отмене, исчерпании
attempts, превышении wait budget или deadline. После opt-out повтор не выдается.

По умолчанию интервалы — 1 секунда для bot и 3 для recipient; это консервативная
локальная policy, которую host выбирает для своего сценария. Интервалы допускают
0.001…3600 секунд. Первая schedule для bot сохраняет policy и capacity в БД, все workers
используют ее. Новый конструктор не сбрасывает ограничения или cooldown; изменение
действующей policy требует проверенной host migration. Все sender-пути конкретного bot
должны участвовать в общем ограничителе либо учитывать внешний расход отдельно.
Локальный резерв не контролирует фактическое время отправки задержанного процесса и
не отменяет динамические ограничения Telegram.
[FAQ о лимитах](https://core.telegram.org/bots/faq#broadcasting-to-users)

`retry_after` — точное целое 1…2³¹−1 секунд. Автоматический retry допускается при wait
не более 86400 секунд, оставшихся attempts и полезном deadline. Более длинный
подтвержденный wait завершает job с `retry-window-exceeded`, сохраняя **полный**
bot/recipient cooldown; его нельзя сокращать до локального максимума и повторять раньше.
Permanent failure означает подтвержденную недоступность recipient: reachable становится
false и новые доставки подавляются. Неподтвержденные transport failures остаются unknown.
Платная отправка и расход Stars не включаются.

Активная capacity по умолчанию 10000 на bot, конфигурация 1…100000; scheduled, claimed,
sending и unknown занимают ее. При переполнении новый job отклоняется `JobQueueFull`,
старый duplicate продолжает читаться. Payload — JSON object, глубина до 64, конечные
числа, строковые ключи; канонический UTF-8 размер по умолчанию 1 MiB, допустимый лимит
128 байт…8 MiB. Lease больше 0 и не более 3600 секунд; SQLite lock timeout больше 0 и
не более 300 секунд. Ограничения конечны, новые config values не обнуляют уже сохраненные
attempts/cooldown. Terminal история сохраняется без автоматической очистки: host задает
retention, дисковый лимит, backup/restore и окно защиты от дубликатов.

## Границы интеграции и проверка

`schedule()` сохраняет собственное намерение в своей транзакции. Изменение брони/оплаты
и вызов schedule не образуют общую бизнес-транзакцию. Для согласования нужен host-owned
transactional outbox и проверенная доставка намерения с тем же job ID. Очередь не
импортирует будущую реализацию outbox и не скрывает эту границу.

Методы синхронные: в async worker используйте thread boundary. При shutdown прекратите
новые claims, завершите активный transport в пределах lease или оставьте sending для
unknown recovery. Возобновление worker не запускает сверку автоматически. Clock общий
для процессов одного хоста; откат wall clock может задержать recovery. `now=` нужен для
тестов, его нельзя брать из недоверенного update. Shared локальная SQLite и ее
файловая система принадлежат host; multi-region/NFS и power loss здесь не проверены.

`JobRecord` содержит state/reason, due/deadline, attempts/max_attempts, cancel_requested,
revision, message_id, evidence_ref и lease_until. Payload и claim token исключены из
repr; явные `.payload`/`.payload_json` остаются конфиденциальными данными. Reason codes
фиксированы: policy/deadline/cancellation, lease/budget/rate/flood, unknown и reconciliation
не содержат raw exception text. `counts()` возвращает только агрегаты; host дополняет
их возрастом очереди, количеством refusals/unknown и сигналами ошибок хранения.

```powershell
python -m unittest discover -s packages/python/tests -p test_jobs.py -v
python examples/python/offline_jobs.py
```

Тесты используют реальные temporary SQLite файлы и spawned процессы: гонку dispatch
interval, гонку двух CAS reviews, `os._exit` до start и после fake remote effect перед
finish. Проверены reopen, дедлайны, token fencing, opt-out до и после start, постоянный
отказ, flood cooldown/attempt budget, capacity и реальный lock timeout. Не устанавливайте
`TELEGRAM_PATTERNS_TESTS=unit` для process acceptance: эта переменная пропускает четыре
integration теста. Offline demo использует только fake transport, выводит safe status
и счетчики; живых сообщений и проверки прочтения нет.

Источники ResponseParameters и FAQ проверены 2026-11-05. Эти локальные проверки не
подтверждают live Telegram доставку, production нагрузку или готовность всего релиза.
