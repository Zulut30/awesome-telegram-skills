---
name: telegram-business-bots
description: "Интегрирует Telegram Business/Secretary Bot с разрешенными чатами аккаунта: business_connection, сообщения, rights и ответы от имени владельца. Используйте для официального подключения бота к аккаунту. Не для групп и каналов → telegram-groups; не для пользовательского аккаунта через MTProto → telegram-user-client."
license: MIT
metadata:
  version: "0.24.0"
---

# Business и Secretary Bots

Проверьте текущую возможность подключения в BotFather, права и условия для конкретного аккаунта. Прочитайте [официальное описание](https://core.telegram.org/bots/features#business-bots) и типы [BusinessConnection](https://core.telegram.org/bots/api#businessconnection), [BusinessBotRights](https://core.telegram.org/bots/api#businessbotrights). Не требуйте Premium по устаревшему примеру без текущей проверки.

Обрабатывайте создание, изменение и отзыв connection. Сохраняйте последний статус и rights, изолируя состояние по владельцу и connection ID. Изменение доступных чатов должно применяться к последующим операциям и кешу.

Маршрутизируйте `business_message`, `edited_business_message`, `deleted_business_messages` отдельно от обычных сообщений бота. Для ответов используйте нужный `business_connection_id`. Перед действием проверьте актуальную возможность: ответ, чтение, удаление, управление профилем и другие разрешения не взаимозаменяемы.

Ограничения recent incoming messages и eligible private chats сверяйте по конкретной операции. Не выдавайте connected-business доступ за право прочитать все группы, архив и историю пользовательского аккаунта. Для полной клиентской задачи оцените отдельно MTProto.

Защитите от цикла автоответов, повторной доставки и смешения двух владельцев. При отзыве доступа отменяйте будущие задания, которым он требуется. Логи должны содержать минимум контекста, не тексты приватной переписки.

Проверьте два connection, отсутствие нужного right, отзыв доступа и duplicate update. Живой ответ от имени владельца выполняйте только по авторизованному тестовому сценарию; сам навык не предоставляет доступ к аккаунту.

С библиотекой awesome-telegram-patterns, если она уже есть в проекте: [специальные операции](references/platform-operations.md) — Business, stories, gifts, managed bots.

## Источники

[Business-боты](https://core.telegram.org/bots/features#business-bots), [BusinessConnection](https://core.telegram.org/bots/api#businessconnection), [BusinessBotRights](https://core.telegram.org/bots/api#businessbotrights).

Проверено: 2026-10-07, Bot API 10.3, aiogram 3.31.0.
