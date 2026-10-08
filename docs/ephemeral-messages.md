# Эфемерные сообщения

Термины: **ACK** — ответ на нажатие кнопки через `answerCallbackQuery`: клиент убирает индикатор ожидания; это не сообщение об успехе операции.

Эфемерное сообщение (Bot API 10.2+) видят только один участник группы или супергруппы и бот; остальные участники его не видят. Оно подходит для личного ответа на нажатие кнопки или на команду, не засоряя общий чат: статус пользователя, подсказка, подтверждение действия. В личных чатах и каналах эфемерных сообщений нет.

## Правила Telegram

По разделу [Ephemeral Messages and Commands](https://core.telegram.org/bots/api#ephemeral-messages-and-commands):

- Любой бот может ответить эфемерно в течение 15 секунд после действия пользователя, назвав это действие: `callback_query_id` нажатой кнопки или `reply_parameters.ephemeral_message_id` входящего эфемерного сообщения. Ответ придет в то приложение, из которого пользователь действовал.
- Бот-администратор чата может написать эфемерно любому участнику, кроме ботов, в любое время и без ссылки на действие; тогда сообщение может прийти в несколько приложений пользователя.
- Доставка не гарантирована, особенно если пользователь не в сети; сообщения могут исчезнуть сами или после перезапуска приложения. Не храните в эфемерном сообщении то, что нельзя потерять.
- У отправленного эфемерного сообщения `message_id` равен 0, а адрес — `ephemeral_message_id`. Этот идентификатор может достаться другому сообщению после удаления или истечения первого.
- `replace_callback_query_message=True` показывает ответ на месте нажатого сообщения. Для кнопок самого эфемерного сообщения это поле должно быть `False`: такое сообщение изменяют методами `editEphemeralMessage…`.
- Ответ на эфемерное сообщение сам должен быть эфемерным и уходит не позже 15 секунд после его отправки. Цитата (`quote`) в таком ответе игнорируется; `live_period` трансляции геопозиции должен быть 0; кнопки `login_url` не поддерживаются.
- Команда с `is_ephemeral=True` в [BotCommand](https://core.telegram.org/bots/api#botcommand) приходит боту невидимой для остальных участников; отвечают на нее через `reply_parameters.ephemeral_message_id`.

## Отправка, изменение и удаление в aiogram

В aiogram 3.31.0 параметры передаются полем `ephemeral_message_parameters` ([EphemeralMessageParameters](https://core.telegram.org/bots/api#ephemeralmessageparameters)) в `sendMessage`, `sendPhoto`, `sendDocument`, `sendRichMessage` и других методах отправки:

```python
from aiogram.methods import DeleteEphemeralMessage, EditEphemeralMessageText, SendMessage

await bot(SendMessage(chat_id=group_id, text='Видите только вы',
                      ephemeral_message_parameters={'receiver_user_id': query.from_user.id,
                                                    'callback_query_id': query.id}))
await query.answer()
```

Изменение и удаление адресуются тройкой `chat_id`, `receiver_user_id`, `ephemeral_message_id`: [editEphemeralMessageText](https://core.telegram.org/bots/api#editephemeralmessagetext) (текст или `rich_message`), [editEphemeralMessageMedia](https://core.telegram.org/bots/api#editephemeralmessagemedia), [editEphemeralMessageCaption](https://core.telegram.org/bots/api#editephemeralmessagecaption), [editEphemeralMessageReplyMarkup](https://core.telegram.org/bots/api#editephemeralmessagereplymarkup) и [deleteEphemeralMessage](https://core.telegram.org/bots/api#deleteephemeralmessage). Все они возвращают `True`, но не гарантируют, что пользователь увидит изменение.

Нажатие кнопки по-прежнему требует ACK через `answerCallbackQuery`: эфемерный ответ его не заменяет.

## С библиотекой awesome-telegram-patterns

Если библиотека уже есть в проекте, SDK-free ядро решает, можно ли отвечать эфемерно, и собирает параметры:

```python
import time
from telegram_patterns import EphemeralMessageRef, EphemeralNotAllowed, EphemeralTrigger, ephemeral_parameters

received = time.monotonic()  # в начале обработчика нажатия
text = await load_status(chat_id, query.from_user.id)
try:
    extra = ephemeral_parameters(chat_type=message.chat.type, receiver_user_id=query.from_user.id,
                                 receiver_is_bot=query.from_user.is_bot, bot_is_admin=False,
                                 trigger=EphemeralTrigger.callback(query.id, received), now=time.monotonic())
except EphemeralNotAllowed:
    await query.answer(text[:200], show_alert=True)  # окно прошло: alert тоже видит только нажавший
else:
    await bot(SendMessage.model_validate({'chat_id': message.chat.id, 'text': text, **extra}))
    await query.answer()
```

- `ephemeral_parameters` возвращает `ephemeral_message_parameters` и, для ответа на эфемерное сообщение (`EphemeralTrigger.reply_to(ephemeral_message_id, received)`), `reply_parameters`. Отказ — `EphemeralNotAllowed` с причиной: не группа, получатель — бот, прошло больше 15 секунд у бота без прав администратора, замена сообщения без свежего нажатия или для кнопки эфемерного сообщения.
- Время считайте по монотонным часам хоста с момента получения update. Telegram отсчитывает 15 секунд от действия пользователя, поэтому медленный сервис стоит вызывать с запасом или заранее.
- `EphemeralMessageRef(chat_id, receiver_user_id, ephemeral_message_id).target()` дает аргументы для методов изменения и удаления; `ephemeral_message_id` берите из `Message.ephemeral_message_id`, а не из `message_id`.

## Проверка

`telegram-patterns run-recipe demo-ephemeral --offline` выполняет пример на настоящем `Dispatcher` без сети: панель в супергруппе — обычное сообщение, нажатие дает эфемерный ответ с `callback_query_id` (и с заменой исходного сообщения для второй кнопки), кнопки эфемерного сообщения изменяют и удаляют его по `ephemeral_message_id`, медленный сервис после 15 секунд получает alert вместо отправки, нажатие вне группы отклоняется, существующий обработчик `/help` продолжает работать. Видимость сообщения только одному участнику и его доставку офлайн-проверка не подтверждает: проверьте в тестовой группе с двумя аккаунтами.

Источники: [Ephemeral Messages and Commands](https://core.telegram.org/bots/api#ephemeral-messages-and-commands), [EphemeralMessageParameters](https://core.telegram.org/bots/api#ephemeralmessageparameters), [ReplyParameters](https://core.telegram.org/bots/api#replyparameters), [Message](https://core.telegram.org/bots/api#message), [editEphemeralMessageText](https://core.telegram.org/bots/api#editephemeralmessagetext), [deleteEphemeralMessage](https://core.telegram.org/bots/api#deleteephemeralmessage). Проверено 7 октября 2026 года по Bot API 10.3 и aiogram 3.31.0.
