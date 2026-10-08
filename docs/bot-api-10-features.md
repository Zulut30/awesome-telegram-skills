# Новые возможности Bot API 10.0–10.3

Термины: **неизвестный результат** — запрос мог выполниться, но ответа нет (таймаут, обрыв связи); повторять вслепую нельзя, сначала сверка; **сверка** — запрос фактического состояния у провайдера или в хранилище перед повтором или выдачей.

Пять функций, добавленных в Bot API 10.0–10.3, с рецептом библиотеки и ограничениями для каждой. Все рецепты запускаются без сети: `telegram-patterns run-recipe <id> --offline`; поведение настоящих клиентов и сервера Telegram офлайн-проверка не подтверждает.

## Guest mode (10.0)

Бот с включенным Guest Mode (настройки бота в Mini App @BotFather) отвечает в группе или личном чате, где он не состоит: пользователь упоминает бота или отвечает на его сообщение, бот получает update `guest_message` и может дать один ответ методом [answerGuestQuery](https://core.telegram.org/bots/api#answerguestquery) с `guest_query_id` и `InlineQueryResult`. Ответ приходит как inline-сообщение: [SentGuestMessage](https://core.telegram.org/bots/api#sentguestmessage) содержит `inline_message_id`. Флаг `User.supports_guest_queries` в `getMe` показывает, включен ли режим.

Ограничения:

- Один ответ на одно упоминание; повторная доставка update не должна давать второй ответ — отмечайте `guest_query_id` до вызова.
- Нет истории чата, списка участников и следующих сообщений: бот видит только вызывающее сообщение и сообщение, на которое оно отвечает, пока его не упомянут снова.
- `guest_message` — отдельный тип update: обычные обработчики `message` его не получают, а `sendMessage` в этот чат недоступен боту, который в нем не состоит.
- В одном сообщении можно упомянуть до трех guest-ботов.

Рецепт: `demo-guest-reply` (`guest_bot.py`) — ответ с учетом сообщения, на которое ответил пользователь, один раз на `guest_query_id`.

## Общение ботов между собой (10.0)

Обычно боты не видят сообщений других ботов. При включенном Bot-to-Bot Communication Mode в @BotFather ([Bot Features](https://core.telegram.org/bots/features#bot-to-bot-communication)):

- в группе бот получает сообщение другого бота, если тот упомянул его в команде (`/command@OtherBot`) или ответил на его сообщение, и режим включен хотя бы у одного из двух ботов;
- бот с включенным режимом получает все сообщения ботов в группе, если он администратор или у него выключен privacy mode;
- в личный чат бот пишет другому боту через `sendMessage` с его `@username`, если режим включен у обоих;
- бот, подключенный к Business-аккаунту в Chat Access Mode, пишет ботам этого аккаунта, если режим включен у отправителя.

Ограничения: Telegram требует защиту от бесконечных циклов — дедупликацию повторов, ограничение частоты ответов каждому боту и предел глубины или времени обмена, а бот должен оставаться стабильным, даже если другой бот отвечает мгновенно и бесконечно. Невыполнение может привести к ограничениям платформы.

Рецепт: `demo-bot-relay` (`bot_relay_bot.py`) — `LoopGuard` с дедупликацией, паузой на собеседника и пределом глубины; сообщение человека в чате снова разрешает обмен. Счетчики живут в одном процессе: при нескольких воркерах держите их в общем хранилище.

## Live photos (10.0)

Live photo — фото и короткое видео. Отправка — [sendLivePhoto](https://core.telegram.org/bots/api#sendlivephoto) (`live_photo` — видео, `photo` — статичный кадр), альбом — `sendMediaGroup` с [InputMediaLivePhoto](https://core.telegram.org/bots/api#inputmedialivephoto), платные медиа — `InputPaidMediaLivePhoto`. Входящее приходит в `Message.live_photo` ([LivePhoto](https://core.telegram.org/bots/api#livephoto)): `file_id` видео и необязательный массив `photo`.

Ограничения:

- Только `file_id` или загрузка файла: отправка по URL не поддерживается.
- Видео не длиннее 10 секунд и не больше 10 МБ; длительность локального файла библиотека не проверяет — нужен собственный probe.
- `LivePhoto.photo` может отсутствовать: без статичного кадра пару нельзя переслать как live photo.

Рецепт: `demo-live-photo` (`live_photo_bot.py`) — сохранить присланное, отправить по `file_id`, собрать альбом; `live_photo_source` отклоняет URL и загрузку больше 10 МБ.

## Join request queries (10.1)

Бот, назначенный обрабатывать заявки на вступление, получает `ChatJoinRequest.query_id`. В течение 10 секунд он вызывает [sendChatJoinRequestWebApp](https://core.telegram.org/bots/api#sendchatjoinrequestwebapp) — показывает пользователю Mini App — или сразу [answerChatJoinRequestQuery](https://core.telegram.org/bots/api#answerchatjoinrequestquery) с `approve`, `decline` или `queue` (оставить решение администраторам). После Mini App решение отправляет тот же `answerChatJoinRequestQuery`. Флаг `User.supports_join_request_queries` и поле `ChatFullInfo.guard_bot` показывают поддержку и назначенного бота.

Ограничения:

- 10 секунд с момента заявки на первый вызов; опоздавшую заявку не трогайте, она остается администраторам.
- Пользователя в Mini App берите только из подписанного `initData`, проверенного на сервере; параметр URL с `chat_id` не подписан и лишь сужает поиск ожидающей заявки.
- Сколько ждет query после показа Mini App, Bot API не указывает: ошибку ответа считайте неизвестным исходом для администраторов, не повторяйте вслепую.
- Обычная заявка без `query_id` — это `approveChatJoinRequest`/`declineChatJoinRequest` с правом `can_invite_users`.

Рецепт: `demo-join-query` (`join_query_bot.py`) — Mini App, проверка `validate_init_data`, одно решение на заявку, `queue`, если Mini App показать не удалось.

## Медиа в опросах (10.0–10.1)

`sendPoll` принимает медиа в вариантах (`InputPollOption.media` — [InputPollOptionMedia](https://core.telegram.org/bots/api#inputpolloptionmedia): анимация, ссылка `InputMediaLink`, live photo, геопозиция, фото, стикер, место, видео), в описании (`media` — [InputPollMedia](https://core.telegram.org/bots/api#inputpollmedia)) и в пояснении quiz (`explanation_media`). Входящие опросы содержат [PollMedia](https://core.telegram.org/bots/api#pollmedia) — не больше одного вида медиа в объекте.

Ограничения:

- Ссылка (`InputMediaLink`) и стикер — только в вариантах; аудио и документ — только в описании и пояснении; в вариантах они не приходят.
- `explanation_media` — только для quiz.
- Количество вариантов 1–12, текст варианта до 100 символов; ограничения каналов (`members_only`, `country_codes`) не связаны с медиа.

Рецепт: `demo-poll-media` (`poll_media_bot.py`) — опрос с фото, ссылкой и местом через `poll_request`, quiz с медиа пояснения, разбор медиа во входящем опросе.

Источники: [Bot API changelog](https://core.telegram.org/bots/api-changelog), [answerGuestQuery](https://core.telegram.org/bots/api#answerguestquery), [Update](https://core.telegram.org/bots/api#update), [Bot Features: Guest Bots](https://core.telegram.org/bots/features#guest-bots), [Bot Features: Bot-to-Bot](https://core.telegram.org/bots/features#bot-to-bot-communication), [sendLivePhoto](https://core.telegram.org/bots/api#sendlivephoto), [ChatJoinRequest](https://core.telegram.org/bots/api#chatjoinrequest), [sendChatJoinRequestWebApp](https://core.telegram.org/bots/api#sendchatjoinrequestwebapp), [sendPoll](https://core.telegram.org/bots/api#sendpoll), [PollMedia](https://core.telegram.org/bots/api#pollmedia). Проверено 7 октября 2026 года по Bot API 10.3 и aiogram 3.31.0.
