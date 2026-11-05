# Безопасная локальная telemetry

Термины: **outbox** — события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик выполняет их позже.

`Telemetry` связывает Update, действие, бизнес-операцию и job через непрозрачные
references. Она содержит счётчики, duration и retries с конечным набором labels,
а также необязательный локальный sink уже сериализованных JSON-событий.
Мониторинг, SaaS, OpenTelemetry и очереди не обязательны.

```python
from telegram_patterns.telemetry import Telemetry

telemetry = Telemetry(host_telemetry_key, local_sink)
with telemetry.bind(bot_id=bot_id, update_id=update_id, job_id=job_id):
    with telemetry.bind(bot_id=bot_id, action_id=action_id,
                        operation_id=operation_id, inherit=True):
        telemetry.emit("operation", "succeeded", duration_ms=elapsed_ms, attempt=attempt)
snapshot = telemetry.snapshot()
```

## Контекст и сериализация

Ключ — отдельные bytes длиной 32–1024, из конфигурации host. Для стабильного
сопоставления между процессами они используют тот же ключ; ротация меняет refs.
Не передавайте Bot token как telemetry key. Ключ не сериализуется и не выводится
через repr. Raw ID хешируется HMAC-SHA256 с отдельным domain (`bot`, `update`,
`action`, `operation`, `job`), bot scope и типом ID; выводятся 32 hex-символа.
Одинаковые числа разных типов/domain/bot не сливаются. Это псевдонимизация,
а не анонимность: доступ к ключу и журналу ограничивается правилами проекта.

`bind` по умолчанию начинает новый trace. Долгоживущий worker создаёт root
context для **каждого job**. Вложенный `inherit=True` сохраняет trace и имеющиеся
refs, добавляя action/operation того же бота; другая bot scope отвергается.
ContextVar reset в finally восстанавливает прежний контекст при ошибке и
отмене. Параллельные asyncio tasks изолированы, однако задача наследует контекст
при создании: для нового job явно создавайте новый root binding.
References предназначены для связи событий и не используются как auth или
idempotency keys.

У события только allowlist: `stage`, `outcome`, `duration_ms`, `attempt`,
`error_code`, `error_category`, `error_outcome`, `context`. Нельзя передать
произвольные payload, headers, URL или вложенный body. Исключение превращается
в метаданные через `safe_error_report`; его str/args/traceback и публичный текст
не отправляются sink. Строки correlation ID только хешируются, исходное
значение не становится полем события. Это не фильтр стороннего HTTP logger:
его URL/headers необходимо отдельно исключить до записи.

## Метрики и sink

Stage — `update`, `action`, `operation`, `job`. Outcome — `started`, `succeeded`,
`replayed`, `rejected`, `failed`, `unknown`, `cancelled`, `quarantined`. Другие
значения отвергаются до записи и создания metric series. Error category берётся
из конечного набора `safe_error_report`, а не из произвольного exception name.
Duration — конечное число 0–86400000 ms, attempt — целое 1–1000.

`TelemetrySnapshot.metrics` — immutable tuple записей `TelemetryMetric` с
labels `(stage, outcome, error_category)` и показателями `count`,
`duration_ms_sum`, `duration_ms_max`, `retries`. Последний считает события с
`attempt > 1`, а не уникальные бизнес-повторы. Средняя duration = sum/count
для выбранной series; `started` и итоговые события учитываются отдельно.
Trace/ref/user/order ID не становятся labels, поэтому число series не растёт
от количества пользователей. Снимок можно читать локально или передавать уже
выбранному monitoring adapter; он ничего не отправляет самостоятельно.

Sink — быстрая синхронная функция `sink(serialized_json)`, например локальный
writer проекта. Ошибка sink не отменяет бизнес-действие: увеличивается
`sink_failures`, исходное исключение не логируется рекурсивно. Прямой async sink
отвергается; coroutine, возвращённая ошибочной sync-обёрткой, закрывается и
учитывается как sink failure. Встроенной очереди нет: медленный sink блокирует
свой вызывающий поток, поэтому host использует быстрый writer или существующий
bounded exporter с собственной drop policy. Счётчики в памяти обнуляются при
рестарте; это не durable аудит и не источник истины для бизнес-операций.

Полезные локальные сигналы: увеличение `job/quarantined`, ненулевой
`operation/unknown`, рост `duration_ms_max`, `retries` и `sink_failures`.
Сверяйте отсутствие данных с активностью процесса; ноль ошибок при выключенном
worker не является подтверждением здоровья. Backlog можно читать существующим
`SQLiteInbox.counts`; outbox unknown остаётся отдельным durable состоянием.
Владелец определяет окно, порог и действие по этим сигналам, не вводя обязательный
внешний мониторинг.

## Совместимость с UpdateObserver

Существующий aiogram `UpdateObserver` сохраняется. Его async recorder получает
safe `UpdateTrace`; host сопоставляет фиксированные phases и передаёт update ID
в bind. Чтобы связывать весь handler, outer wrapper создаёт один root context
вокруг `UpdateObserver`, а recorder использует текущий контекст:

```python
async def record(trace):
    outcomes = {"received": "started", "handled": "succeeded", "unhandled": "rejected",
                "failed": "failed", "cancelled": "cancelled"}
    telemetry.emit("update", outcomes[trace.phase])

observer = UpdateObserver(record)  # IDs остаются opt-in по прежнему контракту

async def outer(handler, event, data):
    with telemetry.bind(bot_id=configured_bot_id, update_id=event.update_id):
        return await observer(handler, event, data)
```

Wrapper регистрируется на `dispatcher.update` вместо отдельной повторной
регистрации того же observer. Для duration измерьте `perf_counter` вокруг
нужной границы и передайте итоговое значение; лог received не означает
business completion. `InboxWorker` уже создаёт context и измеряет duration job.

## Проверка

`test_serialized_events_contain_only_allowlisted_fields_and_hashed_refs`
проверяет итоговый JSON с контрольными строками: URL с токеном бота, его percent-encoding, `initData`,
Authorization, Cookie и вложенным текстом исключения.
`test_concurrent_tasks_keep_independent_update_action_operation_and_job_context`
проверяет параллельные контексты, а
`test_metrics_have_finite_labels_without_ids_and_measure_duration_retries_and_failures`
— 1000 различных operation ID без роста labels. Отдельно проверяются nested
reset, ошибка sink и ошибочная async-обёртка без RuntimeWarning.

```sh
python -m unittest discover -s packages/python/tests -p test_telemetry.py -v
python examples/python/offline_worker.py
```

Проверено 2026-11-05, локальный serialized sink без внешней отправки:
[Python ContextVar и asyncio](https://docs.python.org/3.11/library/contextvars.html#asyncio-support).
