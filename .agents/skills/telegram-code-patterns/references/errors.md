# Ошибки библиотеки 0.8.0

Подключай `safe_error_report` из Python core или `safeErrorReport` из TypeScript root. Они возвращают пять безопасных полей: code, category, outcome, recovery, message. Вход — исключение; внешнее JSON тело не является доверенным доказательством результата. Developer message/stack не выводи в чат или обычный лог.

```python
from telegram_patterns import ValidationFailure, safe_error_report

invalid = safe_error_report(ValidationFailure('private input'), operation='write')
assert (invalid.category, invalid.outcome, invalid.recovery) == ('validation', 'rejected', 'fix-input')
lost = safe_error_report(TimeoutError('private endpoint'), operation='write')
assert (lost.outcome, lost.recovery) == ('unknown', 'reconcile')
assert 'private' not in str(lost.as_dict())
assert safe_error_report(TimeoutError(), operation='read').recovery == 'retry-read'
```

`ValidationFailure` — известная проверка до эффекта; `PermissionDenied` — проверенный host ACL отказ; `UnsupportedCapability` — недоступная функция; `UnknownOutcome` — неизвестный результат. `InvalidInitData`/`InvalidAPIRequest`/`InvalidField` сохраняют ValueError catches, `OperationConflict` требует сверки прежней операции. TS `ApiError` сохраняет kind/status/outcome, `UnsupportedTelegramCapability` дает use-fallback. Не считай HTTP 403/422 после POST доказательством отсутствия записи; ApiClient сохраняет unknown и не повторяет запрос автоматически.

Укажи реальный вид операции. Для read возможен retry-read; для неизвестного write всегда reconcile. Сохраняй тот же operation_id, payload и проверенный сервером scope; запрос статуса/replay проходит ACL. Новая кнопка/новый ключ не восстанавливает старый платеж. Отмена ожидания не отменяет серверный effect. `InvalidCompletion` после on_submit формы сохраняет pending identity; повторная сверка принадлежит сервису. Core не навязывает storage/SDK и не отправляет HTTP при классификации.

Не заменяй все ошибки SDK/сервиса локальной ValidationFailure: некорректный ответ после effect имеет unknown outcome. Для UI оставь введенные значения, покажи безопасное сообщение и действие проверки статуса. В framework проекта используй существующую обработку ошибок и lifecycle. Проверь хотя бы lost response после сохранения и повтор той же операции без второго effect; браузерная проверка не доказывает live Telegram.
