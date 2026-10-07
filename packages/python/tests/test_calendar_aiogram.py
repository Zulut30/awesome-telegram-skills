import unittest
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.methods import AnswerCallbackQuery, EditMessageText
from aiogram.types import InlineKeyboardMarkup, Update

from telegram_patterns import (
    CalendarMonth,
    InvalidCompletion,
    SelectionContext,
    SelectionMenu,
    SelectionOption,
    SelectionSpec,
    TimeSlot,
    ValidationFailure,
    resolve_local_time,
)
from telegram_patterns.aiogram import (
    KeyboardCapabilities,
    KeyboardLayout,
    calendar_keyboard,
    selection_router,
    time_slot_keyboard,
)
from telegram_patterns.testing import StubSession


class CalendarMarkupTests(unittest.TestCase):
    def test_default_fallback_has_weekdays_and_no_unavailable_callbacks(self):
        month = CalendarMonth(2026, 10, 'UTC', [date(2026, 10, 6), date(2026, 10, 7)], [date(2026, 10, 7)])
        calls = []

        def callback(day):
            calls.append(day)
            return 'date:' + day.isoformat()

        view = calendar_keyboard(month, callback)
        self.assertEqual([date(2026, 10, 6)], calls)
        self.assertEqual('Вт 6', view.inline_keyboard[0][0].text)
        self.assertIsNone(view.inline_keyboard[0][0].disabled)
        self.assertEqual('date:2026-10-06', view.inline_keyboard[0][0].callback_data)

    def test_full_grid_uses_real_disabled_actions_and_only_allowed_dates_callback(self):
        month = CalendarMonth(2026, 10, 'UTC', [date(2026, 10, 6)])
        view = calendar_keyboard(month, lambda day: 'date:' + day.isoformat(), disabled_buttons=True)
        self.assertTrue(all(len(row) == 7 for row in view.inline_keyboard))
        callbacks = [b for row in view.inline_keyboard for b in row if b.callback_data is not None]
        self.assertEqual(1, len(callbacks))
        self.assertEqual('6', callbacks[0].text)
        disabled = [b for row in view.inline_keyboard for b in row if b.disabled is not None]
        self.assertTrue(disabled)
        self.assertTrue(all(b.callback_data is None for b in disabled))
        wire = view.model_dump(exclude_none=True)
        self.assertEqual({}, wire['inline_keyboard'][0][0]['disabled'])

    def test_empty_month_and_navigation_validate_native_callback_budget(self):
        empty = CalendarMonth(2026, 10)
        self.assertEqual([], calendar_keyboard(empty, lambda day: 'unused').inline_keyboard)
        self.assertEqual(
            1, len(calendar_keyboard(empty, lambda day: 'unused', navigation=('prev', 'next')).inline_keyboard)
        )
        with self.assertRaises(ValidationFailure):
            calendar_keyboard(empty, lambda day: 'unused', navigation=('x' * 65, 'next'))
        month = CalendarMonth(2026, 10, 'UTC', [date(2026, 10, 6)])
        with self.assertRaises(ValidationFailure):
            calendar_keyboard(month, lambda day: '🗓' * 17)
        with self.assertRaises(ValidationFailure):
            calendar_keyboard(month, lambda day: 'date', capabilities=KeyboardCapabilities(business=True))

    def test_slots_omit_disabled_show_offsets_and_support_mixed_rows(self):
        wall = datetime(2026, 10, 25, 2, 30)
        starts = [resolve_local_time(wall, 'Europe/Warsaw', fold=fold) for fold in (0, 1)]
        slots = [TimeSlot(str(i), start, start + timedelta(minutes=15)) for i, start in enumerate(starts)]
        slots.append(TimeSlot('blocked', starts[1], starts[1] + timedelta(hours=1), False))
        view = time_slot_keyboard(slots, 'Europe/Warsaw', lambda slot: 'slot:' + slot.key, layout=KeyboardLayout((2,)))
        self.assertEqual([2], [len(row) for row in view.inline_keyboard])
        self.assertIn('UTC+02:00', view.inline_keyboard[0][0].text)
        self.assertIn('UTC+01:00', view.inline_keyboard[0][1].text)
        self.assertFalse(any(b.callback_data.endswith('blocked') for row in view.inline_keyboard for b in row))

    def test_slots_validate_duplicate_keys_capabilities_and_empty_timezone(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        slot = TimeSlot('one', start, start + timedelta(hours=1))
        with self.assertRaises(ValidationFailure):
            time_slot_keyboard([slot, slot], 'UTC', lambda s: 'x')
        with self.assertRaises(ValidationFailure):
            time_slot_keyboard([], '../invalid', lambda s: 'x')
        with self.assertRaises(ValidationFailure):
            time_slot_keyboard([slot], 'UTC', lambda s: 'x' * 65)
        with self.assertRaises(ValidationFailure):
            time_slot_keyboard([slot], 'UTC', lambda s: 'x', capabilities=KeyboardCapabilities(chat_type='channel'))


class CalendarRendererTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.context = SelectionContext(100, 42, 42, 100)
        self.menu = SelectionMenu(SelectionSpec([SelectionOption('d20261006', '6')], min_selected=1), self.context)
        self.session = StubSession().respond(AnswerCallbackQuery, True)

        def response(method):
            return {
                'message_id': 100,
                'date': 1,
                'chat': {'id': 42, 'type': 'private'},
                'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'},
                'text': method.text,
            }

        self.session.respond(EditMessageText, response)
        self.bot = Bot(
            '100:CALENDAR_RENDER_FIXTURE', session=self.session, default=DefaultBotProperties(parse_mode='HTML')
        )
        self.dp = Dispatcher()
        self.index = 0

    async def asyncTearDown(self):
        await self.dp.fsm.close()
        await self.bot.session.close()

    async def click(self, data, actor=42):
        self.index += 1
        update = Update.model_validate(
            {
                'update_id': self.index,
                'callback_query': {
                    'id': str(self.index),
                    'chat_instance': 'fixture',
                    'data': data,
                    'from': {'id': actor, 'is_bot': False, 'first_name': 'Owner'},
                    'message': {
                        'message_id': 100,
                        'date': 1,
                        'chat': {'id': 42, 'type': 'private'},
                        'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'},
                    },
                },
            }
        )
        await self.dp.feed_update(self.bot, update)

    async def test_custom_calendar_render_keeps_owner_stale_ack_and_plain_text(self):
        snapshots = []

        def render(state):
            snapshots.append(state)
            month = CalendarMonth(2026, 10, 'UTC', [date(2026, 10, 6)])
            return '<Calendar>\n' + month.text(), calendar_keyboard(month, lambda day: state.callback('s:d20261006'))

        self.dp.include_router(selection_router(self.menu, render=render))
        old = self.menu.state.callback('s:d20261006')
        await self.click(old, actor=43)
        self.assertFalse(snapshots)
        await self.click(old)
        await self.click(old)
        edits = [c for c in self.session.calls if isinstance(c, EditMessageText)]
        self.assertEqual(1, len(edits))
        self.assertIsNone(edits[0].parse_mode)
        self.assertIn('<Calendar>', edits[0].text)
        self.assertEqual(100, edits[0].message_id)
        self.assertEqual(3, sum(isinstance(c, AnswerCallbackQuery) for c in self.session.calls))
        self.assertEqual(1, len(snapshots))
        self.assertEqual(('d20261006',), self.menu.state.selected)

    async def test_invalid_renderer_retains_intent_and_does_not_edit_or_retry(self):
        self.dp.include_router(
            selection_router(self.menu, render=lambda state: ('', InlineKeyboardMarkup(inline_keyboard=[])))
        )
        old = self.menu.state.callback('s:d20261006')
        with self.assertRaises(InvalidCompletion):
            await self.click(old)
        self.assertEqual(('d20261006',), self.menu.state.selected)
        await self.click(old)
        self.assertFalse(any(isinstance(c, EditMessageText) for c in self.session.calls))


if __name__ == '__main__':
    unittest.main()
