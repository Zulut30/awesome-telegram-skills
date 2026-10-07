# Расширение библиотеки

Доступно с 0.9.0, проверено на 0.24.0.

Сохраняйте SDK, базу, framework и lifecycle проекта. Core использует стандартную библиотеку; интеграция по структурному интерфейсу не требует переписывать существующие классы.

Python root: `OnceStore[Transaction]` с initialize/run и существующим OnceResult; `AsyncTransport[Request,Response]` с async send; `ProviderAdapter[CreateRequest,Snapshot,Event]` с async create(request,operation_id=...), async get(provider_id) и локальным verify_event(raw_body,headers)->Event|None; отдельный `RefundProvider` с async refund. Наследование не обязательно; Protocol не проверяет runtime atomicity. SQLiteOnce уже соответствует OnceStore[sqlite3.Connection]. Async storage не выдается за sync run.

TypeScript root: `KeyValueStorage` с sync getItem/setItem/removeItem, `StorageFactory` и `FetchTransport` с сигнатурой fetch. Передавайте их прежним SelectionDraftStore и ClientOptions.fetch. Не превращайте native CloudStorage callbacks в синхронный storage через cast. Оставьте session/pool cleanup у их владельца; библиотека owns лишь свои listeners/AbortController.

Проверьте пользовательский адаптер через установленный wheel/tarball и типы. Для storage проверьте effect+replay, rollback, конфликт payload и account isolation. Для транспорта — потерянный ответ после эффекта без скрытого повтора; для provider — tampered event, привязку к merchant/order и авторитетный статус. Сверка same-key create допустима только по контракту конкретного провайдера. Учебный fixture или успешно подписанный callback не подтверждает оплату и не выдает entitlement.

Scope/operation_id и ACL принадлежат серверу; проверяйте права до effect и replay. При unknown outcome следуйте локальному [контракту ошибок](errors.md). Не добавляйте обязательный Redis/Postgres или смену SDK ради протокола. Для настоящей платежки нужны актуальные официальные docs ее методов/подписей и отдельный sandbox, а не общий придуманный signing helper.
