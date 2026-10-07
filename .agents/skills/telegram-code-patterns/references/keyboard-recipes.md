# Клавиатуры и события

Доступно с 0.14.0, проверено на 0.24.0.

Навык переносится отдельно; примеры требуют установленный локальный `awesome-telegram-patterns[aiogram]` и aiogram >=3.31. Установка из PyPI не подразумевается. Сохраняй текущий Dispatcher/SDK; для проекта с другой библиотекой используй ее native API, не меняй стек ради helper.

Две кнопки в строке, затем еще две; замена на три и цвет:

```python
from aiogram.types import InlineKeyboardButton as Button
from telegram_patterns.aiogram import inline_keyboard, reply_keyboard, input_prompt, remove_keyboard

buttons = [Button(text=str(n), callback_data=f"item:{n}", style="primary") for n in range(1, 7)]
two = inline_keyboard([buttons[:2], buttons[2:4], buttons[4:]])
three = inline_keyboard([buttons[:3], buttons[3:]])
mixed = inline_keyboard([buttons[:1], buttons[1:3], buttons[3:]])
confirm = inline_keyboard([[Button(text="Подтвердить", callback_data="confirm:opaque-id", style="success"),
                            Button(text="Отмена", callback_data="cancel:opaque-id", style="danger")]])
reply = reply_keyboard([["Каталог", "Помощь"], ["Закрыть"]], placeholder="Выберите действие")
prompt = input_prompt("Ваше имя")
hidden = remove_keyboard()
```

В existing async handler: `await message.answer("Меню", reply_markup=two)`. Helpers строят native SDK markup без HTTP и копируют кнопки. 1–8 в строке / <=100 суммарно — component limits. Inline exact-one-action, callback_data 1–64 UTF-8 bytes; native style только primary/success/danger/default, не RGB. `icon_custom_emoji_id` удаляется при default `emoji_entitlement_verified=False`; True задается только после проверки права бота и реального ID, а не по Premium нажавшего пользователя.

Передавай фактический `chat_type`/`business`; ограничения прав/специальных contexts не покрываются только local validation. Reply запрещен channel/Business; request_contact/location/poll/users/chat/managed_bot/web_app доступны private. KeyboardButton native models позволяют запросы; request_id уникален в меню и signed32. Response — message/contact/location/users_shared/chat_shared, не callback; shared ID не дает истории/прав. Typed/forged reply text не доказывает click.

В callback handler ответь `await query.answer()` до работы; проверь owner/актуальный object/version, затем `await query.message.edit_reply_markup(reply_markup=three)` лишь если доступен Message. Не пытайся повторно изменять уже ту же клавиатуру; inline force_reply flag неизменяем при edit. Объектные права/идемпотентность проверяет сервис. Inaccessible/inline callbacks требуют своего пути.

ForceReply — UI запроса ответа; храни ожидаемый (chat_id, actor_id, prompt.message_id), сверяй reply_to_message и валидируй ввод. Placeholder не меняет произвольную верстку. Для полноценной формы используй локальный form recipe; для своего интерфейса ввода — Mini App.

```python
from telegram_patterns.aiogram import UpdateObserver, event_router, method_catalog, build_request

async def record(trace):
    pass  # Метаданные, без raw Update/text/contact/initData.

async def on_reaction(event):
    pass  # Native SDK event; прикладные права здесь.

# dispatcher.update.outer_middleware(UpdateObserver(record))
# dispatcher.include_router(event_router({"message_reaction": on_reaction}))
methods = method_catalog()
request = build_request("sendMessage", {"chat_id": 42, "text": "Пример"})
# После проверки адресата: result = await existing_bot(request)
```

method_catalog покрывает установленный SDK, build_request отклоняет неизвестные top-level parameters, строит native request и не отправляет его. SDK schema не проверяет все права/лимиты/semantic requirements Telegram. При предоставленном репозитории используй его catalog/recipes; перенос этого навыка не требует этих внешних файлов.

Observer best-effort, include_ids=False; failed recorder не ломает handler. Только доставленные Update, не durable audit и не новая subscription. event_router объявляет SDK update kinds для resolve_used_update_types, не отвечает автоматически на callback. Реакции require admin + explicit allowed_updates; middleware само не включает их. Обычный Bot API не наблюдает user typing/read receipts/click URL/copy. sendChatAction — действие бота.

Для Mini App установленный TS package экспортирует `TelegramNativeAPI`, `TELEGRAM_NATIVE_METHODS`, `TELEGRAM_NATIVE_EVENTS`. `supports(path)` сверяет версию и actual function, `call(path,...args)` сохраняет callbacks/native result (unknown), `listen(event,fn)` возвращает cleanup; dispose очищает только свои listeners. Это не полный typed SDK wrapper, permissions/auth/init flow остаются у проекта. Unsupported/denied/cancelled/late callback не считать успехом; direct onClick/onEvent через call требуют собственных off. Новый mounted экран создает новый adapter.

Проверь реальный Dispatcher и installed package с negative cases: чужой actor, duplicate callback, непредусмотренный reply_to, неверный context, unknown/misspelled parameter, missing native method. Fake transport/mock не доказывают доставку/физический Telegram-клиент. Нельзя отправлять synthetic request fixtures без замены.

Проверено 4 октября 2026: [InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton), [KeyboardButton](https://core.telegram.org/bots/api#keyboardbutton), [ReplyKeyboardMarkup](https://core.telegram.org/bots/api#replykeyboardmarkup), [ForceReply](https://core.telegram.org/bots/api#forcereply), [Update](https://core.telegram.org/bots/api#update), [Mini App client API](https://core.telegram.org/bots/webapps#initializing-mini-apps), [события](https://core.telegram.org/bots/webapps#events-available-for-mini-apps). Версия установленного SDK для проверки: aiogram 3.31.0.

Для flat списка и width patterns 2/3/mixed прочитай [новую композицию](keyboard-layouts.md). Новый default capability fallback сохраняет текст без styles/emoji; старые calls выше не меняют поведения.
