---
name: telegram-mini-app-typescript
description: "Разрабатывает TypeScript-код Telegram Mini App: bridge или SDK, типизированный API-клиент, конфигурацию и сборку. Используй для подключения Telegram и инфраструктуры frontend, отдельно от визуального дизайна. Не для визуального оформления → telegram-mini-app-ui."
license: MIT
metadata:
  version: "0.24.0"
---

# Mini App на TypeScript

Проверь package manifest, lockfile, tsconfig, модульный формат и используемый frontend-framework. Сохраняй существующий SDK или native bridge, если они подходят задаче. Для нового проекта выбирай минимальный TypeScript starter; React не обязателен.

При подключении Telegram или смене SDK прочитай [references/bridge.md](references/bridge.md). Не смешивай методы разных SDK и нативного bridge по похожим именам.

## Типы и границы

Опиши небольшой Telegram adapter: получение launch context, проверка capability, readiness и подписки на нужные события. Используй типы установленного SDK. Если нужны собственные declarations, описывай только проверенные поля; не маскируй доступность API через `any` или non-null assertion.

Держи доступ к Telegram API на границе приложения; прикладная логика не должна читать глобальный `window.Telegram` в каждом компоненте. В режиме браузерного превью adapter может предоставить явно выбранный mock, который не проходит как авторизация production backend.

Для Python backend определи HTTP-контракты запросов и ответов. Если проект уже использует OpenAPI, переиспользуй схему и установленный генератор; иначе хватит малого API-клиента. TypeScript-типы не проверяют сетевой JSON во время выполнения: валидируй недоверенные ответы на границе по потребности.

## Конфигурация и lifecycle

Разделяй публичные frontend-настройки и серверные секреты. Для Vite `VITE_*` попадает в клиентскую сборку: bot token и ключи доступа там недопустимы. Проверяй обязательный API URL и режим запуска при старте.

Учитывай отмену запросов при закрытии экрана, stale responses и повторное создание подписок. Для SSR не обращайся к browser globals на сервере. Изменение процесса входа реализуй вместе с серверной проверкой initData, а не с локальным user_id.

Разделяй загруженный bridge и подтвержденный запуск/сессию: наличие window.Telegram само по себе не означает вход через Telegram. Настрой явные режимы Telegram, dev preview и предусмотренное состояние вне Telegram. Query-параметр demo не должен включать mock auth в production. Смена launch context или личности сбрасывает связанные cache и старые запросы.

## Проверка

Запусти отдельный typecheck и production build командами проекта; сборщик не всегда проверяет типы. Проверь, что production-сборка использует нужный API URL, не включает mock auth и не содержит серверной конфигурации. После этого проверь один основной сценарий внутри Telegram; отдельно укажи результаты браузерного превью.

## Источники

[Telegram Mini Apps](https://core.telegram.org/bots/webapps), [TypeScript strict](https://www.typescriptlang.org/tsconfig/strict.html), [Vite env](https://vite.dev/guide/env-and-mode). Для SDK используй официальную документацию его установленной версии.

Проверено: 2026-10-07, Telegram Mini Apps (Bot API 10.3).
