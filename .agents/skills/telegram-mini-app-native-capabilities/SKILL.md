---
name: telegram-mini-app-native-capabilities
description: "Подключает конкретные native-возможности Telegram Mini App: геолокацию, биометрию, QR, хранилища, sharing и скачивание. Используй для client API с разрешениями, version gates и fallback, отдельно от общего подключения bridge. Не для общего подключения bridge и SDK → telegram-mini-app-typescript."
license: MIT
metadata:
  version: "0.24.0"
---

# Native-возможности Mini App

Определи нужный пользовательский сценарий, установленный SDK/bridge и целевые клиенты. Подключай только требуемую capability. Сверь точное имя, версию, callback/events и ограничения с текущей официальной документацией и API установленного SDK.

## Контракт адаптера

Для различий capabilities прочитай [references/capabilities.md](references/capabilities.md). Проверяй version gate и фактическую доступность метода/объекта; platform и наличие window.Telegram не доказывают поддержку. Подписки, состояние и cleanup принадлежат одному adapter.

Опиши состояния unavailable, idle, pending, accepted/result, denied/cancelled и error в форме, подходящей конкретному API. Не своди отказ пользователя и отсутствие функции к success. Переход в настройки/запрос выполняется по осмысленному действию пользователя там, где API этого требует.

## Результат и fallback

После async callback проверь, что экран/запрос и пользовательский контекст еще актуальны. Не применяй результат старого запроса к новой форме. Сверь ограничения повторного вызова и порядок init; не вызывай запрос permission в бесконечном цикле.

Предусмотри полезную альтернативу: ручной выбор адреса, стандартное поле ввода, доступную ссылку или объяснение. Fallback не должен незаметно менять контракт доверия и отправлять чувствительные данные в менее защищенное хранилище.

Серверные права и auth остаются серверными: геолокация, QR, biometric callback и local storage не доказывают личность или доступ к объекту. Ключи бота/провайдера не передаются клиенту даже для SecureStorage.

## Проверка

Через fake adapter проверь unsupported, отказ, отмену, ошибку, success, повторный вызов и поздний callback после ухода. Затем проверь фактическое поведение нужного API в целевом Telegram-клиенте с разрешенной тестовой операцией. Запиши отдельно mock и native evidence, версии и непроверенные клиенты.

## Источники

[Telegram client API](https://core.telegram.org/bots/webapps#initializing-mini-apps), [events](https://core.telegram.org/bots/webapps#events-available-for-mini-apps).

Проверено: 2026-10-07, Telegram Mini Apps (Bot API 10.3).
