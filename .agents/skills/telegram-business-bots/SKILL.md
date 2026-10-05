---
name: telegram-business-bots
description: "Интегрирует Telegram Business/Secretary Bot с разрешенными чатами аккаунта: business_connection, сообщения, rights и ответы от имени владельца. Используй для официального подключения бота к аккаунту."
---

# Business и Secretary Bots

Проверь текущую возможность подключения в BotFather, права и условия для конкретного аккаунта. Прочитай [официальное описание](https://core.telegram.org/bots/features#business-bots) и типы [BusinessConnection](https://core.telegram.org/bots/api#businessconnection), [BusinessBotRights](https://core.telegram.org/bots/api#businessbotrights). Не требуй Premium по устаревшему примеру без текущей проверки.

Обрабатывай создание, изменение и отзыв connection. Сохраняй последний статус и rights, изолируя состояние по владельцу и connection ID. Изменение доступных чатов должно применяться к последующим операциям и кешу.

Маршрутизируй `business_message`, `edited_business_message`, `deleted_business_messages` отдельно от обычных сообщений бота. Для ответов используй нужный `business_connection_id`. Перед действием проверь актуальную возможность: ответ, чтение, удаление, управление профилем и другие разрешения не взаимозаменяемы.

Ограничения recent incoming messages и eligible private chats сверяй по конкретной операции. Не выдавай connected-business доступ за право прочитать все группы, архив и историю пользовательского аккаунта. Для полной клиентской задачи оцени отдельно MTProto.

Защити от цикла автоответов, повторной доставки и смешения двух владельцев. При отзыве доступа отменяй будущие задания, которым он требуется. Логи должны содержать минимум контекста, не тексты приватной переписки.

Проверь два connection, отсутствие нужного right, отзыв доступа и duplicate update. Живой ответ от имени владельца выполняй только по авторизованному тестовому сценарию; сам навык не предоставляет доступ к аккаунту.

Для переиспользования Python-компонентов тем, реакций, заявок, Business, stories, gifts и managed bots прочитай [специальные операции](references/platform-operations.md). Выбери нужный метод из reviewed allowlist и сохрани текущий Bot/Dispatcher/storage. Current actor ACL и exact binding проверяются отдельно от fresh native right; перед write нужен durable host claim. Unknown outcome не повторяется; financial consent/quote/local budget не обещают atomic remote debit. Managed token передавай через явный secret sink, event не дает полномочий. SDK/mock не подтверждает live права или устройства.
