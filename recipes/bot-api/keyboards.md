# Кнопки, клавиатуры и поле ввода

Готовый запускаемый бот: [keyboards_bot.py](../../examples/python/keyboards_bot.py). Все примеры используют установленный aiogram 3.31.0 и публичный API общей библиотеки. `reply_markup` передается в `await message.answer(...)` или другой подходящий метод SDK. Ограничения сверены 4 октября 2026 по [Bot API](https://core.telegram.org/bots/api#inlinekeyboardbutton).

## Две кнопки в ряд

```python
from aiogram.types import InlineKeyboardButton as Button
from telegram_patterns.aiogram import inline_keyboard

keyboard = inline_keyboard([
    [Button(text="Каталог", callback_data="menu:catalog"), Button(text="Помощь", callback_data="menu:help")],
    [Button(text="Назад", callback_data="menu:back"), Button(text="Закрыть", callback_data="menu:close")],
])
# await message.answer("Выберите действие", reply_markup=keyboard)
```

Внешний список — строки, внутренний — кнопки одной строки. Получится `Каталог | Помощь`, затем `Назад | Закрыть`.

## Три кнопки в ряд и смешанная раскладка

```python
buttons = [Button(text=str(n), callback_data=f"item:{n}") for n in range(1, 7)]
three = inline_keyboard([buttons[:3], buttons[3:]])
mixed = inline_keyboard([buttons[:1], buttons[1:3], buttons[3:]])
```

Для списка callback actions с одинаковой шириной уже есть `action_menu(buttons, columns=2)` / `columns=3` и пагинация `paginated_menu`. Explicit `inline_keyboard` нужен для разных native actions/размеров строк. До 100 кнопок и 1–8 в строке — ограничения нашего компонента; это не заявление об универсальном лимите Telegram.

## Цвета и custom emoji

```python
colors = inline_keyboard([[
    Button(text="Основная", callback_data="choice:main", style="primary"),
    Button(text="Подтвердить", callback_data="choice:confirm", style="success"),
    Button(text="Отмена", callback_data="choice:cancel", style="danger"),
]])
```

`primary` — синий, `success` — зеленый, `danger` — красный. Произвольные RGB/CSS цвета нативных кнопок не задаются; вид и поддержка зависят от клиента. `style=None` оставляет оформление клиенту.

```python
# Заменить действительным ID из getCustomEmojiStickers/проверенного источника.
candidate = Button(text="Готово", callback_data="choice:ok", icon_custom_emoji_id="123456789", style="success")
safe_fallback = inline_keyboard([[candidate]])  # Иконка удаляется; исходный model не изменяется.
# Только после проверки entitlement БОТА и ID в данном контексте:
# with_icon = inline_keyboard([[candidate]], emoji_entitlement_verified=True)
```

Premium нажавшего пользователя не дает entitlement боту. Проверяются Fragment additional username либо Premium владельца для непосредственно отправленных ботом private/group/supergroup сообщений. Иконка кнопки и `custom_emoji` entity текста — разные поля. Для других контекстов условия проверяются отдельно.

## Reply-клавиатура под полем ввода

```python
from aiogram.types import KeyboardButton
from telegram_patterns.aiogram import reply_keyboard, remove_keyboard, input_prompt

reply = reply_keyboard([["Каталог", "Помощь"], ["Закрыть клавиатуру"]],
                       resize=True, one_time=False, persistent=False,
                       placeholder="Выберите действие")
# await message.answer("Меню", reply_markup=reply)
# await message.answer("Клавиатура скрыта", reply_markup=remove_keyboard())
```

Reply-кнопка отправляет текст или service data как `message`. Пользователь может набрать такой же текст вручную: это не доказательство нажатия и не авторизация. `one_time=True` просит клиент скрыть клавиатуру после использования; это не удаление разметки. Reply-клавиатуры не поддерживаются в channels/Business messages. Передавайте фактические `chat_type` / `business`; helper проверяет указанный контекст, не запрашивает его у Telegram.

## Контакт, геопозиция, опрос, users/chat

```python
from aiogram.types import KeyboardButtonPollType, KeyboardButtonRequestUsers, KeyboardButtonRequestChat

requests = reply_keyboard([
    [KeyboardButton(text="Мой контакт", request_contact=True), KeyboardButton(text="Геопозиция", request_location=True)],
    [KeyboardButton(text="Опрос", request_poll=KeyboardButtonPollType(type="regular"))],
    [KeyboardButton(text="Пользователи", request_users=KeyboardButtonRequestUsers(request_id=1, max_quantity=3)),
     KeyboardButton(text="Группа", request_chat=KeyboardButtonRequestChat(request_id=2, chat_is_channel=False))],
], chat_type="private", one_time=True)
```

Запросы доступны в личном чате. Обработчики: `F.contact`, `F.location`, `F.poll`, `F.users_shared`, `F.chat_shared`. Проверяйте ожидающего actor, контекст и request_id; shared ID не дает автоматически доступа к истории/профилю/чату. Для собственного контакта сверяйте `contact.user_id == message.from_user.id`; отсутствие совпадения не доказывает владение номером. request_id — уникальный внутри клавиатуры signed 32-bit integer. `request_managed_bot` поддерживается native `KeyboardButtonRequestManagedBot`; [BotFather/management prerequisites](https://core.telegram.org/bots/api#keyboardbuttonrequestmanagedbot) проверяются отдельно.

## Ввод и принудительный ответ

```python
prompt_markup = input_prompt("Ваше имя")
# prompt = await message.answer("Как вас называть?", reply_markup=prompt_markup)
# Сохранить (chat_id, actor_id, prompt.message_id).
# При ответе сверить actor и reply_to_message.message_id, затем проверить текст.
```

`ForceReply` открывает клиентский интерфейс ответа; он не заставляет пользователя ответить и не валидирует текст. `input_field_placeholder` — подсказка 1–64 символа (helper консервативно считает UTF-16 units), не произвольный дизайн. В Bot API 10.3 есть `force_reply` и у inline/reply markup; inline flag нельзя менять при редактировании этой клавиатуры. Пользовательские поля, rich input, цвета/верстка формы делаются в Mini App.

## Ссылка, копирование, disabled, inline mode и Mini App

```python
from aiogram.types import CopyTextButton, DisabledButton, WebAppInfo

actions = inline_keyboard([
    [Button(text="Документация", url="https://core.telegram.org/bots/api"),
     Button(text="Копировать", copy_text=CopyTextButton(text="READY-CODE"))],
    [Button(text="Искать inline", switch_inline_query="query"),
     Button(text="Недоступно", disabled=DisabledButton())],
])
app_button = inline_keyboard([[Button(text="Открыть приложение", web_app=WebAppInfo(url="https://example.invalid/replace"))]],
                             chat_type="private", business=False)
```

Inline button содержит ровно одно action; callback_data — 1–64 UTF-8 bytes. Copy ограничен 256 символами, helper консервативно считает UTF-16. URL/copy/switch-inline/disabled не порождают обычный callback_query о нажатии. Inline mode включается у BotFather, имеет отдельный `inline_query` handler; chosen result требует своей настройки. Native web_app button — HTTPS и ordinary private bot chat; ссылка примера заменяется вашим deployment. В Mini App сервер проверяет raw initData.

Другие native actions (`login_url`, `switch_inline_query_current_chat`, `switch_inline_query_chosen_chat`, `callback_game`, `pay`) передаются тем же helper как SDK models. Pay/game должны быть первыми в первой строке, pay — только на invoice (`invoice=True`). [Invoice](methods/sendInvoice.md), [LoginUrl](https://core.telegram.org/bots/api#loginurl), [Games](https://core.telegram.org/bots/api#games) имеют собственные требования; helper не подтверждает payment или доступ.

## Обновление меню и клавиатура в меню бота

Пример handler с ACK, привязкой владельца и защитой от повторного редактирования есть в `create_app` бота. Подходящие вызовы SDK: `await message.edit_reply_markup(reply_markup=...)` или `await message.edit_text(..., reply_markup=...)`. Inaccessible/inline message не гарантирует доступный chat/message; сервер проверяет права и актуальность до частного эффекта. Изменение оформления нельзя считать выполнением бизнес-операции.

Для удаления inline-кнопок у сообщения: `await message.edit_reply_markup(reply_markup=None)`. Это отличается от `ReplyKeyboardRemove`, который убирает reply-клавиатуру под вводом. Explicit row helper принимает непустое меню; для удаления используйте native edit, а не пустые rows.

Для нижней кнопки меню бота используйте [setChatMenuButton](methods/setChatMenuButton.md) с `MenuButtonWebApp`/`MenuButtonCommands`. Список команд задается [setMyCommands](methods/setMyCommands.md), с явными scope/language при необходимости. Эти настройки отличаются от reply-клавиатуры конкретного сообщения.
