# Все методы Bot API

Снимок 10.3, 185 методов. Для каждой строки есть Python пример построения запроса через публичный API библиотеки. Значения искусственные; Telegram HTTP/права/бизнес-сценарии ими не проверены. Практические примеры клавиатур: [keyboards.md](keyboards.md).

| Метод | Обязательные параметры SDK |
| --- | --- |
| [addStickerToSet](methods/addStickerToSet.md) | user_id, name, sticker |
| [answerCallbackQuery](methods/answerCallbackQuery.md) | callback_query_id |
| [answerChatJoinRequestQuery](methods/answerChatJoinRequestQuery.md) | chat_join_request_query_id, result |
| [answerGuestQuery](methods/answerGuestQuery.md) | guest_query_id, result |
| [answerInlineQuery](methods/answerInlineQuery.md) | inline_query_id, results |
| [answerPreCheckoutQuery](methods/answerPreCheckoutQuery.md) | pre_checkout_query_id, ok |
| [answerShippingQuery](methods/answerShippingQuery.md) | shipping_query_id, ok |
| [answerWebAppQuery](methods/answerWebAppQuery.md) | web_app_query_id, result |
| [approveChatJoinRequest](methods/approveChatJoinRequest.md) | chat_id, user_id |
| [approveSuggestedPost](methods/approveSuggestedPost.md) | chat_id, message_id |
| [banChatMember](methods/banChatMember.md) | chat_id, user_id |
| [banChatSenderChat](methods/banChatSenderChat.md) | chat_id, sender_chat_id |
| [close](methods/close.md) | — |
| [closeForumTopic](methods/closeForumTopic.md) | chat_id, message_thread_id |
| [closeGeneralForumTopic](methods/closeGeneralForumTopic.md) | chat_id |
| [convertGiftToStars](methods/convertGiftToStars.md) | business_connection_id, owned_gift_id |
| [copyMessage](methods/copyMessage.md) | chat_id, from_chat_id, message_id |
| [copyMessages](methods/copyMessages.md) | chat_id, from_chat_id, message_ids |
| [createChatInviteLink](methods/createChatInviteLink.md) | chat_id |
| [createChatSubscriptionInviteLink](methods/createChatSubscriptionInviteLink.md) | chat_id, subscription_period, subscription_price |
| [createForumTopic](methods/createForumTopic.md) | chat_id, name |
| [createInvoiceLink](methods/createInvoiceLink.md) | title, description, payload, currency, prices |
| [createNewStickerSet](methods/createNewStickerSet.md) | user_id, name, title, stickers |
| [declineChatJoinRequest](methods/declineChatJoinRequest.md) | chat_id, user_id |
| [declineSuggestedPost](methods/declineSuggestedPost.md) | chat_id, message_id |
| [deleteAllMessageReactions](methods/deleteAllMessageReactions.md) | chat_id |
| [deleteBusinessMessages](methods/deleteBusinessMessages.md) | business_connection_id, message_ids |
| [deleteChatPhoto](methods/deleteChatPhoto.md) | chat_id |
| [deleteChatStickerSet](methods/deleteChatStickerSet.md) | chat_id |
| [deleteEphemeralMessage](methods/deleteEphemeralMessage.md) | chat_id, receiver_user_id, ephemeral_message_id |
| [deleteForumTopic](methods/deleteForumTopic.md) | chat_id, message_thread_id |
| [deleteMessage](methods/deleteMessage.md) | chat_id, message_id |
| [deleteMessageReaction](methods/deleteMessageReaction.md) | chat_id, message_id |
| [deleteMessages](methods/deleteMessages.md) | chat_id, message_ids |
| [deleteMyCommands](methods/deleteMyCommands.md) | — |
| [deleteStickerFromSet](methods/deleteStickerFromSet.md) | sticker |
| [deleteStickerSet](methods/deleteStickerSet.md) | name |
| [deleteStory](methods/deleteStory.md) | business_connection_id, story_id |
| [deleteWebhook](methods/deleteWebhook.md) | — |
| [editChatInviteLink](methods/editChatInviteLink.md) | chat_id, invite_link |
| [editChatSubscriptionInviteLink](methods/editChatSubscriptionInviteLink.md) | chat_id, invite_link |
| [editEphemeralMessageCaption](methods/editEphemeralMessageCaption.md) | chat_id, receiver_user_id, ephemeral_message_id |
| [editEphemeralMessageMedia](methods/editEphemeralMessageMedia.md) | chat_id, receiver_user_id, ephemeral_message_id, media |
| [editEphemeralMessageReplyMarkup](methods/editEphemeralMessageReplyMarkup.md) | chat_id, receiver_user_id, ephemeral_message_id |
| [editEphemeralMessageText](methods/editEphemeralMessageText.md) | chat_id, receiver_user_id, ephemeral_message_id |
| [editForumTopic](methods/editForumTopic.md) | chat_id, message_thread_id |
| [editGeneralForumTopic](methods/editGeneralForumTopic.md) | chat_id, name |
| [editMessageCaption](methods/editMessageCaption.md) | — |
| [editMessageChecklist](methods/editMessageChecklist.md) | business_connection_id, chat_id, message_id, checklist |
| [editMessageLiveLocation](methods/editMessageLiveLocation.md) | latitude, longitude |
| [editMessageMedia](methods/editMessageMedia.md) | media |
| [editMessageReplyMarkup](methods/editMessageReplyMarkup.md) | — |
| [editMessageText](methods/editMessageText.md) | — |
| [editStory](methods/editStory.md) | business_connection_id, story_id, content |
| [editUserStarSubscription](methods/editUserStarSubscription.md) | user_id, telegram_payment_charge_id, is_canceled |
| [exportChatInviteLink](methods/exportChatInviteLink.md) | chat_id |
| [forwardMessage](methods/forwardMessage.md) | chat_id, from_chat_id, message_id |
| [forwardMessages](methods/forwardMessages.md) | chat_id, from_chat_id, message_ids |
| [getAvailableGifts](methods/getAvailableGifts.md) | — |
| [getBusinessAccountGifts](methods/getBusinessAccountGifts.md) | business_connection_id |
| [getBusinessAccountStarBalance](methods/getBusinessAccountStarBalance.md) | business_connection_id |
| [getBusinessConnection](methods/getBusinessConnection.md) | business_connection_id |
| [getChat](methods/getChat.md) | chat_id |
| [getChatAdministrators](methods/getChatAdministrators.md) | chat_id |
| [getChatGifts](methods/getChatGifts.md) | chat_id |
| [getChatMember](methods/getChatMember.md) | chat_id, user_id |
| [getChatMemberCount](methods/getChatMemberCount.md) | chat_id |
| [getChatMenuButton](methods/getChatMenuButton.md) | — |
| [getCustomEmojiStickers](methods/getCustomEmojiStickers.md) | custom_emoji_ids |
| [getFile](methods/getFile.md) | file_id |
| [getForumTopicIconStickers](methods/getForumTopicIconStickers.md) | — |
| [getGameHighScores](methods/getGameHighScores.md) | user_id |
| [getManagedBotAccessSettings](methods/getManagedBotAccessSettings.md) | user_id |
| [getManagedBotToken](methods/getManagedBotToken.md) | user_id |
| [getMe](methods/getMe.md) | — |
| [getMyCommands](methods/getMyCommands.md) | — |
| [getMyDefaultAdministratorRights](methods/getMyDefaultAdministratorRights.md) | — |
| [getMyDescription](methods/getMyDescription.md) | — |
| [getMyName](methods/getMyName.md) | — |
| [getMyShortDescription](methods/getMyShortDescription.md) | — |
| [getMyStarBalance](methods/getMyStarBalance.md) | — |
| [getStarTransactions](methods/getStarTransactions.md) | — |
| [getStickerSet](methods/getStickerSet.md) | name |
| [getUpdates](methods/getUpdates.md) | — |
| [getUserChatBoosts](methods/getUserChatBoosts.md) | chat_id, user_id |
| [getUserGifts](methods/getUserGifts.md) | user_id |
| [getUserPersonalChatMessages](methods/getUserPersonalChatMessages.md) | user_id, limit |
| [getUserProfileAudios](methods/getUserProfileAudios.md) | user_id |
| [getUserProfilePhotos](methods/getUserProfilePhotos.md) | user_id |
| [getWebhookInfo](methods/getWebhookInfo.md) | — |
| [giftPremiumSubscription](methods/giftPremiumSubscription.md) | user_id, month_count, star_count |
| [hideGeneralForumTopic](methods/hideGeneralForumTopic.md) | chat_id |
| [leaveChat](methods/leaveChat.md) | chat_id |
| [logOut](methods/logOut.md) | — |
| [pinChatMessage](methods/pinChatMessage.md) | chat_id, message_id |
| [postStory](methods/postStory.md) | business_connection_id, content, active_period |
| [promoteChatMember](methods/promoteChatMember.md) | chat_id, user_id |
| [readBusinessMessage](methods/readBusinessMessage.md) | business_connection_id, chat_id, message_id |
| [refundStarPayment](methods/refundStarPayment.md) | user_id, telegram_payment_charge_id |
| [removeBusinessAccountProfilePhoto](methods/removeBusinessAccountProfilePhoto.md) | business_connection_id |
| [removeChatVerification](methods/removeChatVerification.md) | chat_id |
| [removeMyProfilePhoto](methods/removeMyProfilePhoto.md) | — |
| [removeUserVerification](methods/removeUserVerification.md) | user_id |
| [reopenForumTopic](methods/reopenForumTopic.md) | chat_id, message_thread_id |
| [reopenGeneralForumTopic](methods/reopenGeneralForumTopic.md) | chat_id |
| [replaceManagedBotToken](methods/replaceManagedBotToken.md) | user_id |
| [replaceStickerInSet](methods/replaceStickerInSet.md) | user_id, name, old_sticker, sticker |
| [repostStory](methods/repostStory.md) | business_connection_id, from_chat_id, from_story_id, active_period |
| [restrictChatMember](methods/restrictChatMember.md) | chat_id, user_id, permissions |
| [revokeChatInviteLink](methods/revokeChatInviteLink.md) | chat_id, invite_link |
| [savePreparedInlineMessage](methods/savePreparedInlineMessage.md) | user_id, result |
| [savePreparedKeyboardButton](methods/savePreparedKeyboardButton.md) | user_id, button |
| [sendAnimation](methods/sendAnimation.md) | chat_id, animation |
| [sendAudio](methods/sendAudio.md) | chat_id, audio |
| [sendChatAction](methods/sendChatAction.md) | chat_id, action |
| [sendChatJoinRequestWebApp](methods/sendChatJoinRequestWebApp.md) | chat_join_request_query_id, web_app_url |
| [sendChecklist](methods/sendChecklist.md) | business_connection_id, chat_id, checklist |
| [sendContact](methods/sendContact.md) | chat_id, phone_number, first_name |
| [sendDice](methods/sendDice.md) | chat_id |
| [sendDocument](methods/sendDocument.md) | chat_id, document |
| [sendGame](methods/sendGame.md) | chat_id, game_short_name |
| [sendGift](methods/sendGift.md) | gift_id |
| [sendInvoice](methods/sendInvoice.md) | chat_id, title, description, payload, currency, prices |
| [sendLivePhoto](methods/sendLivePhoto.md) | chat_id, live_photo, photo |
| [sendLocation](methods/sendLocation.md) | chat_id, latitude, longitude |
| [sendMediaGroup](methods/sendMediaGroup.md) | chat_id, media |
| [sendMessage](methods/sendMessage.md) | chat_id, text |
| [sendMessageDraft](methods/sendMessageDraft.md) | chat_id, draft_id |
| [sendPaidMedia](methods/sendPaidMedia.md) | chat_id, star_count, media |
| [sendPhoto](methods/sendPhoto.md) | chat_id, photo |
| [sendPoll](methods/sendPoll.md) | chat_id, question, options |
| [sendRichMessage](methods/sendRichMessage.md) | chat_id, rich_message |
| [sendRichMessageDraft](methods/sendRichMessageDraft.md) | chat_id, draft_id, rich_message |
| [sendSticker](methods/sendSticker.md) | chat_id, sticker |
| [sendVenue](methods/sendVenue.md) | chat_id, latitude, longitude, title, address |
| [sendVideo](methods/sendVideo.md) | chat_id, video |
| [sendVideoNote](methods/sendVideoNote.md) | chat_id, video_note |
| [sendVoice](methods/sendVoice.md) | chat_id, voice |
| [setBusinessAccountBio](methods/setBusinessAccountBio.md) | business_connection_id |
| [setBusinessAccountGiftSettings](methods/setBusinessAccountGiftSettings.md) | business_connection_id, show_gift_button, accepted_gift_types |
| [setBusinessAccountName](methods/setBusinessAccountName.md) | business_connection_id, first_name |
| [setBusinessAccountProfilePhoto](methods/setBusinessAccountProfilePhoto.md) | business_connection_id, photo |
| [setBusinessAccountUsername](methods/setBusinessAccountUsername.md) | business_connection_id |
| [setChatAdministratorCustomTitle](methods/setChatAdministratorCustomTitle.md) | chat_id, user_id, custom_title |
| [setChatDescription](methods/setChatDescription.md) | chat_id |
| [setChatMemberTag](methods/setChatMemberTag.md) | chat_id, user_id |
| [setChatMenuButton](methods/setChatMenuButton.md) | — |
| [setChatPermissions](methods/setChatPermissions.md) | chat_id, permissions |
| [setChatPhoto](methods/setChatPhoto.md) | chat_id, photo |
| [setChatStickerSet](methods/setChatStickerSet.md) | chat_id, sticker_set_name |
| [setChatTitle](methods/setChatTitle.md) | chat_id, title |
| [setCustomEmojiStickerSetThumbnail](methods/setCustomEmojiStickerSetThumbnail.md) | name |
| [setGameScore](methods/setGameScore.md) | user_id, score |
| [setManagedBotAccessSettings](methods/setManagedBotAccessSettings.md) | user_id, is_access_restricted |
| [setMessageReaction](methods/setMessageReaction.md) | chat_id, message_id |
| [setMyCommands](methods/setMyCommands.md) | commands |
| [setMyDefaultAdministratorRights](methods/setMyDefaultAdministratorRights.md) | — |
| [setMyDescription](methods/setMyDescription.md) | — |
| [setMyName](methods/setMyName.md) | — |
| [setMyProfilePhoto](methods/setMyProfilePhoto.md) | photo |
| [setMyShortDescription](methods/setMyShortDescription.md) | — |
| [setPassportDataErrors](methods/setPassportDataErrors.md) | user_id, errors |
| [setStickerEmojiList](methods/setStickerEmojiList.md) | sticker, emoji_list |
| [setStickerKeywords](methods/setStickerKeywords.md) | sticker |
| [setStickerMaskPosition](methods/setStickerMaskPosition.md) | sticker |
| [setStickerPositionInSet](methods/setStickerPositionInSet.md) | sticker, position |
| [setStickerSetThumbnail](methods/setStickerSetThumbnail.md) | name, user_id, format |
| [setStickerSetTitle](methods/setStickerSetTitle.md) | name, title |
| [setUserEmojiStatus](methods/setUserEmojiStatus.md) | user_id |
| [setWebhook](methods/setWebhook.md) | url |
| [stopMessageLiveLocation](methods/stopMessageLiveLocation.md) | — |
| [stopPoll](methods/stopPoll.md) | chat_id, message_id |
| [transferBusinessAccountStars](methods/transferBusinessAccountStars.md) | business_connection_id, star_count |
| [transferGift](methods/transferGift.md) | business_connection_id, owned_gift_id, new_owner_chat_id |
| [unbanChatMember](methods/unbanChatMember.md) | chat_id, user_id |
| [unbanChatSenderChat](methods/unbanChatSenderChat.md) | chat_id, sender_chat_id |
| [unhideGeneralForumTopic](methods/unhideGeneralForumTopic.md) | chat_id |
| [unpinAllChatMessages](methods/unpinAllChatMessages.md) | chat_id |
| [unpinAllForumTopicMessages](methods/unpinAllForumTopicMessages.md) | chat_id, message_thread_id |
| [unpinAllGeneralForumTopicMessages](methods/unpinAllGeneralForumTopicMessages.md) | chat_id |
| [unpinChatMessage](methods/unpinChatMessage.md) | chat_id |
| [upgradeGift](methods/upgradeGift.md) | business_connection_id, owned_gift_id |
| [uploadStickerFile](methods/uploadStickerFile.md) | user_id, sticker, sticker_format |
| [verifyChat](methods/verifyChat.md) | chat_id |
| [verifyUser](methods/verifyUser.md) | user_id |
