# Контекст Telegram до подключения helper

Bot token, Mini App launch и business connection — разные identity/context. Generic request constructor и native supports не проверяют все права/launch условия. Host проверяет actor, chat, owner, ACL и актуальный connection до effect/replay. User-client history требует отдельной явно поставленной задачи и session; не запускайте MTProto login как fallback библиотеки.

`sendData` не универсальный канал: keyboard launch отличается от inline/menu/query_id и main/direct backend. Native presence/version не подтверждает launch или consent. Raw initData проверяется сервером; native callback/invoiceClosed не выдает доступ.

Business can_read_messages означает read-mark, не историю аккаунта. Проверьте is_enabled, rights и owner/connection/chat; отзыв доступа блокирует будущие операции. Общие typing/read/copy/URL-click events обычный Update не предоставляет. Bot-to-bot/guest имеют новые специальные контексты: не применяйте старый абсолютный запрет другим ботам и немемберам; нужны settings/rights и loop bounds. SDK construction только локальная проверка.

Источники, проверенные для этих положений 2026-10-04: [Bot API](https://core.telegram.org/bots/api), [Mini Apps](https://core.telegram.org/bots/webapps), [Bot Features](https://core.telegram.org/bots/features), [user authorization](https://core.telegram.org/api/auth), [user history](https://core.telegram.org/method/messages.getHistory). При изменении поведения сверяйте конкретный метод и SDK. Предлагаемые решения остаются обязанностями host, а копирование навыка не требует соседних файлов.
