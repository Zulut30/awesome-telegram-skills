"""Markup only: controller and transaction still validate callbacks on the server."""
from datetime import date, datetime, timedelta, timezone
import json
from telegram_patterns import CalendarMonth, TimeSlot
from telegram_patterns.aiogram import calendar_keyboard, time_slot_keyboard

month = CalendarMonth(2026, 10, 'UTC', [date(2026, 10, 6)])
calendar = calendar_keyboard(month, lambda day: 'calendar:' + day.isoformat())
assert calendar.inline_keyboard[0][0].callback_data == 'calendar:2026-10-06'
start = datetime(2026, 10, 6, 8, tzinfo=timezone.utc)
slots = time_slot_keyboard([TimeSlot('morning', start, start + timedelta(minutes=30))], 'UTC', lambda slot: 'time:' + slot.key)
assert slots.inline_keyboard[0][0].callback_data == 'time:morning'
print(json.dumps({'passed': True, 'case': 'bot_calendar', 'network': False,
                  'calendar_rows': len(calendar.inline_keyboard), 'slot_rows': len(slots.inline_keyboard)}))
