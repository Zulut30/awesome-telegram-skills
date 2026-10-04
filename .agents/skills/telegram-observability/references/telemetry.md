# Контекст и безопасные события

## События и измерения

| Граница | Полезное наблюдение |
| --- | --- |
| Bot transport | Тип update, reliable acceptance, processing outcome, retry/dedup и backlog age |
| HTTP | Проверенный request/trace id, route template, статус и duration |
| Прикладная операция | Operation id при необходимости, переход и durable outcome; разделение confirmed/unknown |
| Worker/payment | Claim, attempt, provider category, завершение/reconciliation; бизнес-результат отдельно от доставки |
| Mini App | Release, экран/действие, client capability, sanitized ошибка и доступные performance metrics |

Разделяй correlation id, idempotency key и подтвержденную личность. В trace контекст можно передавать ссылку на operation id по правилам хранения данных; в labels метрик вместо индивидуального id нужна конечная категория. Полный path с идентификатором заменяй route template.

Для Python ContextVar установка/сброс выполняются на границе владельца, reset token — в finally. asyncio task наследует контекст при создании: долгоживущий worker должен создавать подходящий контекст для каждого job, а не продолжать request context после завершения запроса. Глобальный mutable dict приводит к смешиванию параллельных пользователей.

## Redaction до sink

Allowlist полей надежнее записи raw request и последующего удаления. Проверяй входные headers/body, URL, logger args, сериализатор исключений и сторонний HTTP logger. Из URL Bot API скрывается токен в path, не только query. InitData и подписи не нужны для доказательства failure.

Используй в тестах узнаваемые искусственные canaries: raw и percent-encoded URL token, signed initData, Cookie/Authorization, nested credential и exception message. Ни один canary не появляется в конечном сериализованном output. Не печатай реальные секреты для демонстрации redaction.

Клиентские error events ограничены размером/частотой и схемой. Обработай telemetry endpoint как недоверенный ввод; пользовательский текст не становится произвольным именем метрики или HTML. Source maps связываются с release и доступом проекта, а не публикуются ради отчета автоматически.

## Операционная полезность

Минимальные показатели выбираются по критичному пути: failure rate, latency, due/backlog age, unknown outcomes. Alert имеет окно/порог, действие и владельца; отсутствие данных отличается от нуля ошибок. Сначала проверь сигнал управляемым failure в test среде.

При недоступном sink используй bounded queue/drop policy, backoff и ограниченную диагностику без рекурсивного логирования ошибки logger. Сохранение работы пользователя важнее бесконечной доставки telemetry. Retention и доступ к журналам соответствуют данным продукта.

Источники: [OpenTelemetry handling sensitive data](https://opentelemetry.io/docs/security/handling-sensitive-data/), [contextvars и asyncio](https://docs.python.org/3/library/contextvars.html).
