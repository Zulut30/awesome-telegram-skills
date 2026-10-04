"""Строки 2/3, styles, reply-ввод и пагинация без доставки в Telegram."""
import json
from aiogram.types import InlineKeyboardButton
from telegram_patterns.aiogram import (
    ActionButton, ButtonStyle, MenuPage, action_keyboard, action_menu, paginated_menu, page_number,
    ChatType, inline_keyboard, reply_keyboard, input_prompt, remove_keyboard,
)

style: ButtonStyle = 'success'
context: ChatType = 'private'
items = [ActionButton(str(index), 'item-' + str(index), style=style) for index in range(1, 7)]
single = action_keyboard('Открыть', 'catalog', style='primary')
assert single.inline_keyboard[0][0].callback_data == 'act:catalog'
for columns in (2, 3):
    menu = action_menu(items, columns=columns)
    assert len(menu.inline_keyboard[0]) == columns
page: MenuPage = paginated_menu(items, page_size=3, columns=3)
assert (page.page, page.page_count, page.total_items) == (0, 2, 6)
assert page_number(page.markup.inline_keyboard[-1][0].callback_data) == 1
assert page_number('invalid') is None
rows = [[InlineKeyboardButton(text='Открыть', callback_data='act:catalog')]]
assert inline_keyboard(rows, chat_type=context).inline_keyboard[0][0].text == 'Открыть'
assert reply_keyboard([['Назад', 'Отмена']], chat_type=context, placeholder='Выберите действие').keyboard
assert input_prompt('Введите тему').force_reply and remove_keyboard().remove_keyboard
# Цвет — primary/success/danger, не RGB. Emoji требуют отдельного entitlement.
print(json.dumps({'passed': True, 'case': 'bot_keyboards', 'network': False}))
