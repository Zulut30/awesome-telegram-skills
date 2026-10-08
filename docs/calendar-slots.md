# Календарь и запись на время

Доступно с 0.17.0, проверено на 0.24.0. SDK-free `CalendarMonth`, `TimeSlot`, `resolve_local_time`, `SlotSchedule`, `SlotBooking`, `SQLiteSlotStore` и optional aiogram `calendar_keyboard`, `time_slot_keyboard`. Full bot «дата → время → подтверждение» — рецепт `demo-calendar`: сначала `telegram-patterns run-recipe demo-calendar`, затем явный `--offline`. Пакеты предоставляются wheel/tarball; публикация в реестрах не предполагается.

Термины: **ACK** — ответ на нажатие кнопки через `answerCallbackQuery`: клиент убирает индикатор ожидания; это не сообщение об успехе операции; **CAS** — сравнение с заменой: запись сохраняется, только если версия не изменилась с момента чтения; квитанция (receipt) — сохраненная запись о выполненной операции; повтор возвращает ее вместо второго эффекта.

## Время и доступность

`resolve_local_time` принимает naive wall time, IANA key и явный `fold=0/1` для повторяющегося времени. DST gap и неоднозначное время без fold отвергаются. На Windows для IANA зон нужен optional extra `calendar`; проверены данные `tzdata==2026.5`. Системная база допустима для приложения, но pinned offline fixture требует указанную версию. `UTC` работает без extra. Ядро не импортирует aiogram и не меняет process TZ.

`TimeSlot` нормализует aware start/end в UTC, проверяет положительный полуоткрытый интервал `[start,end)`, enabled bool и ASCII key 1..24. `label(time_zone)` включает UTC offset, различая повторяющиеся wall times. `CalendarMonth` — immutable Monday-first grid с available/blocked датами одного месяца. Доступные даты сервер выводит из текущих enabled слотов в зоне отображения; календарь не резервирует ресурс.

## Серверная транзакция

`SQLiteSlotStore(database, authorize=callback, timeout=5)` требует один file SQLite. `initialize()` — явная additive миграция prefixed таблиц. `publish(resource, slots, expected_revision=0)` создает расписание; обновление CAS требует текущей revision. Publish — доверенная операция сервиса, не user route. Замена расписания не меняет сохраненные booking times.

Обязательный `authorize(connection, verified_actor_id, resource)` возвращает ровно `True` по текущим правам проекта. Callback синхронный, доверенный, использует переданный connection без network/commit/rollback. Actor/resource определяет сервер по проверенному событию. Guard работает внутри транзакции до effect и возврата receipt, включая replay после отзыва прав. Внешний ACL-сервис не становится атомарным с SQLite автоматически.

`schedule(..., actor_id, now=server_now)` дает coherent snapshot. `reserve(..., expected_revision, operation_id, now=server_now)` под `BEGIN IMMEDIATE` повторно проверяет revision, enabled, будущее время, занятость key и пересечение активного интервала ресурса, затем сохраняет booking и receipt одной транзакцией. Два процесса с общим файлом не создают две записи; overlapping aliases тоже отвергаются. Соседние интервалы и разные ресурсы независимы. Capacity — одно место на ресурсный интервал; holds/waitlist требуют отдельного контракта.

Operation ID scoped по resource/actor. Тот же payload возвращает `OnceResult(replayed=True)`, другой — `OperationConflict`; server clock не входит в idempotency payload. Receipt неизменяемо описывает исходный результат, включая после cancel. Для текущего состояния используйте owner-guarded `booking`; `cancel` освобождает интервал и сохраняет отдельный receipt. Retention, файл, миграции, backup и ошибки SQLite принадлежат host. Здесь нет внешних effects и обещания exactly-once доставки Telegram.

## Самодостаточный public API пример

Настоящий временный SQLite-файл, явная fixture ACL, DST, unavailable date и markup. Этот пример не запускает Telegram и не предоставляет production identity. В существующем боте сохраните Dispatcher/SDK/storage; полный workflow подключается Router из предоставленного рецепта.

```python
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from telegram_patterns import CalendarMonth, TimeSlot, resolve_local_time, SQLiteSlotStore
from telegram_patterns.aiogram import calendar_keyboard, time_slot_keyboard

early = resolve_local_time(datetime(2026, 10, 25, 2, 30), 'Europe/Warsaw', fold=0)
late = resolve_local_time(datetime(2026, 10, 25, 2, 30), 'Europe/Warsaw', fold=1)
assert late - early == timedelta(hours=1)
slot = TimeSlot('early', early, early + timedelta(minutes=15))
month = CalendarMonth(2026, 10, 'Europe/Warsaw',
                      [date(2026, 10, 25), date(2026, 10, 26)], [date(2026, 10, 26)])
calendar_markup = calendar_keyboard(month, lambda day: 'date:' + day.isoformat())
time_markup = time_slot_keyboard([slot], 'Europe/Warsaw', lambda item: 'time:' + item.key)
with TemporaryDirectory(prefix='calendar guide ') as temporary:
    store = SQLiteSlotStore(Path(temporary) / 'slots.sqlite3',
        authorize=lambda connection, actor, resource: actor == 42 and resource == 'room')
    store.initialize()
    schedule = store.publish('room', [slot], expected_revision=0)
    now = datetime(2026, 10, 5, tzinfo=timezone.utc)
    receipt = store.reserve('room', 'early', actor_id=42, expected_revision=schedule.revision,
                            operation_id='booking-42-1', now=now)
    replay = store.reserve('room', 'early', actor_id=42, expected_revision=schedule.revision,
                           operation_id='booking-42-1', now=now)
    assert replay.replayed and replay.value == receipt.value
    booking = store.booking('room', receipt.value['booking_id'], actor_id=42)
    assert booking is not None and booking.status == 'active'
```

Короткие callback strings выше — fixture labels. В проекте связывайте действие с владельцем, ботом, чатом, темой, сообщением, сессией и ревизией; дата не является полномочием. Full пример использует `SelectionMenu`/`selection_router(render=...)`, свежий server spec после ACK и отдельную бизнес-транзакцию. Чужой callback не загружает расписание; старое подтверждение не резервирует слот.

## UI и жизненный цикл

Default `calendar_keyboard` показывает доступные даты с weekday labels; недоступные не имеют callback. `disabled_buttons=True` дает native сетку с `DisabledButton` для header/empty/unavailable cells и требует явного host-подтверждения поддержки. Эти кнопки не создают callback events. `navigation=(previous_callback,next_callback)` только строит кнопки — месяц меняет контроллер. `time_slot_keyboard` скрывает disabled интервалы; native callback budget — 64 UTF-8 bytes. Component limit — 100 uniquely keyed slots; full пример ограничен 60 слотами на дату и 100 ordinary-private sessions, не обрезает расписание молча.

Optional synchronous `selection_router(render=...)` возвращает `(plain_text, InlineKeyboardMarkup)` после host hook. ACK/guards/revision сохраняются; invalid output не откатывает принятый intent. Renderer не заменяет business authorization. Hook/edit ошибка не разрешает новый operation ID или автоматический повтор записи.

В примере `/book` сохраняет текущий выбор при explicit recovery и сверяет незавершенный intent тем же ID. После успеха `/book` показывает текущий booking status, `/book new` явно начинает новый выбор. Начальная отправка не повторяется автоматически; известное сообщение редактируется. Выбор и сессия временные, бронирование и квитанция хранятся надежно. Для восстановления интерфейса после process restart host сохраняет связь пользователя с booking/operation отдельно.

Из async handler используйте owned thread work и дождитесь завершения при cancellation/shutdown до освобождения lock/ресурсов. Отмена ожидания не доказывает отсутствие commit. Примерный `database_call` join-ит работу перед возвратом cancellation; explicit запрос сверяет тот же intent. SQLite схема не является универсальным storage-контрактом для других БД и не требует миграции существующего проекта.

## Проверка и источники

Тесты ядра: пропущенный и повторенный час при переводе часов в Варшаве, переход на полчаса на острове Лорд-Хау, пропущенная дата в Апиа, високосный месяц, точность UTC, проверка текущих прав перед повтором, CAS и гонки отдельных процессов за один слот, пересекающиеся псевдонимы и одно и то же намерение. Тесты с SDK: выбор даты, времени и возврат, недоступная дата, чужой и устаревший callback, изменение расписания, квитанция после рестарта и потерянное редактирование после фиксации бронирования. Отключенные кнопки клиента и запасной вариант проверяются отдельно. Установленные артефакты доказывают публичные импорты и сборку компонентов; отображение в живом Telegram, физические устройства и надежное хранение меню остаются неподтвержденными.

Проверено 5 октября 2026 года: [Python 3.13 zoneinfo](https://docs.python.org/3.13/library/zoneinfo.html), [datetime](https://docs.python.org/3/library/datetime.html), [SQLite transactions](https://www.sqlite.org/lang_transaction.html), [tzdata](https://pypi.org/project/tzdata/), [InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton), [aiogram 3.31.0 DisabledButton](https://docs.aiogram.dev/en/v3.31.0/api/types/disabled_button.html). Scope — указанные time/transaction/markup контракты; остальные даты каталога Telegram не обновлялись.
