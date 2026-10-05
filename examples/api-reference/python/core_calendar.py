"""SDK-free calendar, explicit DST choice, transaction and current booking."""
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from telegram_patterns import CalendarMonth, TimeSlot, resolve_local_time, SlotSchedule, SlotBooking, SQLiteSlotStore

month = CalendarMonth(2026, 10, 'Europe/Warsaw', [date(2026, 10, 25)])
assert month.allows(date(2026, 10, 25))
early = resolve_local_time(datetime(2026, 10, 25, 2, 30), 'Europe/Warsaw', fold=0)
late = resolve_local_time(datetime(2026, 10, 25, 2, 30), 'Europe/Warsaw', fold=1)
assert late - early == timedelta(hours=1)
slot = TimeSlot('early', early, early + timedelta(minutes=15))
with TemporaryDirectory(prefix='calendar public api ') as temporary:
    store = SQLiteSlotStore(Path(temporary) / 'slots.sqlite3',
                            authorize=lambda connection, actor, resource: actor == 42 and resource == 'room')
    store.initialize()
    schedule = store.publish('room', [slot], expected_revision=0)
    assert isinstance(schedule, SlotSchedule)
    now = datetime(2026, 10, 5, tzinfo=timezone.utc)
    receipt = store.reserve('room', 'early', actor_id=42, expected_revision=schedule.revision, operation_id='public-example', now=now)
    replay = store.reserve('room', 'early', actor_id=42, expected_revision=schedule.revision, operation_id='public-example', now=now)
    assert replay.replayed and replay.value == receipt.value
    booking = store.booking('room', receipt.value['booking_id'], actor_id=42)
    assert isinstance(booking, SlotBooking) and booking.status == 'active'
print(json.dumps({'passed': True, 'case': 'core_calendar', 'network': False,
                  'business_effects': 1, 'replayed': replay.replayed}))
