# python-telegram-bot

Если проект уже написан на python-telegram-bot (PTB), библиотеку можно подключить без перехода на aiogram: SDK-независимое ядро работает с любым SDK, а адаптер `telegram_patterns.ptb` превращает его результаты в объекты PTB и дает офлайн-транспорт для тестов. Проверено с python-telegram-bot 22.8, который реализует Bot API 10.0.

Установка: локальный wheel с extra `ptb` (`awesome-telegram-patterns[ptb]`), который требует `python-telegram-bot>=22.8,<23`. Extra `aiogram` для этого не нужен.

## Что работает с PTB

- Клавиатуры как Bot API JSON: `inline_button`, `reply_button`, `layout_rows`, `inline_markup`, `reply_markup`, `force_reply_markup`, `remove_markup`, `paginated_markup`, `selection_markup`. JSON совпадает с выводом aiogram-адаптера — это проверяют тесты.
- Ядро без SDK: `SelectionMenu`, `CalendarMonth`/`SlotSchedule`, `MessageBuilder` и `split_formatted`, `RichMessageBuilder`, `ephemeral_parameters`, `StarsSubscription`, `SQLiteOnce`, `validate_init_data`.
- Адаптер: `ptb_markup(json)` и `ptb_inline_markup(json)` для `reply_markup`, `ptb_text(formatted)` для `send_message(**...)` с entities и `parse_mode=None`, `StubRequest` и `offline_application()` для тестов без сети.

```python
from telegram_patterns import inline_button, inline_markup, layout_rows
from telegram_patterns.ptb import ptb_markup

buttons = [inline_button(name, callback_data=f'menu:{key}') for name, key in [('Каталог', 'catalog'), ('Помощь', 'help')]]
await update.effective_message.reply_text('Меню', reply_markup=ptb_markup(inline_markup(layout_rows(buttons, (2,)))))
```

## Новые возможности Bot API

PTB 22.8 знает Bot API 10.0. Возможности 10.1–10.3 доступны и без обновления SDK:

- новые поля в запросах — через `api_kwargs` метода: `send_message(chat_id, text, api_kwargs=ephemeral_parameters(...))`;
- новые методы — через `Bot.do_api_request`: `await bot.do_api_request('sendRichMessage', api_kwargs={'chat_id': chat_id, 'rich_message': card.as_input()})`;
- новые поля во входящих объектах — в `api_kwargs` объекта: `message.api_kwargs['community_chat_added']`, `message.api_kwargs['ephemeral_message_id']`, `request.api_kwargs['query_id']`;
- новые типы update (например `subscription` из 10.2) — в `update.api_kwargs`; их ловит `TypeHandler(Update, ...)`, а в `allowed_updates` тип нужно перечислить явно.
- `ptb_markup` сохраняет неизвестные PTB поля кнопок (например `disabled` из 10.3) в `api_kwargs`, поэтому они уходят на провод без изменений.

## Ограничения

- Пустая inline-клавиатура: PTB сериализует ее как `{}`. `ptb_markup` такую клавиатуру отклоняет; чтобы убрать клавиатуру при правке сообщения, передайте `reply_markup=None`.
- Правки сообщений (`edit_message_text`, `edit_message_reply_markup`) принимают только `InlineKeyboardMarkup` — используйте `ptb_inline_markup`.
- `reply_text` в PTB по умолчанию отвечает на исходное сообщение в группах и не отвечает в личных чатах (`do_quote`, `Defaults.do_quote`); в aiogram `message.reply` отвечает всегда, `message.answer` — никогда.
- Синхронные операции ядра с SQLite (`SQLiteOnce`, `SQLiteSlotStore`) вызывайте через `asyncio.to_thread`, чтобы не блокировать цикл событий.
- aiogram-компоненты (`telegram_patterns.aiogram`: роутеры, FSM-хранилище, `StubSession`) с PTB не работают; для них нужен перенос логики на `Application` и handlers PTB.
- `StubRequest` не обращается к сети и не подтверждает права, доставку и поведение клиентов: проверьте сценарий на тестовом боте.

## Рецепты

20 рецептов имеют вариант для PTB с офлайн-проверкой (`sdk: python-telegram-bot` в галерее, `variant_of` — исходный рецепт aiogram):

- 11 клавиатур: `ptb-two-columns`, `ptb-three-columns`, `ptb-mixed-rows`, `ptb-button-colors`, `ptb-emoji-fallback`, `ptb-reply-menu`, `ptb-contact-location`, `ptb-force-reply`, `ptb-remove-reply`, `ptb-copy-disabled`, `ptb-url-app` — JSON на проводе совпадает с aiogram-рецептом;
- 9 сценариев на настоящем `Application` со `StubRequest`: `ptb-demo-catalog`, `ptb-demo-selection`, `ptb-demo-message-text`, `ptb-demo-rich-message`, `ptb-demo-ephemeral`, `ptb-demo-stars-subscription`, `ptb-demo-community`, `ptb-demo-join-query`, `ptb-demo-recovery`.

Запуск: `telegram-patterns run-recipe ptb-demo-catalog --offline` (нужен extra `ptb`); исходники — в `examples/ptb`.

Источники: [python-telegram-bot](https://docs.python-telegram-bot.org/en/stable/), [Bot.do_api_request](https://docs.python-telegram-bot.org/en/stable/telegram.bot.html#telegram.Bot.do_api_request), [BaseRequest](https://docs.python-telegram-bot.org/en/stable/telegram.request.baserequest.html), [ApplicationBuilder](https://docs.python-telegram-bot.org/en/stable/telegram.ext.applicationbuilder.html), [Defaults.do_quote](https://docs.python-telegram-bot.org/en/stable/telegram.ext.defaults.html), [Bot API changelog](https://core.telegram.org/bots/api-changelog). Проверено 7 октября 2026 года по python-telegram-bot 22.8 (Bot API 10.0) и Bot API 10.3.
