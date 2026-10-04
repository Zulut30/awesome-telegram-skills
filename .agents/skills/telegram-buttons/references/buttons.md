# Styles и custom emoji

Проверено по официальному API 4 октября 2026 года: [InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton), [KeyboardButton](https://core.telegram.org/bots/api#keyboardbutton).

`style` принимает `primary` (синий), `success` (зеленый), `danger` (красный); без него оформление выбирает клиент. Это не произвольный RGB/CSS цвет.

`icon_custom_emoji_id` задает custom emoji перед текстом. Доступ зависит от дополнительных username, приобретенных через Fragment, либо Premium владельца бота для сообщений, непосредственно отправленных ботом в private/group/supergroup. Не связывай возможность с Premium пользователя, который нажал кнопку. Условия других типов сообщений проверяй отдельно.

Пример Bot API payload для inline-кнопки:

```json
{"text":"Подтвердить","callback_data":"confirm:order-123","style":"success"}
```

Добавляй `icon_custom_emoji_id` только после проверки права и действительного ID. Для получения данных custom emoji используй [getCustomEmojiStickers](https://core.telegram.org/bots/api#getcustomemojistickers). Иконка кнопки отличается от `custom_emoji` entity внутри текста сообщения.

Inline markup — список строк: `[[button1, button2], [button3, button4]]` для двух в ряд, `[[button1, button2, button3]]` для трех. Для aiogram 3.31 это `InlineKeyboardMarkup(inline_keyboard=rows)`. Каждая inline-кнопка имеет ровно одно action, включая современный `disabled=DisabledButton()`; callback_data 1–64 UTF-8 bytes. Pay/game — первые в первой строке, pay только invoice. URL/copy/switch inline/disabled не присылают обычный callback_query о нажатии.

Reply markup строится как `ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Каталог"), KeyboardButton(text="Помощь")]], resize_keyboard=True, input_field_placeholder="Выберите действие")`. Оно отправляет text/service data как Message и не работает channel/Business. Request-поля доступны private; request_id уникален в клавиатуре и signed32. Текст можно набрать вручную, shared user/chat ID не выдает автоматически права или историю. ForceReply запрашивает UI ответа, но не проверяет текст; привяжи ожидающий ответ к actor/chat/prompt.message_id. Для удаления — ReplyKeyboardRemove(remove_keyboard=True). Inline force_reply в Bot API 10.3 нельзя менять при edit.

Если пользователь уже подключил общую библиотеку, те же native models принимает `telegram_patterns.aiogram.inline_keyboard(rows,...)` / `reply_keyboard(rows,...)`; для равномерных callback rows есть action_menu(columns=2/3). Это optional reuse, не обязательная зависимость навыка. Сверяй exports установленной версии; компонентные лимиты не выдавай за лимиты Telegram. Источники reply/input: [ReplyKeyboardMarkup](https://core.telegram.org/bots/api#replykeyboardmarkup), [ForceReply](https://core.telegram.org/bots/api#forcereply).
