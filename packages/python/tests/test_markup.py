import json
import unittest

from aiogram.types import CopyTextButton, DisabledButton, KeyboardButton, WebAppInfo
from aiogram.types import InlineKeyboardButton as Button

from telegram_patterns import (
    InvalidType,
    ValidationFailure,
    force_reply_markup,
    inline_button,
    inline_markup,
    layout_rows,
    markup_page_number,
    paginated_markup,
    remove_markup,
    reply_button,
    reply_markup,
)
from telegram_patterns.aiogram import (
    ActionButton,
    KeyboardLayout,
    inline_keyboard,
    inline_layout,
    input_prompt,
    page_number,
    paginated_menu,
    remove_keyboard,
    reply_keyboard,
)


def wire(markup):
    return json.loads(markup.model_dump_json(exclude_none=True))


class MarkupTests(unittest.TestCase):
    def test_same_json_as_the_aiogram_builders(self):
        items = [inline_button(str(n), callback_data=f'item:{n}') for n in range(1, 7)]
        native = [Button(text=str(n), callback_data=f'item:{n}') for n in range(1, 7)]
        for widths in ((2,), (3,), (1, 2, 3)):
            self.assertEqual(
                inline_markup(layout_rows(items, widths)), wire(inline_layout(native, KeyboardLayout(widths)))
            )
        self.assertEqual(
            inline_markup(
                [
                    [
                        inline_button('Основная', callback_data='a', style='primary'),
                        inline_button('Отмена', callback_data='c', style='danger'),
                    ]
                ]
            ),
            wire(
                inline_keyboard(
                    [
                        [
                            Button(text='Основная', callback_data='a', style='primary'),
                            Button(text='Отмена', callback_data='c', style='danger'),
                        ]
                    ]
                )
            ),
        )
        self.assertEqual(
            inline_markup(
                [
                    [inline_button('Копировать', copy_text='READY-CODE'), inline_button('Недоступно', disabled=True)],
                    [
                        inline_button('Документация', url='https://core.telegram.org/bots/api'),
                        inline_button('Приложение', web_app='https://example.com/app'),
                    ],
                ]
            ),
            wire(
                inline_keyboard(
                    [
                        [
                            Button(text='Копировать', copy_text=CopyTextButton(text='READY-CODE')),
                            Button(text='Недоступно', disabled=DisabledButton()),
                        ],
                        [
                            Button(text='Документация', url='https://core.telegram.org/bots/api'),
                            Button(text='Приложение', web_app=WebAppInfo(url='https://example.com/app')),
                        ],
                    ]
                )
            ),
        )
        self.assertEqual(
            reply_markup([['Каталог', 'Помощь'], ['Закрыть']], placeholder='Выберите действие'),
            wire(reply_keyboard([['Каталог', 'Помощь'], ['Закрыть']], placeholder='Выберите действие')),
        )
        self.assertEqual(
            reply_markup(
                [[reply_button('Контакт', request_contact=True), reply_button('Где я', request_location=True)]],
                one_time=True,
            ),
            wire(
                reply_keyboard(
                    [
                        [
                            KeyboardButton(text='Контакт', request_contact=True),
                            KeyboardButton(text='Где я', request_location=True),
                        ]
                    ],
                    one_time=True,
                )
            ),
        )
        self.assertEqual(force_reply_markup('Ваше имя'), wire(input_prompt('Ваше имя')))
        self.assertEqual(remove_markup(), wire(remove_keyboard()))

    def test_emoji_icon_needs_verified_entitlement(self):
        button = inline_button('Готово', callback_data='ok', icon_custom_emoji_id='123456789')
        self.assertEqual(inline_markup([[button]]), {'inline_keyboard': [[{'text': 'Готово', 'callback_data': 'ok'}]]})
        self.assertEqual(
            inline_markup([[button]], emoji_entitlement_verified=True)['inline_keyboard'][0][0]['icon_custom_emoji_id'],
            '123456789',
        )
        self.assertIn('icon_custom_emoji_id', button, 'the source button is not changed')

    def test_invalid_buttons_and_contexts_are_refused(self):
        for make in (
            lambda: inline_button('x'),
            lambda: inline_button('x', callback_data='a', url='https://a.b'),
            lambda: inline_button('x', callback_data='я' * 33),
            lambda: inline_button('x', url='ftp://a.b'),
            lambda: inline_button('x', web_app='http://a.b'),
            lambda: inline_button(' ', callback_data='a'),
            lambda: inline_button('x', callback_data='a', style='blue'),
            lambda: inline_button('x', copy_text='a' * 257),
            lambda: reply_button('x', request_contact=True, request_location=True),
            lambda: reply_markup([['x']], placeholder='a' * 65),
            lambda: layout_rows([1], (9,)),
            lambda: inline_markup([[inline_button(str(n), callback_data=str(n)) for n in range(9)]]),
            lambda: inline_markup([[inline_button('app', web_app='https://a.b')]], chat_type='group'),
            lambda: reply_markup([[reply_button('Контакт', request_contact=True)]], business=True),
        ):
            with self.assertRaises(ValidationFailure):
                make()
        for make in (
            lambda: inline_button('x', disabled=1),
            lambda: inline_markup('abc'),
            lambda: reply_markup([['x']], resize=1),
        ):
            with self.assertRaises(InvalidType):
                make()

    def test_pagination_matches_the_aiogram_menu(self):
        items = [(f'Компонент {n}', f'item-{n}') for n in range(1, 8)]
        native = [ActionButton(text, key, style='primary') for text, key in items]
        for page in (0, 1, 2, 9):
            core = paginated_markup(items, page=page, page_size=3, page_prefix='catalog-page:', style='primary')
            menu = paginated_menu(native, page=page, page_size=3, page_prefix='catalog-page:')
            self.assertEqual(
                (core.markup, core.page, core.page_count, core.total_items),
                (wire(menu.markup), menu.page, menu.page_count, menu.total_items),
            )
        for data in ('catalog-page:2', 'catalog-page:02', 'catalog-page:-1', 'other:1', None, 'catalog-page:x'):
            self.assertEqual(
                markup_page_number(data, prefix='catalog-page:'), page_number(data, prefix='catalog-page:')
            )
        with self.assertRaises(ValidationFailure):
            paginated_markup([('a', 'k'), ('b', 'k')])

    def test_selection_markup_matches_the_aiogram_keyboard(self):
        from telegram_patterns import SelectionContext, SelectionMenu, SelectionOption, SelectionSpec, selection_markup
        from telegram_patterns.aiogram import selection_keyboard

        spec = SelectionSpec(
            [SelectionOption('alpha', 'Alpha', ['basic']), SelectionOption('beta', 'Beta', ['extra'])],
            toggles={'notify': 'Уведомлять'},
            filters={'all': 'Все', 'basic': 'Основные', 'extra': 'Доп.'},
            quantity_min=1,
            quantity_max=3,
            min_selected=1,
            max_selected=2,
            confirm_text='Подтвердить',
        )
        context = SelectionContext(100, 7, 7, 50)
        menu = SelectionMenu(spec, context)
        self.assertEqual(selection_markup(menu.state), wire(selection_keyboard(menu.state)))
        menu.apply(menu.state.callback('s:alpha'), context)
        menu.apply(menu.state.callback('ask'), context)
        self.assertEqual(menu.state.phase, 'confirming')
        self.assertEqual(selection_markup(menu.state), wire(selection_keyboard(menu.state)))
        self.assertIn('style', json.dumps(selection_markup(menu.state, styles=True)))

    def test_layout_rows_repeat_and_tail(self):
        self.assertEqual(layout_rows(list(range(7)), (1, 2)), [[0], [1, 2], [3, 4], [5, 6]])
        self.assertEqual(layout_rows(list(range(7)), (1, 2), repeat=True), [[0], [1, 2], [3], [4, 5], [6]])


if __name__ == '__main__':
    unittest.main()
