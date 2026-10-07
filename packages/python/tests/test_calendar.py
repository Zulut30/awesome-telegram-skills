from __future__ import annotations

from dataclasses import FrozenInstanceError
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import multiprocessing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram_patterns import (CalendarMonth, TimeSlot, resolve_local_time, SlotBooking, SlotSchedule,
                               SQLiteSlotStore, ConflictFailure, InvalidType, OperationConflict,
                               PermissionDenied, UnsupportedCapability, ValidationFailure)

NOW = datetime(2026, 10, 5, 8, tzinfo=timezone.utc)
START = NOW + timedelta(days=1)


def allow(_connection, actor, resource):
    return actor in (42, 43) and resource in ('room', 'other')


def competing_worker(database, barrier, queue, actor, operation, slot, revision):
    try:
        store = SQLiteSlotStore(database, authorize=allow)
        barrier.wait(timeout=15)
        result = store.reserve('room', slot, actor_id=actor, expected_revision=revision, operation_id=operation, now=NOW)
        queue.put(('ok', result.replayed, result.value['booking_id']))
    except ConflictFailure:
        queue.put(('conflict', False, None))
    except BaseException as error:
        queue.put(('error', type(error).__name__, None))


class CalendarTests(unittest.TestCase):
    def test_gap_is_rejected_and_ambiguous_time_requires_explicit_fold(self):
        with self.assertRaises(ValidationFailure):
            resolve_local_time(datetime(2026, 3, 29, 2, 30), 'Europe/Warsaw')
        wall = datetime(2026, 10, 25, 2, 30)
        with self.assertRaises(ValidationFailure): resolve_local_time(wall, 'Europe/Warsaw')
        early = resolve_local_time(wall, 'Europe/Warsaw', fold=0)
        late = resolve_local_time(wall, 'Europe/Warsaw', fold=1)
        self.assertEqual(datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc), early)
        self.assertEqual(timedelta(hours=1), late - early)

    def test_non_hour_transition_and_skipped_whole_date(self):
        with self.assertRaises(ValidationFailure): resolve_local_time(datetime(2026, 10, 4, 2, 15), 'Australia/Lord_Howe')
        wall = datetime(2026, 4, 5, 1, 45)
        self.assertEqual(timedelta(minutes=30), resolve_local_time(wall, 'Australia/Lord_Howe', fold=1) - resolve_local_time(wall, 'Australia/Lord_Howe', fold=0))
        with self.assertRaises(ValidationFailure): resolve_local_time(datetime(2011, 12, 30, 12), 'Pacific/Apia')

    def test_ordinary_and_utc_times_no_implicit_fold_or_process_tz(self):
        wall = datetime(2026, 10, 6, 10, 15)
        self.assertEqual(START.replace(minute=15), resolve_local_time(wall, 'Europe/Warsaw'))
        self.assertEqual(wall.replace(tzinfo=timezone.utc), resolve_local_time(wall, 'UTC'))
        self.assertEqual(resolve_local_time(wall, 'UTC'), resolve_local_time(wall, 'UTC', fold=1))
        for fold in (True, -1, 2, '0'):
            with self.assertRaises(ValidationFailure): resolve_local_time(wall, 'UTC', fold=fold)
        with self.assertRaises(InvalidType): resolve_local_time(NOW, 'UTC')

    def test_missing_zone_is_explicit_and_utc_still_works(self):
        with patch('telegram_patterns.calendar.ZoneInfo', side_effect=ZoneInfoNotFoundError):
            with self.assertRaises(UnsupportedCapability): resolve_local_time(datetime(2026, 1, 1), 'Europe/Warsaw')
            self.assertEqual(timezone.utc, resolve_local_time(datetime(2026, 1, 1), 'UTC').tzinfo)
        with self.assertRaises(ValidationFailure): resolve_local_time(datetime(2026, 1, 1), '../Europe/Warsaw')

    def test_slots_normalize_utc_and_show_offsets_for_duplicate_wall_times(self):
        wall = datetime(2026, 10, 25, 2, 30)
        start = resolve_local_time(wall, 'Europe/Warsaw', fold=0)
        later = resolve_local_time(wall, 'Europe/Warsaw', fold=1)
        one = TimeSlot('early', start, start + timedelta(minutes=15))
        two = TimeSlot('late', later, later + timedelta(minutes=15))
        self.assertIn('UTC+02:00', one.label('Europe/Warsaw'))
        self.assertIn('UTC+01:00', two.label('Europe/Warsaw'))
        self.assertNotEqual(one.label('Europe/Warsaw'), two.label('Europe/Warsaw'))
        transition = TimeSlot('crossing', start, later + timedelta(minutes=15)).label('Europe/Warsaw')
        self.assertIn('UTC+02:00', transition); self.assertIn('UTC+01:00', transition)
        normalized = TimeSlot('x', NOW.astimezone(ZoneInfo('Asia/Kolkata')), START)
        self.assertEqual(NOW, normalized.start)
        with self.assertRaises(FrozenInstanceError): normalized.key = 'changed'

    def test_invalid_slots_naive_reversed_and_imaginary_wall_time(self):
        for key, start, end, enabled in [('x', NOW, NOW, True), ('bad:key', NOW, START, True), ('x', NOW.replace(tzinfo=None), START, True), ('x', NOW, START, 1)]:
            with self.assertRaises(ValidationFailure): TimeSlot(key, start, end, enabled)
        imaginary = datetime(2026, 3, 29, 2, 30, tzinfo=ZoneInfo('Europe/Warsaw'))
        with self.assertRaises(ValidationFailure): TimeSlot('gap', imaginary, START)

    def test_leap_month_grid_blocked_days_and_snapshot(self):
        dates = [date(2028, 2, 28), date(2028, 2, 29)]
        month = CalendarMonth(2028, 2, 'Europe/Warsaw', dates, [dates[0]])
        dates.clear()
        self.assertTrue(month.allows(date(2028, 2, 29)))
        self.assertFalse(month.allows(date(2028, 2, 28)))
        self.assertFalse(month.allows(datetime(2028, 2, 29)))
        self.assertTrue(all(len(row) == 7 for row in month.weeks))
        self.assertEqual(29, sum(day is not None for week in month.weeks for day in week))
        self.assertIn('Февраль 2028', month.text())

    def test_empty_month_limits_and_date_boundaries(self):
        self.assertIn('Нет доступных дат', CalendarMonth(2026, 10).text())
        self.assertEqual(31, sum(day is not None for week in CalendarMonth(9999, 12).weeks for day in week))
        self.assertEqual(date(1, 1, 1), CalendarMonth(1, 1).weeks[0][0])
        for args in [(True, 1), (2026, 13), (2026, 10, 'UTC', [date(2026, 11, 1)]), (2026, 10, 'UTC', [datetime(2026, 10, 1)])]:
            with self.assertRaises(ValidationFailure): CalendarMonth(*args)


class SlotStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'booking.sqlite3'
        self.store = SQLiteSlotStore(self.database, authorize=allow)
        self.store.initialize()
        self.slot = TimeSlot('one', START, START + timedelta(hours=1))
        self.store.publish('room', [self.slot], expected_revision=0)

    def reserve(self, **kwargs):
        return self.store.reserve('room', kwargs.pop('slot_key', 'one'), actor_id=kwargs.pop('actor_id', 42), expected_revision=kwargs.pop('expected_revision', 1), operation_id=kwargs.pop('operation_id', 'op-1'), now=kwargs.pop('now', NOW), **kwargs)

    def test_receipt_survives_restart_and_cancel_keeps_original_receipt(self):
        first = self.reserve()
        self.store = SQLiteSlotStore(self.database, authorize=allow)
        replay = self.reserve(now=START + timedelta(days=2))
        self.assertTrue(replay.replayed); self.assertEqual(first.value, replay.value)
        booking_id = first.value['booking_id']
        self.store.cancel('room', booking_id, actor_id=42, operation_id='cancel')
        current = self.store.booking('room', booking_id, actor_id=42)
        self.assertIsInstance(current, SlotBooking); self.assertEqual('cancelled', current.status)
        self.assertEqual('active', self.reserve().value['status'])
        self.assertTrue(self.store.cancel('room', booking_id, actor_id=42, operation_id='cancel').replayed)
        replacement = self.reserve(actor_id=43, operation_id='new')
        self.assertNotEqual(booking_id, replacement.value['booking_id'])

    def test_unavailable_past_unknown_and_stale_schedule_do_not_persist_effect(self):
        self.store.publish('room', [TimeSlot('off', START, START + timedelta(hours=1), False)], expected_revision=1)
        for kwargs in [{'expected_revision':1}, {'slot_key':'off','expected_revision':2}, {'slot_key':'absent','expected_revision':2}]:
            with self.assertRaises(ConflictFailure): self.reserve(**kwargs)
        with self.assertRaises(ConflictFailure): self.store.publish('room', [self.slot], expected_revision=1)
        self.store.publish('room', [self.slot], expected_revision=2)
        with self.assertRaises(ConflictFailure): self.reserve(expected_revision=3, now=START)
        with closing(sqlite3.connect(self.database, isolation_level=None)) as c:
            self.assertEqual(0, c.execute('SELECT count(*) FROM telegram_slot_bookings').fetchone()[0])
            self.assertEqual(0, c.execute('SELECT count(*) FROM telegram_slot_operations').fetchone()[0])

    def test_forged_actor_foreign_booking_and_payload_reuse_are_rejected(self):
        with self.assertRaises(PermissionDenied): self.reserve(actor_id=99)
        first = self.reserve()
        with self.assertRaises(PermissionDenied): self.store.booking('room', first.value['booking_id'], actor_id=43)
        with self.assertRaises(PermissionDenied): self.store.cancel('room', first.value['booking_id'], actor_id=43, operation_id='cancel')
        with self.assertRaises(OperationConflict): self.reserve(expected_revision=2)
        self.assertEqual('active', self.store.booking('room', first.value['booking_id'], actor_id=42).status)

    def test_current_acl_is_checked_inside_same_transaction_before_replay(self):
        with closing(sqlite3.connect(self.database, isolation_level=None)) as c:
            c.execute('CREATE TABLE resource_acl(actor INTEGER PRIMARY KEY, allowed INTEGER)')
            c.execute('INSERT INTO resource_acl VALUES(42,1)')
        calls = []
        def acl(c, actor, resource):
            calls.append(c.in_transaction)
            return bool(c.execute('SELECT allowed FROM resource_acl WHERE actor=?', (actor,)).fetchone()[0])
        self.store = SQLiteSlotStore(self.database, authorize=acl)
        first = self.reserve()
        with closing(sqlite3.connect(self.database, isolation_level=None)) as c: c.execute('UPDATE resource_acl SET allowed=0')
        with self.assertRaises(PermissionDenied): self.reserve()
        with self.assertRaises(PermissionDenied): self.store.booking('room', first.value['booking_id'], actor_id=42)
        self.assertTrue(all(calls)); self.assertEqual(3, len(calls))

    def test_guard_cannot_commit_an_effect_outside_owned_transaction(self):
        def broken(c, actor, resource):
            c.execute('UPDATE telegram_slot_schedules SET revision=10')
            c.commit()
            return True
        self.store = SQLiteSlotStore(self.database, authorize=broken)
        with self.assertRaises(sqlite3.DatabaseError): self.reserve()
        with closing(sqlite3.connect(self.database, isolation_level=None)) as c: self.assertEqual(1, c.execute('SELECT revision FROM telegram_slot_schedules').fetchone()[0])

    def test_failure_between_booking_and_receipt_rolls_back_both(self):
        from telegram_patterns.slots import _json
        calls=[]
        def serialize(value):
            calls.append(value)
            # The payload digest uses sqlite_once; slots._json serializes only the receipt.
            if len(calls)==1: raise RuntimeError('fixture receipt serialization failure')
            return _json(value)
        with patch('telegram_patterns.slots._json',side_effect=serialize):
            with self.assertRaises(RuntimeError): self.reserve()
        with closing(sqlite3.connect(self.database)) as c:
            self.assertEqual(0,c.execute('SELECT count(*) FROM telegram_slot_bookings').fetchone()[0])
            self.assertEqual(0,c.execute('SELECT count(*) FROM telegram_slot_operations').fetchone()[0])
        self.assertFalse(self.reserve().replayed)

    def test_overlap_aliases_are_blocked_but_adjacent_and_other_resources_work(self):
        overlap = TimeSlot('alias', START + timedelta(minutes=15), START + timedelta(hours=2))
        adjacent = TimeSlot('next', self.slot.end, self.slot.end + timedelta(hours=1))
        self.store.publish('room', [self.slot, overlap, adjacent], expected_revision=1)
        self.reserve(expected_revision=2)
        snapshot = self.store.schedule('room', actor_id=42, now=NOW)
        self.assertEqual({'one':False,'alias':False,'next':True}, {s.key:s.enabled for s in snapshot.slots})
        with self.assertRaises(ConflictFailure): self.reserve(slot_key='alias', expected_revision=2, operation_id='alias')
        self.reserve(slot_key='next', expected_revision=2, operation_id='next')
        self.store.publish('other', [self.slot], expected_revision=0)
        self.store.reserve('other','one',actor_id=42,expected_revision=1,operation_id='op-1',now=NOW)

    def test_schedule_replacement_preserves_booking_and_blocks_same_key_move(self):
        receipt = self.reserve()
        moved = TimeSlot('one', START + timedelta(days=1), START + timedelta(days=1,hours=1))
        alias = TimeSlot('new', self.slot.start, self.slot.end)
        self.store.publish('room', [moved, alias], expected_revision=1)
        snapshot = self.store.schedule('room', actor_id=42, now=NOW)
        self.assertFalse(any(s.enabled for s in snapshot.slots))
        current = self.store.booking('room', receipt.value['booking_id'], actor_id=42)
        self.assertEqual(START, current.start)
        for key in ('one','new'):
            with self.assertRaises(ConflictFailure): self.reserve(slot_key=key,expected_revision=2,operation_id=key)

    def test_fractional_and_pre_epoch_timestamps_remain_exact(self):
        beginning = datetime(1969, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)
        self.store.publish('room', [TimeSlot('micro', beginning, beginning+timedelta(microseconds=2))], expected_revision=1)
        receipt = self.reserve(slot_key='micro',expected_revision=2,now=beginning-timedelta(seconds=1))
        current = self.store.booking('room',receipt.value['booking_id'],actor_id=42)
        self.assertEqual(beginning,current.start); self.assertEqual(timedelta(microseconds=2),current.end-current.start)

    def test_schedule_snapshots_and_invalid_configuration(self):
        source = [self.slot]
        snapshot = SlotSchedule('room',1,source); source.clear()
        self.assertEqual((self.slot,), snapshot.slots)
        for kwargs in [{'timeout':True},{'timeout':float('nan')},{'authorize':None}]:
            args={'authorize':allow}; args.update(kwargs)
            with self.assertRaises(ValidationFailure): SQLiteSlotStore(self.database,**args)
        for actor in (True,0,-1,2**63):
            with self.assertRaises(ValidationFailure): self.reserve(actor_id=actor)
        with self.assertRaises(ValidationFailure): SlotSchedule('room',1,[self.slot,self.slot])

    def race(self, *, same_operation=False, overlapping=False):
        if overlapping:
            self.store.publish('room',[self.slot,TimeSlot('alias',self.slot.start,self.slot.end)],expected_revision=1)
        ctx=multiprocessing.get_context('spawn'); barrier=ctx.Barrier(3); queue=ctx.Queue()
        processes=[ctx.Process(target=competing_worker,args=(str(self.database),barrier,queue,
                   42 if same_operation else 42+i,'same' if same_operation else f'op-{i}', 'alias' if overlapping and i else 'one', 2 if overlapping else 1)) for i in range(2)]
        try:
            for process in processes: process.start()
            barrier.wait(timeout=15)
            results=[queue.get(timeout=20) for _ in processes]
            for process in processes:
                process.join(timeout=20); self.assertEqual(0,process.exitcode)
            with closing(sqlite3.connect(self.database, isolation_level=None)) as c:
                self.assertEqual(1,c.execute('SELECT count(*) FROM telegram_slot_bookings').fetchone()[0])
                self.assertEqual(1,c.execute('SELECT count(*) FROM telegram_slot_operations').fetchone()[0])
            return results
        finally:
            for process in processes:
                if process.is_alive(): process.terminate(); process.join(timeout=5)
            queue.close(); queue.join_thread()

    def test_separate_processes_cannot_book_one_slot_twice(self):
        self.assertEqual(['conflict','ok'],sorted(row[0] for row in self.race()))

    def test_separate_processes_replay_identical_intent_once(self):
        results=self.race(same_operation=True)
        self.assertEqual(['ok','ok'],[row[0] for row in results])
        self.assertEqual([False,True],sorted(row[1] for row in results))
        self.assertEqual(results[0][2],results[1][2])

    def test_separate_processes_cannot_book_overlapping_aliases(self):
        self.assertEqual(['conflict','ok'],sorted(row[0] for row in self.race(overlapping=True)))


if __name__ == '__main__': unittest.main()
