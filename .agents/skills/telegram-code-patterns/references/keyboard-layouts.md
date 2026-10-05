# Композиции клавиатур 0.14.0

Optional aiogram extra, Python >=3.11 и предоставленный wheel `awesome-telegram-patterns` 0.14.0; native модели берите из установленного aiogram. Пакет не предполагается доступным в PyPI. Существующие `action_menu`, `inline_keyboard` и `reply_keyboard` сохраняют свои defaults и контракты. Новый API нужен, когда удобнее передать flat список и шаблон ширин, а не нарезать его вручную.

## Две, три и смешанные строки

```python
from telegram_patterns.aiogram import (
    ActionButton, KeyboardLayout, KeyboardCapabilities, action_layout, inline_layout, reply_layout,
)
from aiogram.types import InlineKeyboardButton, KeyboardButton

buttons = [ActionButton(str(i), 'item-'+str(i), style='primary') for i in range(1, 8)]
# Host проверил выбранный context/client/API; это не автоматическое определение.
caps = KeyboardCapabilities(chat_type='private', styles=True)
two = action_layout(buttons, KeyboardLayout([2]), capabilities=caps)
three = action_layout(buttons, KeyboardLayout([3]), capabilities=caps)
mixed = action_layout(buttons, KeyboardLayout([2,3,1]), capabilities=caps)
cyclic = action_layout(buttons, KeyboardLayout([2,1], repeat=True), capabilities=caps)
assert [len(row) for row in mixed.inline_keyboard] == [2,3,1,1]
assert [len(row) for row in cyclic.inline_keyboard] == [2,1,2,1,1]
# In existing handler: await message.answer('Выберите действие', reply_markup=mixed)
native = [InlineKeyboardButton(text='Документация', url='https://core.telegram.org/bots/api'),
          InlineKeyboardButton(text='Помощь', callback_data='menu:help')]
assert len(inline_layout(native).inline_keyboard[0]) == 2
reply = reply_layout(['Каталог', 'Помощь', KeyboardButton(text='Контакт', request_contact=True)],
                     KeyboardLayout([2,1]), capabilities=caps, placeholder='Выберите действие')
assert reply.keyboard[1][0].request_contact
```

`KeyboardLayout(widths=(2,), repeat=False)` копирует последовательность в tuple. Widths 1..8, pattern до 100, buttons 1..100 — лимиты компонента. repeat=False использует последнюю ширину для остатка; True повторяет весь pattern. Последний ряд может быть неполным; порядок кнопок не меняется. Empty layout требует явного использования прежнего `action_menu([])` или edit/removal API, а не пустых новых builders.

`action_layout(buttons, layout=KeyboardLayout(), prefix='act:', capabilities=KeyboardCapabilities(), force_reply=False)` принимает уникальные ActionButton keys, callback_data не длиннее 64 bytes. `inline_layout(buttons, layout=..., capabilities=..., invoice=False, force_reply=False)` принимает native InlineKeyboardButton, включая url/copy/pay/disabled; `reply_layout(buttons, layout=..., capabilities=..., resize=True, one_time=False, persistent=False, placeholder=None, selective=False, force_reply=False)` принимает text/KeyboardButton и сохраняет reply/input options. Результаты — native InlineKeyboardMarkup/ReplyKeyboardMarkup. Typed contract неверного input/type/context/presentation — ValidationFailure/InvalidType (ValueError/TypeError совместимость); HTTP/effect не выполняется.

## Styles и custom emoji

`KeyboardCapabilities(chat_type='private', business=False, styles=False, custom_emoji=False, emoji_entitlement_verified=False)` — immutable сведения, переданные host для конкретного chat/message route. Это не server probe и не разрешение callback. Если client/version неизвестны, default убирает style/emoji, сохраняя текст и действие. styles=True сохраняет только допустимые primary/success/danger. Для emoji нужны одновременно custom_emoji=True и проверенный host entitlement; Premium нажавшего пользователя этого не доказывает.

```python
from telegram_patterns.aiogram import ActionButton, KeyboardCapabilities, action_layout
item = ActionButton('Подтвердить','confirm',style='success',custom_emoji_id='12345')
unknown = action_layout([item]).inline_keyboard[0][0]
assert unknown.style is None and unknown.icon_custom_emoji_id is None
# Здесь capabilities — artificial fixture. Реальное право и ID проверяет backend.
verified = KeyboardCapabilities(styles=True,custom_emoji=True,emoji_entitlement_verified=True)
shown = action_layout([item], capabilities=verified).inline_keyboard[0][0]
assert shown.style == 'success' and shown.icon_custom_emoji_id == '12345'
```

Неверные RGB styles/emoji ID/unknown SDK fields отклоняются **до** fallback: он не скрывает ошибочный input. Native models копируются глубоко, descriptor/layout inputs не изменяются. Существующие builders по-прежнему сохраняют style по своему контракту и убирают неподтверждённую emoji; новый default text fallback не меняет старые вызовы.

Context guards сохраняются: pay/game в первом месте, pay только invoice; Web App в ordinary private; reply request только private; reply недоступен channels/Business; request IDs уникальны. Все runtime flags должны быть bool. Кнопка не выдаёт права, callback ACK не означает успех; host проверяет actor/object/version/idempotency. Copy/url/disabled не являются callback-событием. Лейблы должны сохранять смысл без цвета/иконки.

## Проверка и источники

`examples/python/keyboard_layouts.py` — закрытый SDK/StubSession пример, запускаемый full distribution verifier через installed wheel. Тесты сравнивают pattern с установленным InlineKeyboardBuilder.adjust, проверяют wire через SDK serializer, context refusals, immutable source и совместимость прежних calls. Это не live appearance/entitlement acceptance. Публичные symbols находятся в aiogram.__all__, imports без extra отклоняются ожидаемо; core остаётся SDK-free.

Частично сверено 2026-10-05: [InlineKeyboardButton](https://core.telegram.org/bots/api#inlinekeyboardbutton), [KeyboardButton](https://core.telegram.org/bots/api#keyboardbutton), [aiogram 3.31 KeyboardBuilder](https://docs.aiogram.dev/en/dev-3.x/utils/keyboard.html). Scope — styles/emoji/exact-one-action/context и adjust pattern semantics; установленный SDK дополнительно проверяет payload. Конкретную поддержку клиента и server entitlement проверяйте для своего проекта; дату других API источников это не меняет.
