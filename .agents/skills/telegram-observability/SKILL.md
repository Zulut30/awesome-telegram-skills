---
name: telegram-observability
description: "Добавляет наблюдаемость Telegram-бота и Mini App: связанные frontend/backend/worker события, метрики и безопасные логи. Используй для внедрения instrumentation и мониторинга; конкретный текущий сбой относится к debugging."
license: MIT
---

# Наблюдаемость

Изучи существующие logger, error collector и мониторинг. Начни с основного пути и вопроса, на который должны отвечать данные: потерянный update, медленный заказ, payment reconciliation или ошибка интерфейса. Внешний SaaS и OpenTelemetry не обязательны для маленького проекта.

## Связанный путь

Для контекста, минимальных показателей и redaction прочитай [references/telemetry.md](references/telemetry.md). Свяжи запрос/операцию/worker с результатом, сохраняя контекст между async задачами корректно. Trace/request id из клиента недоверенный: валидируй формат и не используй его для auth/дедупликации бизнес-операции.

Отделяй frontend действие, HTTP response, durable acceptance и завершение операции. Лог перед вызовом не доказывает результат. Для UI ошибки полезны build/release, route template, capability и sanitized error category; для backend — duration и итог перехода.

## Данные и сигналы

Сохраняй нужные атрибуты по allowlist. Скрывай token в Telegram URL, initData, Authorization/Cookie, provider credentials, signatures и личный payload до передачи sink; проверь URL query/path, nested fields и exception strings. Sampling и последующая очистка dashboard не защищают уже отправленный секрет.

Выбирай метрики с ограниченным числом значений: статус, route template, операция, категория ошибки. user_id, order_id и полный URL не становятся metric labels. Ошибка коллектора не должна блокировать заказ или порождать бесконечную очередь telemetry.

## Проверка

В изолированной среде пройди success, управляемую ошибку и две конкурентные операции. Проверь связность событий, отсутствие утечки контекста, redaction тестовых canaries и поведение при недоступном sink. Тестируй реально сериализованный output, а не только вызов logger.

Дай схему событий, измерения, место просмотра и условие полезного alert. Не устанавливай monitoring сервис и не отправляй реальные данные во внешний аккаунт без задачи на эту интеграцию. Укажи проверенный sink и ограничения покрытия.

Источники: [OpenTelemetry sensitive data](https://opentelemetry.io/docs/security/handling-sensitive-data/), [Python contextvars](https://docs.python.org/3/library/contextvars.html), [Bot API](https://core.telegram.org/bots/api).
