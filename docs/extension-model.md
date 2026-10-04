# Пользовательские адаптеры — 0.9.0

Пункт 008. Core остается stdlib-only; интерфейсы не устанавливают SDK, базу, web framework или платежный сервис. Python использует структурные `Protocol`, TypeScript — interfaces/type aliases. Классу проекта достаточно иметь правильные методы; наследование и global registry не нужны. Type checking проверяет сигнатуры, а поведенческий consumer — операции. Интерфейс не доказывает атомарность, авторизацию или надежность стороннего сервиса.

## Python core

Публичные импорты — `OnceStore`, `AsyncTransport`, `ProviderAdapter`, `RefundProvider` из `telegram_patterns`. Методы протоколов описывают контракт, не имеют исполняемой реализации и не открывают ресурсы. Они не предназначены для `isinstance` проверки внешнего объекта.

| Протокол | Сигнатуры и результат | Обязанности адаптера |
| --- | --- | --- |
| `OnceStore[Transaction]` | `initialize()->None`; `run(scope:str,operation_key:str,payload:Any,apply:Callable[[Transaction],Any])->OnceResult` | Effect и JSON-совместимый replay result атомарны в одной storage transaction; конфликт payload дает OperationConflict; исключение до commit откатывает локальный effect. Инициализация явная, может делегировать миграциям host |
| `AsyncTransport[Request,Response]` | `async send(request:Request)->Response` | Точные модели запросов/ответов выбранного стека. Не добавлять скрытый retry записи; описать реальные wire retries SDK/proxy, отмену и timeout. Не поглощать неизвестный результат |
| `ProviderAdapter[CreateRequest,Snapshot,Event]` | `async create(request,*,operation_id:str)->Snapshot`; `async get(provider_id:str)->Snapshot`; `verify_event(body:bytes,headers:Mapping[str,str])->Event\|None` | Create/get могут выполнять I/O. Verify делает локальную provider-specific аутентификацию и разбор raw bytes; None означает отклоненное событие. Возвращенный event не является платежом или разрешением доступа |
| `RefundProvider[RefundRequest,Snapshot]` | `async refund(request,*,operation_id:str)->Snapshot` | Отдельная необязательная возможность. Не требовать refund от провайдера, который его не поддерживает; его idempotency и outcome проверяются отдельно |

Transaction/Response/Event covariant, Request contravariant; это позволяет использовать точные модели проекта. `SQLiteOnce` структурно соответствует `OnceStore[sqlite3.Connection]`; другая БД предоставляет свой Transaction и свою миграцию. Асинхронный storage имеет другую модель: не выдавай async DB API за синхронный `run`. В async backend синхронную работу запускают через подходящий thread boundary приложения; текущий контракт не добавляет blocking DB в event loop сам.

Авторизацию проверяет сервис до нового effect и до replay. Scope/operation_id задаются доверенным сервером, а не callback payload. Уникальность ключа, неизменность запроса, account/tenant namespace и retention — часть контракта приложения/адаптера. Protocol не обещает, что любой provider поддерживает повтор create с тем же ключом: если это не подтверждено его документацией, используй поиск/статус по собственной связи с заказом. При неизвестном результате сохраняй исходную identity и [сверяй операцию](error-model.md).

Provider snapshot/event остаются типами конкретного SDK/проекта; интерфейс не выдумывает общий currency/status model. Authenticate event по фактическому wire-контракту провайдера; учитывай raw body, headers/доверенный transport context и пределы размера. Сопоставь merchant/order/amount/currency на сервере и проверь авторитетный статус там, где это необходимо. Только после ledger transition сервис решает о выдаче. Никаких общих «подписей Telegram» для Crypto Pay/Platega/ЮКассы из этого интерфейса не следует.

Переданный transport/SDK session принадлежит host; он закрывает его в своем lifecycle. Адаптер, который сам открывает ресурс, документирует собственный context manager/close вне общего протокола. Аннотация протокола не закрывает и не переинициализирует существующую session. Внешние эффекты не становятся частью SQLite transaction.

## TypeScript

Root экспортирует `KeyValueStorage`, `StorageFactory`, `FetchTransport`. `KeyValueStorage` содержит синхронные `getItem(key:string):string|null`, `setItem(key:string,value:string):void`, `removeItem(key:string):void`. `StorageFactory=()=>KeyValueStorage` передается прежнему `SelectionDraftStore`; browser localStorage и прежний Pick<Storage,...> совместимы. Native CloudStorage async callbacks не соответствуют этому протоколу и не должны маскироваться через cast.

`FetchTransport=(input:RequestInfo|URL,init?:RequestInit)=>Promise<Response>` передается в `ClientOptions.fetch`. Это прежняя Fetch-compatible граница с именованным типом, без смены ApiClient.request или его decoder. ApiClient делает один вызов transport, owns свой AbortController и listeners; адаптер обязан уважать signal и не скрывать опасные повторы. Host владеет session/пулом/кешем собственного транспорта. Клиент не закрывает его и не хранит token.

SelectionDraftStore использует только собственный namespaced key: custom storage не очищается целиком. Scope разделяет выбор разных пользователей, не подтверждает серверные права. Его bool/status API сохраняется, включая unavailable/corrupt/quota; новая typing граница не заменяет серверную проверку.

## Рабочий пример и миграция

[custom_adapters.py](../examples/python/custom_adapters.py) запускается без SDK, токена и сети. Собственный ProjectStore делегирует реальной SQLite transaction и подтверждает один effect при replay. ProjectTransport/FixtureProvider моделируют сохранение до потери ответа, явную сверку той же операции, конфликт payload и tampered webhook. Учебный HMAC не является контрактом реальной платежки. Даже корректно подписанный fixture event с полем paid не выдает доступ: server snapshot остается pending.

Ранее существующий API не переименован. Можно оставить текущие импорты и переданные storage/fetch; новые протоколы позволяют добавить статическую аннотацию и проверять адаптер отдельно. TypeScript декларации используют публичные имена вместо private StorageLike; structural assignability сохранена. Python host может аннотировать `store: OnceStore[sqlite3.Connection] = SQLiteOnce(path)` без wrapper.

Проверка поставки копирует runnable пример за пределы дерева репозитория, запускает его с installed core wheel без aiogram и проверяет Mypy против установленного wheel. Tarball consumer проверяет собственный storage/Fetch transport, типы, account isolation и сохранность чужого storage key. Реальные provider integrations, async durable FSM, HTTP delivery и device acceptance остаются отдельными задачами, а не доказанными свойствами этих интерфейсов.
