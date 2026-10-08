"""SDK-free keyboards as Bot API JSON: the same reply_markup for aiogram, python-telegram-bot or raw HTTP; no network."""
import json
from telegram_patterns import (MarkupPage, SelectionContext, SelectionMenu, SelectionOption, SelectionSpec, ValidationFailure,
                               force_reply_markup, inline_button, inline_markup, layout_rows, markup_page_number, paginated_markup,
                               remove_markup, reply_button, reply_markup, selection_markup)

buttons = [inline_button(name, callback_data=f'menu:{key}') for name, key in [('Каталог', 'catalog'), ('Помощь', 'help'), ('Назад', 'back')]]
menu = inline_markup(layout_rows(buttons, (2,)))
assert menu == {'inline_keyboard': [[{'text': 'Каталог', 'callback_data': 'menu:catalog'}, {'text': 'Помощь', 'callback_data': 'menu:help'}],
                                    [{'text': 'Назад', 'callback_data': 'menu:back'}]]}
icon = inline_button('Готово', callback_data='ok', icon_custom_emoji_id='5368324170671202286')
assert 'icon_custom_emoji_id' not in inline_markup([[icon]])['inline_keyboard'][0][0]  # no verified entitlement: text only
ask = reply_markup([[reply_button('Отправить контакт', request_contact=True)], ['Отмена']], one_time=True)
assert ask['keyboard'][0][0] == {'text': 'Отправить контакт', 'request_contact': True}
assert force_reply_markup('Ваше имя')['force_reply'] is True and remove_markup() == {'remove_keyboard': True, 'selective': False}
try:
    inline_markup([[inline_button('Приложение', web_app='https://example.com/app')]], chat_type='group')
except ValidationFailure:
    pass  # Mini App buttons need an ordinary private chat
else:
    raise AssertionError('Web App button accepted in a group')
page: MarkupPage = paginated_markup([(f'Товар {n}', f'item-{n}') for n in range(1, 8)], page=1, page_size=3)
assert (page.page, page.page_count) == (1, 3) and page.markup['inline_keyboard'][-1][1] == {'text': 'Далее →', 'callback_data': 'page:2'}
assert markup_page_number('page:2') == 2 and markup_page_number('page:../2') is None
draft = SelectionMenu(SelectionSpec([SelectionOption('a', 'Alpha'), SelectionOption('b', 'Beta')], max_selected=1),
                      SelectionContext(100, 7, 7, 50))
assert selection_markup(draft.state)['inline_keyboard'][0][0]['text'] == '□ Alpha'  # the same rows as selection_keyboard
print(json.dumps({'case': 'core_markup', 'passed': True, 'network': False}))
