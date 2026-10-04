# Границы Telegram API

Пункт 010. Выбор маршрута определяется задачей, действующим подключением и правами. Наличие метода в SDK, construction рецепта или UI-функции не подтверждает доступ к данным либо успешный effect. Библиотека не превращает Bot token, initData или business_connection_id в пользовательскую session автоматически.

| Поверхность | Identity и область | Обязанность проекта |
| --- | --- | --- |
| Bot API | Bot token; доставленные updates и разрешенные методы | Chat/actor/owner binding, ACL, update subscription, replay/effect и актуальные контекстные ограничения |
| Mini App | Frontend/native facade; серверная identity после проверки raw initData | Launch context, backend session/ACL, поддержка клиента, согласие на конкретное действие и обработка результата |
| Business/Secretary bot | Делегированное подключение владельца с rights и выбранными чатами | Connection lifecycle, актуальные права, изоляция владельцев, отзыв доступа и предотвращение циклов |
| MTProto user client | Отдельная user authorization/session | Явная клиентская задача, allowlist/глубина истории, checkpoint, retention, защита session и сохранение privacy scope |

Для чтения истории выбранных чатов пользовательского аккаунта ставится отдельная задача user-client. Bot- или Business-сценарий не запускает login, сбор контактов, join/send/read-mark или экспорт всех dialogs как скрытый fallback. Авторизация клиента описана в [User Authorization](https://core.telegram.org/api/auth); [messages.getHistory](https://core.telegram.org/method/messages.getHistory) относится к user methods и доступному peer. Это не универсальный обход чужих прав.

## Выбор и права

Для обычных сообщений и администрирования используй Bot API. Реакции и chat_member требуют соответствующих rights и явной подписки allowed_updates; join requests — can_invite_users. Проверка SDK конструктора не проверяет эти права. [Update](https://core.telegram.org/bots/api#update).

Business: проверь is_enabled, owner/connection/chat и конкретный right. `can_read_messages` означает отметку входящего сообщения прочитанным, не выгрузку истории; `readBusinessMessage` имеет контекстные ограничения. Не требуй Premium по старой инструкции. [BusinessBotRights](https://core.telegram.org/bots/api#businessbotrights), [Business Bot features](https://core.telegram.org/bots/features#business-bots). Поле rights может отсутствовать; отсутствие не дает разрешение. В aiogram 3.31.0 реальные поля проверяются через модель; документация setBusinessAccountName употребляет can_change_name, а rights модель — can_edit_name. Это расхождение источника отмечается, не исправляется выдуманным полем или автоматической выдачей прав.

Mini App: `sendData` — keyboard launch; inline/menu возвращают результат через доступный query_id/answerWebAppQuery; main/direct не становятся keyboard launch по наличию функции. Backend проверяет raw initData, не initDataUnsafe. Client callback, sharing/contact/biometric result или invoiceClosed не выдают серверные права/entitlement. [Mini Apps](https://core.telegram.org/bots/webapps). Собственный `TelegramNativeAPI.supports` проверяет presence/version/platform, а не все semantic launch/permission условия: это действующий контракт библиотеки, а не проверка ACL.

Для профиля выбирай доступные User/getChat данные. `getUserPersonalChatMessages` относится к чату, указанному в профиле, и не означает личную переписку/архив аккаунта. Premium пользователя не доказывает emoji entitlement владельца бота. [Profile chat method](https://core.telegram.org/bots/api#getuserpersonalchatmessages). Неполные/устаревшие данные описывай с их источником и неизвестностью; не превращай shared IDs в право управлять объектом.

## Какие события не обещаем

В обычном Bot API Update нет общего события user typing, user read receipt, URL button click или copy_text click. `sendChatAction` — действие бота; business read-mark — отдельная исходящая операция. Redirect analytics, если отдельно нужны проекту, не становятся Telegram callback или аутентификацией actor. Observer библиотеки видит только доставленные Update и не создает subscriptions, history или durable audit.

Нельзя применять старое обобщение «бот никогда не видит другого бота» или «не состоящий в чате бот никогда не получает сообщение». В актуальных [Bot Features](https://core.telegram.org/bots/features#bot-to-bot-communication) описаны bot-to-bot mode с контекстными настройками, mention/reply/group/private условиями и loop prevention. [Guest mode](https://core.telegram.org/bots/features#guest-bots) дает отдельный guest update/reply, а не историю, participants или дальнейшие updates без нового вызова. Старый FAQ расходится с этой частью Features и changelog; версионные правила проверяются по конкретной операции, не по общей формулировке FAQ.

Собственный сервис должен отдельно ограничить TTL/depth/replies, дедупликацию, concurrency и циклы bot-to-bot; SDK модели сами этого не делают. Штатный handler, который намеренно игнорирует is_bot, не расширяется автоматически ради нового режима.

## Проверка границ библиотеки

В [машиночитаемой матрице](../catalog/api-boundaries.json) перечислены четыре поверхности, контексты, checks и сценарии выбора. [SDK probe](../scripts/check_telegram_boundaries.py) исполняется offline с установленным wheel/aiogram 3.31.0: request construction, реальные Update/rights поля, отсутствие history fallback, guest/Business distinction. Проверка SDK не является live Telegram acceptance.

Сценарии из evaluation: «чтение групп пользователя» оставляет user-client отдельной задачей; «отслеживание действий» не придумывает typing/read/copy events; «Mini App из direct link» не использует sendData как универсальный канал; «бот-администратор» проверяет rights; «отзыв business connection» не дает отвечать по устаревшему кешу. Переносимый code-patterns reference содержит эти решения без зависимости от соседних skills. Независимый blind agent тест сюда не подмешивается.

Сверены 2026-10-04 только указанные положения Bot API, Mini Apps, Bot Features, MTProto auth/history и aiogram 3.31.0 models. Даты всего upstream каталога/skills не обновляются этим просмотром. Для нового version-specific права/launch условия заново проверяй первичный источник и установленный SDK.
