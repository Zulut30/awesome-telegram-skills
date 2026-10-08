# Карта возможностей Bot API

Индекс [api-index.json](api-index.json) получен напрямую из [официальной страницы](https://core.telegram.org/bots/api) 2 октября 2026 года. Снимок Bot API 10.3 содержит 185 методов и 400 типов с именами параметров/полей. Это навигация по схеме, а не 185 испытанных реализаций.

| Область | Поиск по индексу |
| --- | --- |
| Сообщения и media | sendMessage, sendPhoto, sendVideo, sendMediaGroup, sendLivePhoto |
| Rich messages и streaming drafts | sendRichMessage, sendMessageDraft, sendRichMessageDraft, RichBlock |
| Кнопки и клавиатуры | InlineKeyboardButton, KeyboardButton, style, icon_custom_emoji_id, DisabledButton |
| Форматирование и custom emoji | MessageEntity, RichTextCustomEmoji, getCustomEmojiStickers |
| Профиль пользователя и бота | getUserProfilePhotos, getUserProfileAudios, getChat, getUserPersonalChatMessages, setMyProfilePhoto |
| Группы, каналы и участники | ChatPermissions, banChatMember, getChatMember, chat_join_request |
| Темы, direct messages, communities | ForumTopic, DirectMessagesTopic, Community |
| Опросы, quizzes, реакции | sendPoll, PollMedia, setMessageReaction, deleteMessageReaction |
| Inline, guest и WebApp queries | answerInlineQuery, answerGuestQuery, answerWebAppQuery |
| Business/Secretary | BusinessConnection, BusinessBotRights, business_connection_id |
| Stories | postStory, editStory, repostStory, deleteStory |
| Gifts и Premium | sendGift, getAvailableGifts, getUserGifts, giftPremiumSubscription |
| Stars, subscriptions и paid media | sendInvoice, createInvoiceLink, BotSubscriptionUpdated, sendPaidMedia |
| Managed bots | getManagedBotToken, replaceManagedBotToken, BotAccessSettings |
| Доставка и локальный API server | getUpdates, setWebhook, getWebhookInfo, logOut |

Для каждой функции проверьте: caller/context, нужные права, поддержку SDK/client, доступность optional-полей и возможные повторные эффекты. Получение личного канала из профиля не равно чтению личной переписки. Подключенный business bot имеет отдельную модель прав; user client MTProto — другую.

При неизвестной функции начните с индекса и live API, затем выберите относящийся к задаче навык. Наличие функции в общей таблице не создает права на ее выполнение.
