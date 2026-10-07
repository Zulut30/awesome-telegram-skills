"""Component texts come from the ru/en catalog; an application can replace any string; handlers hold no phrases."""

import ast
import re
import string
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery, GetMe, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

import telegram_patterns
from telegram_patterns import (
    CalendarMonth,
    RichMessageBuilder,
    SelectionContext,
    SelectionMenu,
    SelectionOption,
    SelectionSpec,
    Texts,
    ValidationFailure,
    default_texts,
    paginated_markup,
    safe_error_report,
    selection_markup,
)
from telegram_patterns.aiogram import (
    ActionButton,
    ActionResult,
    FileField,
    InvalidField,
    MessageNavigation,
    NavigationScreen,
    NumberField,
    TextField,
    calendar_keyboard,
    callback_router,
    paginated_menu,
    selection_keyboard,
    text_form_router,
)
from telegram_patterns.testing import StubSession

PACKAGE = Path(telegram_patterns.__file__).parent
DATE = datetime(2026, 10, 7, tzinfo=timezone.utc)
# Developer tooling (CLI, doctor, project templates) speaks Russian to the developer, not to bot users.
TOOLING = {'texts.py', 'cli.py', 'diagnostics.py', 'recipes.py', 'starter.py', 'starter_components.py'}


def fields(template):
    return {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}


def phrases(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.search('[А-Яа-яЁё]', node.value)
        and id(node) not in docstrings
    ]


class CatalogTests(unittest.TestCase):
    def test_locales_share_keys_and_placeholders(self):
        ru, en = default_texts('ru'), default_texts('en')
        self.assertEqual(set(ru), set(en))
        self.assertGreaterEqual(len(ru), 125)
        for key in ru:
            self.assertEqual(fields(ru[key]), fields(en[key]), key)
            self.assertNotRegex(en[key], '[А-Яа-яЁё]', key)
        with self.assertRaises(TypeError):
            ru['form.submit'] = 'x'

    def test_handlers_hold_no_user_phrases(self):
        found = {
            path.relative_to(PACKAGE).as_posix(): len(phrases(path))
            for path in sorted(PACKAGE.rglob('*.py'))
            if phrases(path)
        }
        self.assertLessEqual(set(found), TOOLING, 'move user-facing strings to telegram_patterns.texts')
        self.assertGreaterEqual(found['texts.py'], 125)

    def test_overrides_keep_placeholders_and_insert_values_literally(self):
        texts = Texts('en', {'form.step': '[{number} of {total}] {prompt}'})
        self.assertEqual(texts('form.step', number=1, total=2, prompt='Name {x}?'), '[1 of 2] Name {x}?')
        self.assertEqual(texts('form.submit'), 'Submit')
        merged = texts.with_overrides({'form.submit': 'Send'})
        self.assertEqual(
            (merged('form.submit'), merged('form.step', number=1, total=1, prompt='?')), ('Send', '[1 of 1] ?')
        )
        for overrides, message in (
            ({'form.sbmit': 'Send'}, 'Unknown text key'),
            ({'form.step': 'Step {number}'}, 'must use exactly'),
            ({'form.submit': 'Send {now}'}, 'must use exactly'),
            ({'form.submit': '  '}, 'nonempty'),
            ({'form.submit': 'x' * 1025}, 'at most'),
            ({'form.submit': 'Send {'}, 'unbalanced'),
        ):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValidationFailure, message):
                Texts('en', overrides)
        with self.assertRaisesRegex(ValidationFailure, 'ru or en'):
            Texts('de')
        with self.assertRaisesRegex(ValidationFailure, 'needs the value'):
            Texts()('form.step', number=1)
        self.assertEqual(Texts().month(10), 'Октябрь')
        self.assertEqual(Texts('en').weekdays()[0], 'Mo')


class CoreLocaleTests(unittest.TestCase):
    def test_selection_speaks_through_its_spec(self):
        options = [SelectionOption('tea', 'Tea'), SelectionOption('cake', 'Cake')]
        context = SelectionContext(100, 42, 42, 1)
        english = SelectionMenu(SelectionSpec(options, texts=Texts('en')), context)
        self.assertEqual(english.state.spec.filters, {'all': 'All'})
        self.assertEqual(english.state.spec.confirm_text, 'Confirm action')
        self.assertEqual(english.state.text(), 'Choose options.\nSelected: nothing\nQuantity: 1\nFilter: All')
        result = english.apply(english.state.callback('s:tea'), context)
        self.assertEqual((result.status, result.text), ('accepted', 'The choice is updated.'))
        self.assertEqual(
            english.apply(english.state.callback('s:tea'), SelectionContext(100, 43, 42, 1)).text,
            'This choice belongs to another user.',
        )
        labels = [b['text'] for row in selection_markup(english.state)['inline_keyboard'] for b in row]
        self.assertIn('Cancel', labels)
        self.assertIn('Confirm action', labels)
        russian = SelectionMenu(SelectionSpec(options), context)
        self.assertEqual(russian.state.spec.filters, {'all': 'Все'})
        self.assertTrue(russian.state.text().startswith('Выберите варианты.\nВыбрано: ничего'))
        custom = SelectionSpec(options, confirm_text='Order', texts=Texts('en', {'selection.cancel': 'Never mind'}))
        menu = SelectionMenu(custom, context)
        menu.apply(menu.state.callback('s:tea'), context)
        menu.apply(menu.state.callback('ask'), context)
        confirming = [b['text'] for row in selection_markup(menu.state)['inline_keyboard'] for b in row]
        self.assertEqual(confirming, ['Yes: Order', 'Change choice', 'Never mind'])

    def test_calendar_pagination_errors_and_rich_fallback(self):
        month = CalendarMonth(2026, 10, available_dates=[date(2026, 10, 9)])
        self.assertTrue(month.text(Texts('en')).startswith('October 2026 · UTC\nMo Tu We Th Fr Sa Su\n'))
        self.assertTrue(month.text().startswith('Октябрь 2026 · UTC\nПн Вт Ср Чт Пт Сб Вс\n'))
        self.assertTrue(month.text(Texts('en')).endswith('Pick a date with the buttons below.'))
        page = paginated_markup([(str(n), str(n)) for n in range(8)], texts=Texts('en'))
        self.assertEqual(page.markup['inline_keyboard'][-1][0]['text'], 'Next →')
        report = safe_error_report(ValidationFailure('secret detail'), texts=Texts('en'))
        self.assertEqual(report.message, 'Check the input data.')
        self.assertEqual(safe_error_report(ValidationFailure('x')).message, 'Проверьте входные данные.')
        override = Texts('en', {'error.unknown-outcome-write': 'Still checking; see your orders.'})
        self.assertEqual(
            safe_error_report(RuntimeError(), operation='write', texts=override).message,
            'Still checking; see your orders.',
        )
        fallback = RichMessageBuilder(texts=Texts('en')).document('file-id').build().fallback()
        self.assertIn('Document', fallback.text)
        self.assertIn('Документ', RichMessageBuilder().document('file-id').build().fallback().text)


class AdapterLocaleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sent = []
        self.session = (
            StubSession()
            .respond(SendMessage, self.reply)
            .respond(AnswerCallbackQuery, True)
            .respond(GetMe, User(id=100, is_bot=True, first_name='Fixture', username='texts_bot'))
        )
        self.bot = Bot('100:TEXTS_FIXTURE', session=self.session, default=DefaultBotProperties(parse_mode='HTML'))
        self.serial = 0

    async def asyncTearDown(self):
        await self.bot.session.close()

    def reply(self, method):
        self.sent.append(method)
        return Message(
            message_id=1000 + len(self.sent),
            date=DATE,
            chat=Chat(id=method.chat_id, type='private'),
            from_user=User(id=100, is_bot=True, first_name='Fixture'),
            text=method.text,
            reply_markup=method.reply_markup,
        )

    def update(self, text):
        self.serial += 1
        message = Message(
            message_id=self.serial,
            date=DATE,
            chat=Chat(id=42, type='private'),
            from_user=User(id=42, is_bot=False, first_name='Fixture'),
            text=text,
        )
        return Update(update_id=self.serial, message=message)

    async def test_text_form_in_english_with_one_replaced_phrase(self):
        texts = Texts('en', {'form.length': 'Keep it under {maximum} characters, please.'})
        dp = Dispatcher(events_isolation=SimpleEventIsolation())

        async def submit(submission):
            return 'Thanks!'

        dp.include_router(
            text_form_router([TextField('topic', 'Topic', 'Which topic?', max_length=5)], submit, texts=texts)
        )
        for value in ('/apply', 'far too long', 'Bots'):
            await dp.feed_update(self.bot, self.update(value))
        await dp.fsm.close()
        self.assertEqual(
            [method.text for method in self.sent],
            [
                'Step 1/1. Which topic?\n/back — go back · /cancel — cancel',
                'Keep it under 5 characters, please.',
                'Step 1/1. Which topic?\n/back — go back · /cancel — cancel',
                'Check your answers:\nTopic: Bots\n/back — edit · /cancel — cancel',
            ],
        )
        self.assertEqual(self.sent[-1].reply_markup.inline_keyboard[0][0].text, 'Submit')

    async def test_fields_navigation_keyboards_and_callback_router(self):
        with self.assertRaises(InvalidField) as caught:
            NumberField('amount', 'Amount', 'How much?', decimal_places=1).restore('1.25')
        self.assertEqual(str(caught.exception), 'Допустимо до 1 знаков после разделителя.')
        self.assertEqual(caught.exception.text(Texts('en')), 'Up to 1 digits are allowed after the separator.')
        self.assertEqual(InvalidField('Choose Python.').text(Texts('en')), 'Choose Python.')
        with self.assertRaises(TypeError):
            InvalidField('message', key='field.date_range')
        document = {'file_id': 'f', 'file_unique_id': 'u', 'file_name': None, 'mime_type': None, 'file_size': 10}
        self.assertEqual(FileField('file', 'File', 'Send a file').display(document, Texts('en')), 'Document (10 bytes)')
        self.assertEqual(FileField('file', 'File', 'Send a file').display(document), 'Документ (10 байт)')

        page = paginated_menu([ActionButton(str(n), str(n)) for n in range(8)], page=1, texts=Texts('en'))
        self.assertEqual(page.markup.inline_keyboard[-1][0].text, '← Back')
        month = CalendarMonth(2026, 10, available_dates=[date(2026, 10, 9)])
        markup = calendar_keyboard(month, lambda day: f'day:{day:%d}', navigation=('p', 'n'), texts=Texts('en'))
        self.assertEqual(
            [b.text for row in markup.inline_keyboard for b in row], ['Fr 9', 'Previous month', 'Next month']
        )
        options = [SelectionOption('tea', 'Tea')]
        menu = SelectionMenu(SelectionSpec(options, texts=Texts('en')), SelectionContext(100, 42, 42, 1))
        self.assertEqual(selection_keyboard(menu.state).inline_keyboard[-1][-1].text, 'Cancel')

        screens = [NavigationScreen('home', 'Home', [ActionButton('Help', 'help')]), NavigationScreen('help', 'Help')]
        await MessageNavigation(screens, texts=Texts('en'), refresh_text='Reload').open(self.bot, 42, 42)
        self.assertEqual(
            [b.text for row in self.sent[-1].reply_markup.inline_keyboard for b in row], ['Help', 'Reload']
        )
        nav = MessageNavigation(screens, texts=Texts('en'))
        await nav.open(self.bot, 42, 43)
        self.assertEqual(
            [b.text for row in self.sent[-1].reply_markup.inline_keyboard for b in row], ['Help', 'Refresh']
        )
        query = CallbackQuery(
            id='q1', chat_instance='c', from_user=User(id=42, is_bot=False, first_name='F'), data='nav:x'
        )
        result = await nav.handle(query.as_(self.bot))
        self.assertEqual((result.status, result.text), ('stale', 'Invalid button. Open /menu.'))

        notes = []

        async def execute(action):
            raise AssertionError('malformed data must not execute')

        async def notify(callback, result):
            notes.append(result)

        dp = Dispatcher()
        dp.include_router(callback_router(execute, notify, texts=Texts('en', {'action.stale': 'Menu expired.'})))
        bad = CallbackQuery(
            id='q2', chat_instance='c', from_user=User(id=42, is_bot=False, first_name='F'), data='act:no way'
        )
        await dp.feed_update(self.bot, Update(update_id=99, callback_query=bad))
        await dp.fsm.close()
        self.assertEqual(notes, [ActionResult('stale', 'Menu expired.')])


if __name__ == '__main__':
    unittest.main()
