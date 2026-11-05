# Конкурентные локальные действия

`SQLiteOnce.run_guarded` связывает текущие права, проверку revision, бизнес-запись
и сохранённый результат в одной транзакции файловой SQLite. Повторное нажатие
или второй worker с тем же серверным operation ID возвращает прежний результат;
бизнес-запись повторно не выполняется. Обязательных сервисов или Telegram SDK нет.

```python
from telegram_patterns import SQLiteOnce

store = SQLiteOnce("project.sqlite")
store.initialize()  # либо эквивалентная миграция проекта
result = store.run_guarded(
    scope, operation_id, payload, apply,
    check=check,
)
```

## Что проверяет проект

`scope` выводится на сервере из подтверждённого контекста. Для кнопки пример
связывает bot ID, chat ID, actor ID, message ID и topic ID. `actor_id` из JSON
или callback data не подтверждает личность. Для inline-сообщений нужен отдельный
контракт с `inline_message_id`; пример рассчитан на сообщения в чатах.

Operation ID создаётся **один раз при подготовке действия**, сохраняется вместе
с неизменяемым намерением на сервере и остаётся тем же после timeout, повторной
доставки и перезапуска. Кнопка передаёт только этот непрозрачный ID. Генерация
нового UUID при каждом нажатии не защищает от дублей. `payload` описывает именно
это намерение: объект, ожидаемую revision, целевое значение. ID update/callback
сам по себе не объединяет два разных нажатия одной кнопки.

`check(connection, replayed)` вызывается после `BEGIN IMMEDIATE` и поиска receipt,
до выполнения `apply` **и до выдачи прежнего результата**. Он должен:

1. Найти намерение, проверить его привязку к actor и полному контексту.
2. Прочитать текущие права и ограничения объекта в этой же SQLite.
3. Для `replayed=False` проверить ожидаемую domain revision и допустимость перехода.
4. Для `replayed=True` разрешить выдачу прежнего receipt при текущих правах.
   Revision могла вырасти из-за самого успешного действия или последующих действий;
   это не причина повторять эффект или отвергать прежний успешный receipt.
5. Вернуть ровно `True`. Любое другое значение вызывает `PermissionDenied`.
   Проверка может явно поднять доменную ошибку, например `ConflictFailure` для
   устаревшего нового намерения.

Смена payload при занятом `(scope, operation_id)` вызывает `OperationConflict`,
после проверки текущего доступа. Новый operation ID с устаревшей revision должен
отклоняться доменной проверкой. Ledger не знает правил вашего объекта и сам
revision не сравнивает. Изменение ACL должно сериализоваться в той же базе;
внешний кеш прав не даёт этой транзакционной гарантии.

## Граница транзакции

`apply(connection)` синхронно выполняет только локальные SQL-изменения через
переданное соединение и возвращает JSON-совместимый receipt. Бизнес-изменения и
receipt фиксируются вместе; исключение либо несериализуемый результат откатывает
оба. Payload проверяется как строгий JSON до вызова callbacks. Scope и operation
ID — непустые строки до 256 UTF-8 байт каждая. Старые `run`, схема ledger и типы
ошибок сохранены; существующий `run` не получает новую проверку прав автоматически.

Оба callback должны быть обычными синхронными функциями. `async def`, async
callable, возвращённые awaitable и async generator отклоняются через `InvalidType`;
возвращённая coroutine закрывается. SQL authorizer разрешает в `check` только
чтение и запрещает изменения, DDL, PRAGMA, ATTACH и управление транзакцией.
В `apply` запрещены COMMIT/ROLLBACK и неявный commit через `executescript`;
локальные savepoints сохраняют прежний контракт `run`.

Callbacks — доверенный код проекта. Authorizer защищает от случайной SQL-записи,
но не изолирует Python: не отключайте его внутри callback, не вызывайте UDF с
побочными эффектами, не открывайте другие соединения и не меняйте файлы/сеть.
Держите транзакцию короткой. Второй writer ожидает до `timeout`; при исчерпании
SQLite может поднять `OperationalError` (busy/locked). Проект определяет bounded
retry с тем же operation ID или ответ «попробовать позже».

Для async backend вызовите всю синхронную операцию через модель исполнения
проекта, например `await asyncio.to_thread(service.execute, origin, operation_id)`.
Не передавайте SQLite connection между потоками. Отмена await не останавливает
уже запущенный поток: операция могла зафиксироваться. Последующая сверка использует
тот же ID и текущие права, а не создаёт новое намерение.

## Перезапуск и внешние вызовы

Если процесс остановлен до commit, SQLite откатывает локальные изменения и
receipt; тот же ID можно обработать заново. Если commit состоялся, но ответ
потерян, повтор с тем же ID читает receipt после текущей проверки прав.
Сохраняйте ledger и намерения достаточно долго для вашего окна повторной доставки;
удаление receipt или повторное использование ID снимает защиту от дублей.

Это гарантия одной локальной бизнес-записи в одной SQLite. HTTP/Bot API, платежи,
другая база, сетевой диск и несколько независимых файлов SQLite в неё не входят.
Не помещайте внешний вызов в `apply` и не объявляйте его exactly-once. Для него
нужны отдельно сохраняемые intent/outcome, состояние неизвестного результата и
сверка с провайдером; неопределённый исход не разрешает слепой повтор.

## Исполняемый пример и проверки

[offline_concurrent_actions.py](../examples/python/offline_concurrent_actions.py)
содержит проектный `CounterService`: durable server-owned intent, контекст
actor/bot/chat/message/topic, текущий ACL и revision. Два отдельных spawn-процесса
выполняют один ID. Пример проверяет одну запись, replay после нового экземпляра
сервиса, отказ чужому контексту, устаревшему намерению и отозванному actor.

После установки локального Python-пакета:

```sh
python examples/python/offline_concurrent_actions.py
python -m unittest discover -s packages/python/tests -p test_guarded_actions.py -v
```

Тесты `test_two_processes_same_key_commit_one_effect_and_replay_one_receipt` и
`test_two_processes_different_intents_same_revision_have_one_winner` используют
реальные процессы и файловую SQLite. `test_process_crash_before_commit_rolls_back_effect_and_receipt`
и `test_process_crash_after_commit_reconciles_the_same_operation_on_restart`
останавливают worker через `os._exit` до и после commit. Отдельно проверяются
отозванный ACL на replay, каждый origin ID, stale revision нового эффекта,
подмена payload, SQL-запись из check, transaction control, async callbacks и
rollback. `test_waiting_process_checks_acl_after_the_prior_writer_revokes_access`
проверяет отказ worker после транзакционного отзыва доступа другим writer.
Пять process-тестов помечены integration и пропускаются при
`TELEGRAM_PATTERNS_TESTS=unit`. Это локальная проверка; она не доказывает работу
внешнего провайдера или устойчивость к потере питания конкретного диска.

## Источники

Проверено 2026-11-05 для контракта Python 3.11+:
[SQLite transactions](https://www.sqlite.org/lang_transaction.html),
[Python sqlite3 authorizer](https://docs.python.org/3.11/library/sqlite3.html#sqlite3.Connection.set_authorizer).
