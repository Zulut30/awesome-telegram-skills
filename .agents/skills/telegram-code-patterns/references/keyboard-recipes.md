# Клавиатуры и события

Доступно с 0.14.0, проверено на 0.24.0.

Термины: **fallback** — запасной вариант, если основная возможность недоступна.

Навык переносится отдельно; примеры требуют установленный локальный `awesome-telegram-patterns[aiogram]` и aiogram >=3.31. Установка из PyPI не подразумевается. Сохраняйте текущий Dispatcher/SDK; для проекта с другой библиотекой используйте ее native API, не меняйте стек ради helper.

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

Передавайте фактические `chat_type` и `business`: локальная проверка не покрывает ограничения прав и особых контекстов. Reply-клавиатура запрещена в каналах и Business; кнопки `request_contact`, `request_location`, `request_poll`, `request_users`, `request_chat`, `request_managed_bot` и `web_app` доступны только в личном чате. Модели `KeyboardButton` поддерживают такие запросы; `request_id` уникален в пределах меню и помещается в знаковое 32-битное число. Ответ приходит сообщением (`contact`, `location`, `users_shared`, `chat_shared`), а не callback; полученный ID не дает доступа к истории и прав. Набранный вручную или подделанный текст ответа не доказывает нажатие кнопки.

В callback handler ответь `await query.answer()` до работы; проверьте owner/актуальный object/version, затем `await query.message.edit_reply_markup(reply_markup=three)` лишь если доступен Message. Не пытайтесь повторно изменять уже ту же клавиатуру; inline force_reply flag неизменяем при edit. Объектные права/идемпотентность проверяет сервис. Inaccessible/inline callbacks требуют своего пути.

ForceReply — UI запроса ответа; храните ожидаемый (chat_id, actor_id, prompt.message_id), сверяйте reply_to_message и валидируйте ввод. Placeholder не меняет произвольную верстку. Для полноценной формы используйте локальный form recipe; для своего интерфейса ввода — Mini App.

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

method_catalog покрывает установленный SDK, build_request отклоняет неизвестные top-level parameters, строит native request и не отправляет его. SDK schema не проверяет все права/лимиты/semantic requirements Telegram. При предоставленном репозитории используйте его catalog/recipes; перенос этого навыка не требует этих внешних файлов.

Наблюдатель работает по возможности, `include_ids=False`; сбой записи не ломает обработчик. Он видит только доставленные `Update`: это не надежный журнал аудита и не новая подписка. `event_router` объявляет типы updates для `resolve_used_update_types` и не отвечает на callback автоматически. Реакции требуют прав администратора и явного `allowed_updates`; middleware сама их не включает. Обычный Bot API не показывает, что пользователь печатает, прочитал сообщение, открыл ссылку или скопировал текст. `sendChatAction` — действие самого бота.

Для Mini App установленный TS package экспортирует `TelegramNativeAPI`, `TELEGRAM_NATIVE_METHODS`, `TELEGRAM_NATIVE_EVENTS`. `supports(path)` сверяет версию и actual function, `call(path,...args)` сохраняет callbacks/native result (unknown), `listen(event,fn)` возвращает cleanup; dispose очищает только свои listeners. Это не полная типизированная обертка SDK: разрешения, авторизация и порядок инициализации остаются у проекта. Неподдерживаемый вызов, отказ, отмена и поздний callback — не успех; прямые `onClick` и `onEvent` через `call` требуют собственной отписки. Новый mounted экран создает новый adapter.

Проверьте реальный `Dispatcher` и установленный пакет на отрицательных сценариях: чужой пользователь, повторный callback, непредусмотренный `reply_to`, неверный контекст, неизвестный параметр или опечатка в имени, отсутствующий метод клиента. Подставной транспорт и mock не доказывают доставку и работу в настоящем клиенте Telegram. Не отправляйте синтетические заготовки запросов без замены реальными данными.

Проверено 4 октября 2026: [InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton), [KeyboardButton](https://core.telegram.org/bots/api#keyboardbutton), [ReplyKeyboardMarkup](https://core.telegram.org/bots/api#replykeyboardmarkup), [ForceReply](https://core.telegram.org/bots/api#forcereply), [Update](https://core.telegram.org/bots/api#update), [Mini App client API](https://core.telegram.org/bots/webapps#initializing-mini-apps), [события](https://core.telegram.org/bots/webapps#events-available-for-mini-apps). Версия установленного SDK для проверки: aiogram 3.31.0.

Для flat списка и width patterns 2/3/mixed прочитайте [новую композицию](keyboard-layouts.md). Новый default capability fallback сохраняет текст без styles/emoji; старые calls выше не меняют поведения.
