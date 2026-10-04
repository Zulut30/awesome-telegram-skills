# Ошибки и восстановление — 0.8.0

Пункт 007. Python core и TypeScript используют одинаковые значения `ErrorCode`, `ErrorCategory`, `ErrorOutcome`, `RecoveryAction`, `OperationKind` и форму `ErrorReport`. Это experimental API. Классификация возвращает подсказку потребителю, сама не выполняет HTTP, retry, выдачу доступа или изменение состояния. [Offline-пример](../examples/python/error_recovery.py) показывает сохраненный заказ и потерю ответа после commit.

`safe_error_report(exception, operation='read')` и `safeErrorReport(error, operation='read')` принимают фактический вид операции: `read` или `write`. Для необработанной ошибки записи выбираются `outcome='unknown'` и `recovery='reconcile'`. Отмена ожидания, timeout, HTTP 403/422 и некорректный ответ после POST не подтверждают отсутствие эффекта. `read` допустим только для действительно безопасного чтения: GET-маршрут, который изменяет данные, не становится чтением из-за названия метода.

| Поле отчета | Контракт |
| --- | --- |
| `code: ErrorCode` | `validation-failed`, `invalid-init-data`, `invalid-api-request`, `invalid-field`, `authentication-required`, `permission-denied`, `unsupported-capability`, `timeout`, `network`, `operation-conflict`, `cancelled`, `internal`, `unknown-outcome`, `invalid-response` |
| `category: ErrorCategory` | `validation`, `permission`, `unsupported`, `timeout`, `network`, `conflict`, `cancelled`, `internal`, `unknown-outcome`; не заменяет outcome |
| `outcome: ErrorOutcome` | `rejected`: доказанное отклонение этой попытки до эффекта; `read-failed`: чтение не завершилось; `unknown`: эффект не подтвержден и не опровергнут |
| `recovery: RecoveryAction` | `fix-input`, `authenticate`, `check-permissions`, `use-fallback`, `retry-read`, `reconcile`, `none`; указание для приложения, не выполненная операция |
| `message: str/string` | Постоянный безопасный русский текст из каталога; локализацию выбирает host по code. Текст исключения, stack, URL, headers, token, response body и пользовательский payload сюда не копируются |

Python `ErrorReport` — frozen DTO; `.as_dict()` возвращает новую JSON-совместимую копию пяти полей. TypeScript factory возвращает frozen объект с readonly полями. Гарантия безопасного сообщения относится к результату нормализатора; вручную созданный DTO и внешнее JSON тело сами по себе ей не обладают. Python требует `BaseException`; TypeScript принимает `unknown`, но произвольный объект не признается доверенной ошибкой. Неизвестное поле/объект не может заявить, что запись точно отклонена.

## Исключения

| Python API | TypeScript API | Когда применять |
| --- | --- | --- |
| `PatternError(message)` с фиксированным code у подкласса; `.report(operation='read')` | `PatternError(code, outcome, developerMessage?)`; `.report()` | Общая прикладная ошибка. Код/исход задаются доверенным адаптером; произвольный server payload нельзя превратить в известное отклонение |
| `ValidationFailure(message)` | `ValidationFailure(message?)` | Локальная проверка до эффекта: validation / rejected / fix-input |
| `InvalidType(message)` | `InvalidType(message?)` | Ошибка типа аргумента до эффекта; сохраняет `TypeError` catch. В Python также наследует `ValidationFailure`/`ValueError`; в TypeScript наследует `TypeError`, поэтому общий нормализатор предпочтительнее единственного `instanceof PatternError` |
| `PermissionDenied(message)` | `PermissionDenied(message?)` | Host проверил ACL и отклонил попытку до эффекта: permission / rejected / check-permissions |
| `AuthenticationRequired(message)` | `AuthenticationRequired(message?)` | До эффекта требуется вход: permission / rejected / authenticate |
| `UnsupportedCapability(message)` | `UnsupportedCapability(message?)` | Функция не поддерживается окружением: unsupported / rejected / use-fallback |
| `TimeoutFailure(message)` | `ApiError('timeout', status, outcome)` либо `DOMException(...,'TimeoutError')` | Timeout: для чтения retry-read, для записи reconcile |
| `TransportFailure(message)` | `ApiError('network', status, outcome)` | Транспорт: результат зависит от вида операции |
| `ConflictFailure(message)`, существующий `OperationConflict` | `PatternError('operation-conflict','rejected',message?)` | Эта попытка конфликтует с существующим ключом; reconcile проверяет прежнюю операцию |
| `UnknownOutcome(message)` | `UnknownOutcome(message?)` | Всегда unknown / reconcile, даже если вызывающий передал read |
| `InvalidCompletion(message)` | `ApiError('invalid-response', status, 'unknown')` после записи | Эффект мог состояться до некорректного feedback/decoder; исправление формы и новая запись не считаются восстановлением |

Все Python-конструкторы выше принимают стандартные exception args; таблица показывает рекомендуемый один developer message. Они не владеют ресурсами и не выполняют I/O. Не печатай `str(error)`/stack в пользовательский ответ или обычный лог: developer message может содержать секрет. `InvalidField` сохраняет прежний bounded plain-text контракт для намеренно подготовленного сообщения пользователю; общий нормализатор возвращает постоянный текст без его содержимого.

`InvalidInitData`, `InvalidAPIRequest`, `InvalidField` теперь наследуют `ValidationFailure`; прежние `ValueError` catches работают. `OperationConflict` наследует `ConflictFailure` и остается `ValueError`. Собственные preflight `ValueError` и `TypeError` заменены на совместимые подклассы. SDK/SQLite/OSError/host callback exceptions не переписываются: их необработанный write outcome консервативно неизвестен. Даже `PermissionError` не означает доказанное отсутствие эффекта.

`ApiError(kind,status,outcome)` сохраняет прежние аргументы и поля kind/status/outcome, наследует `PatternError`. HTTP 401/403/400/422 различаются по code, но write outcome остается unknown; response body не разбирается для классификации. `UnsupportedTelegramCapability` сохраняет имя и конструктор, наследует `UnsupportedCapability`. Старые function/DTO imports не переименованы. Миграция состоит в использовании нормализатора вместо разбора message или одного `except ValueError` для выбора retry.

## Решение приложения

Для `fix-input` покажи ошибку и оставь ввод; для `authenticate` обнови серверный вход; для `check-permissions` проверь права; для `use-fallback` предложи альтернативный сценарий. `retry-read` разрешает предложить повтор безопасного чтения, но не вводит автоматический retry loop. `none` оставляет решение сервису/поддержке.

При `reconcile` сохрани immutable operation_id, исходные данные и server-derived scope. Проверь статус или replay той же операции через авторизованный endpoint. Не меняй ключ и не разрешай новую оплату/заявку только потому, что ответ потерян. `SQLiteOnce` покрывает effect и replay только в одной SQLite transaction; внешний платеж требует контракта провайдера и серверного ledger. Ошибка формы после `on_submit` не освобождает pending identity: пример и тест подтверждают повторную сверку той же заявки.

Нормализаторы используют только собственные metadata и не вызывают exception formatter или переопределенный `.report()`. Пользовательский подкласс с собственными свойствами остается доверенным кодом host; API не является sandbox для враждебных Python/JS objects. Серверный ErrorReport не подтверждает ACL, оплату или отсутствие эффекта без серверного контракта.

Проверка: негативные сценарии в Python/TypeScript, сохранение operation_id в synthetic Dispatcher, реальный HTTP/отмена ожидания, installed core offline reconciliation, типы установленного wheel/tarball и browser regression. Это не live Telegram/provider acceptance.
