---
name: telegram-web-login
description: "Подключает Telegram Login к обычному сайту на TypeScript с Python backend: OIDC, проверку ID token и привязку аккаунта сервиса. Используй для входа вне Mini App; initData, legacy widget и авторизация MTProto имеют другие протоколы."
license: MIT
---

# Telegram Login для сайта

Определи текущую auth библиотеку, домены, callback и требуемые claims. Сохраняй выбранный framework; не внедряй identity broker без необходимости. Telegram Login не дает права читать пользовательские чаты и не является Mini App initData.

## Протокол

Для текущего OIDC и привязки прочитай [references/login.md](references/login.md). Используй поддерживаемую OIDC библиотеку либо официальный Telegram Login SDK согласно выбранному сценарию. Сервер проверяет ID token до доверия данным; декодированный callback user не является доказательством личности.

Client Secret и code exchange остаются в Python backend. Allowed URLs и redirect URI должны соответствовать конфигурации приложения. В flow Authorization Code используй server-bound одноразовый state и PKCE S256; nonce привязывается к той же login transaction, когда он применяется. Срок и replay контролируются сервером.

Проверяй signature, разрешенный настроенный algorithm, issuer, audience, expiry и требуемые claims. Ключи берутся из доверенного Telegram JWKS; нельзя доверять адресу ключа из JWT. Повтор callback не создает вторую сессию/привязку. После входа используй защищенную сессию сервиса по его существующей модели.

## Аккаунт сервиса

Храни OIDC identity по `(issuer, sub)`; не принимай sub за Bot API user ID. Для связи с ботом проверяй доступный подписанный Telegram id и его контракт. Username, имя, фото и телефон не служат ключом автоматического объединения аккаунтов.

Привязка требует подтвержденной текущей сессии сервиса и проверенного Telegram входа. Конфликт с уже привязанной identity обрабатывается явно; уникальность хранится в БД. Отвязка не должна лишать пользователя последнего способа восстановить доступ без согласованного решения.

Запрашивай profile/phone/bot messaging scope только по потребности. Разрешение входа не подменяет отдельное разрешение на сообщения. Не журналируй code, ID token, verifier, секрет или полный payload.

## Проверка

Проверь signed token с неверными issuer/audience/algorithm, expiry, state/nonce mismatch, replay и конкурентную привязку к двум аккаунтам. JWT fixtures создавай локальными тестовыми ключами и явно отмечай, что они не подписаны Telegram.

Для реализации проверь backend и frontend сборку, отказ popup и ошибку callback. Реальный вход требует разрешенной test конфигурации BotFather; без нее опиши локальные проверки и оставшийся end-to-end шаг.

Источники: [Telegram Login](https://core.telegram.org/bots/telegram-login), [OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html).
