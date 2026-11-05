# Жизненный цикл durable worker

Термины: **ACK** — ответ на нажатие кнопки через `answerCallbackQuery`: клиент убирает индикатор ожидания; это не сообщение об успехе операции; **outbox** — события, сохраненные в той же транзакции, что и изменение данных; отдельный обработчик выполняет их позже; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

`InboxWorker` — SDK-free композиция существующего `SQLiteInbox`. Он не запускает
polling, не отвечает webhook и не владеет Bot/session/ORM. Владелец приложения
останавливает прием новых запросов, запрашивает stop, дожидается worker и затем
закрывает сессии, storage и process lock. Существующие `run_bot`, `UpdateObserver`
и lifecycle сервисного примера сохраняются.

```python
from telegram_patterns.worker import InboxWorker

worker = InboxWorker(inbox, bot_id, worker_id, decode, handle, telemetry=telemetry)
try:
    await worker.serve(stop_event)
finally:
    await owned_session.close()
```

## Прием, декодирование и завершение

Webhook сохраняет событие через `WebhookReceiver`/`SQLiteInbox` **до** успешного
HTTP-ответа. Worker обрабатывает уже принятые события; его логи или `done` не
являются самостоятельным ACK транспорта. `run_one()` возвращает `idle`, `done`,
`quarantined` или `lease-lost`.

`decode(payload)` — короткая синхронная локальная функция без сетевых вызовов.
Она проверяет поддерживаемый тип события и семантику установленного SDK. Не
принимайте пустой SDK Update после молчаливого удаления неизвестного поля.
Исключение декодирования сохраняет исходный JSON в quarantine с фиксированной
причиной `decode-failed`. Admission неизвестного типа уже сохраняется
`WebhookReceiver` как `unknown-update-kind`; worker не освобождает его при
установке нового decoder автоматически. `CancelledError` не считается ошибкой
decode: отмена сохраняется как прерванная обработка и распространяется владельцу.

`await handle(decoded, claim)` должен вернуть **ровно True** после durable
бизнес-завершения. Тогда выполняется fenced `inbox.complete`. Иное значение
сохраняет `handler-rejected`, исключение — `processing-failed`; `done` для этих
путей не ставится. По умолчанию worker выбирает quarantine для ручной сверки,
а не повторяет произвольный эффект. Если проекту нужен retry, он отдельно
обосновывает его безопасность и использует bounded `SQLiteInbox.retry` с
задержкой; бюджет attempts сохраняется inbox.

Стабильный update/job ID передаётся handler в `InboxClaim`. Обработка после
сбоя может повториться, поэтому бизнес-эффекту нужны доменный operation ID,
транзакционная дедупликация и outbox. Пример —
[SQLiteOnce.run_guarded](concurrent-actions.md) и
[transactional outbox](transactional-outbox.md). Lease inbox защищает локальный
переход состояния, но не удалённый эффект. Потеря lease возвращает `lease-lost`
и telemetry outcome `unknown`; это не доказательство отсутствия бизнес-эффекта.

## Stop, отмена и потоки

`serve(stop_event)` проверяет stop перед следующим claim. Если stop установлен
во время job, уже начатая работа завершается; следующая не принимается. Если
очередь пуста, Event пробуждает idle ожидание. Один экземпляр допускает одного
serve-владельца и один активный `run_one`: конкурентный вызов отвергается до
нового claim, а guard снимается в finally. Несколько процессов используют отдельные экземпляры и fenced
claims той же SQLiteInbox. Обработчик OS signals остаётся у выбранного host;
нового фонового процесса или второго polling consumer нет.

Для остановки с grace period владелец сначала устанавливает stop и ждёт task.
Если срок исчерпан, он отменяет task и **дожидается отмены**, затем закрывает
ресурсы. Прерванный handler пытается сохранить quarantine; если storage
недоступен или lease уже потерян, исходное событие остаётся durable processing
до восстановления lease. Нельзя притворяться, что оно успешно обработано.

```python
stop_event.set()
try:
    await asyncio.wait_for(asyncio.shield(worker_task), timeout=grace_seconds)
except TimeoutError:
    worker_task.cancel()
    await asyncio.gather(worker_task, return_exceptions=True)
# После этого — закрытие принадлежащих приложению ресурсов.
```

`settled_to_thread(sync_action, *args, **kwargs)` использует проверенный паттерн
сервисного `io_call`: shield сохраняет локальную задачу, а при отмене helper
дожидается её фактического окончания, включая повторную отмену, и затем
распространяет cancellation. Он не завершает поток принудительно. Это важно для
SQLite: отменённый await не должен освобождать lock или закрывать session,
пока thread ещё фиксирует транзакцию. Локальные операции должны иметь конечный
timeout; helper не даёт обещания мгновенной остановки зависшего кода.

Если отмена наступила при возврате уже committed claim, handler может не
запуститься, а job останется processing: после lease она восстанавливается с
тем же update ID. Если отмена наступила при сохранении успешного complete,
он уже мог committed. Результат выясняют по durable состоянию; отмена await не
является rollback. Внешние запросы, сделанные handler, требуют собственного
unknown/reconciliation контракта, который потоковая обёртка не заменяет.

## Проверка

`examples/python/offline_worker.py` связывает webhook/inbox,
worker, guarded business+outbox и локальную telemetry. Неизвестный envelope и
ошибка decoder сохраняются, stop дожидается текущего job, следующий остаётся
pending, ресурс закрывается после drain. Telegram и внешние ресурсы не вызываются.

```sh
python examples/python/offline_worker.py
python -m unittest discover -s packages/python/tests -p test_worker.py -v
```

`test_cancelled_thread_is_joined_even_after_second_cancel_before_owner_closes`
проверяет реальную SQLite-запись в thread и порядок commit → закрытие owner.
`test_stop_event_stops_admission_then_drains_job_before_resource_closure`
проверяет done текущего и pending следующего job. Остальные сценарии — ошибка
и отмена decoder/handler, сохранение неизвестного envelope, lost lease и отмена
при возврате claim. Это локальная проверка; доставку реальному Telegram проверяют
отдельно. Существующий `run_bot` по-прежнему закрывает свою SDK session.

Проверено 2026-11-05 для Python 3.11+:
[asyncio shield](https://docs.python.org/3.11/library/asyncio-task.html#asyncio.shield),
[to_thread](https://docs.python.org/3.11/library/asyncio-task.html#asyncio.to_thread).
