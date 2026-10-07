"""Every guard of initdata, sqlite_once, slots, message_text and the aiogram media adapter rejects its input.

These modules carry a 100% branch coverage gate (scripts/check_coverage.py); each case below names the
rule it protects rather than a line number.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from aiogram.methods import EditMessageMedia

from telegram_patterns import (
    ConflictFailure,
    InvalidType,
    SlotBooking,
    SlotSchedule,
    SQLiteOnce,
    SQLiteSlotStore,
    TimeSlot,
    UnsupportedCapability,
    ValidationFailure,
    validate_init_data,
)
from telegram_patterns.aiogram import MediaFile, MediaItem, download_media, media_album, media_edit, media_request
from telegram_patterns.message_text import FormattedText, MessageBuilder, split_formatted

NOW = datetime(2026, 10, 5, 8, tzinfo=timezone.utc)
START = NOW + timedelta(days=1)


def allow(_connection, actor, resource):
    return True


def linked(text, start, end):
    """Plain text with one atomic text_link over text[start:end]."""
    builder = MessageBuilder().text(text[:start]).style(text[start:end], 'text_link', url='https://example.com')
    return builder.text(text[end:]).build()


class InitDataGuardTests(unittest.TestCase):
    def test_clock_must_be_a_nonnegative_integer(self):
        for now in (-1, True, 1.5):
            with self.subTest(now=now), self.assertRaisesRegex(ValidationFailure, 'nonnegative Unix timestamp'):
                validate_init_data('auth_date=1&hash=0', '1:TOKEN', now=now)


class SQLiteOnceGuardTests(unittest.TestCase):
    def test_transaction_ended_inside_apply_is_refused_even_if_the_authorizer_is_bypassed(self):
        with tempfile.TemporaryDirectory() as folder:
            once = SQLiteOnce(Path(folder) / 'once.sqlite3')
            once.initialize()
            with self.assertRaisesRegex(sqlite3.DatabaseError, 'not authorized'):
                once.run('scope', 'commit', {'n': 1}, lambda connection: connection.commit())
            with patch('telegram_patterns.sqlite_once.owned_transaction', lambda *arguments: sqlite3.SQLITE_OK):
                with self.assertRaisesRegex(RuntimeError, 'must not commit or roll back'):
                    once.run('scope', 'bypass', {'n': 2}, lambda connection: connection.commit())
            self.assertEqual(once.run('scope', 'bypass', {'n': 2}, lambda connection: 'ok').value, 'ok')


class SlotGuardTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = SQLiteSlotStore(Path(folder.name) / 'slots.sqlite3', authorize=allow)
        self.store.initialize()
        self.slot = TimeSlot('one', START, START + timedelta(hours=1))

    def test_schedule_and_booking_records_reject_malformed_values(self):
        for resource in ('', 'x' * 129, 'a\nb', '\ud800', 7):
            with self.subTest(resource=resource), self.assertRaisesRegex(ValidationFailure, 'bounded identifier'):
                SlotSchedule(resource, 1, [self.slot])
        for revision in (0, True, 2**63):
            with self.subTest(revision=revision), self.assertRaisesRegex(ValidationFailure, 'positive schedule'):
                SlotSchedule('room', revision, [self.slot])
        for slots in ('one', b'one', 7):
            with self.subTest(slots=slots), self.assertRaisesRegex(InvalidType, 'TimeSlot objects'):
                SlotSchedule('room', 1, slots)
        with self.assertRaisesRegex(ValidationFailure, 'at most 1000'):
            SlotSchedule('room', 1, [self.slot, 'not a slot'])
        with self.assertRaisesRegex(ValidationFailure, 'active or cancelled'):
            SlotBooking('b1', 'room', 'one', 42, START, START + timedelta(hours=1), 'pending')

    def test_store_arguments_and_unknown_state_are_controlled(self):
        for database in ('', ':memory:', 7):
            with self.subTest(database=database), self.assertRaisesRegex(ValidationFailure, 'file database'):
                SQLiteSlotStore(database, authorize=allow)
        for revision in (-1, True, 2**63 - 1):
            with self.subTest(revision=revision), self.assertRaisesRegex(ValidationFailure, '0 to create'):
                self.store.publish('room', [self.slot], expected_revision=revision)
        with self.assertRaisesRegex(ConflictFailure, 'not published'):
            self.store.schedule('room', actor_id=42, now=NOW)
        self.store.publish('room', [self.slot], expected_revision=0)
        for revision in (0, True, 2**63):
            with self.subTest(revision=revision), self.assertRaisesRegex(ValidationFailure, 'positive expected'):
                self.store.reserve('room', 'one', actor_id=42, expected_revision=revision, operation_id='op', now=NOW)
        self.assertIsNone(self.store.booking('room', 'missing-booking', actor_id=42))


class SplitPathTests(unittest.TestCase):
    """Whitespace-only windows join or borrow from a neighbour; otherwise ValueError, never lost text."""

    def assert_lossless(self, value, limit):
        parts = split_formatted(value, limit=limit)
        self.assertEqual(''.join(part.text for part in parts), value.text)
        self.assertTrue(all(part.text.strip() for part in parts), parts)
        return parts

    def test_whitespace_parts_join_or_borrow_from_neighbours(self):
        cases = [
            (linked('a\n bab', 3, 6), 3),  # joins the previous part
            (linked('\na\nbb b\n\n\n ', 1, 4), 6),  # joins the next part
            (linked(' baaa\n', 4, 5), 5),  # takes the tail of the previous part
            (linked('\n\nb ab', 2, 5), 5),  # takes the head of the next part
        ]
        for value, limit in cases:
            with self.subTest(text=value.text, limit=limit):
                self.assert_lossless(value, limit)

    def test_unsendable_whitespace_is_an_error(self):
        for value, limit in (
            (FormattedText('  b \n'), 3),
            (linked('\n   a\n', 2, 6), 5),
            (FormattedText('\n  aaa b  a'), 3),
        ):
            with self.subTest(text=value.text, limit=limit), self.assertRaisesRegex(ValueError, 'whitespace-only part'):
                split_formatted(value, limit=limit)
        with self.assertRaises(TypeError):
            split_formatted('plain text')
        with self.assertRaises(TypeError):
            MessageBuilder('plain text')


class MediaGuardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.document = MediaItem(MediaFile('document', 'BQACAgIAAx0', bot_id=100))

    def test_chat_ids_usernames_and_items_are_checked_before_a_request(self):
        self.assertEqual(
            media_request(self.document, bot_id=100, chat_id='@fixture_channel').chat_id, '@fixture_channel'
        )
        for chat in ('@abc', 'fixture_channel', 0, 2**52, True):
            with self.subTest(chat=chat), self.assertRaisesRegex(ValidationFailure, 'chat ID or explicit @username'):
                media_request(self.document, bot_id=100, chat_id=chat)
        with self.assertRaisesRegex(InvalidType, 'MediaItem'):
            media_request('BQACAgIAAx0', bot_id=100, chat_id=42)
        with self.assertRaisesRegex(InvalidType, 'list or tuple'):
            media_album(iter([self.document, self.document]), bot_id=100, chat_id=42)
        with self.assertRaisesRegex(InvalidType, 'MediaItem'):
            media_edit('BQACAgIAAx0', bot_id=100, chat_id=42, message_id=7)

    def test_item_files_flags_and_inline_addresses(self):
        with self.assertRaisesRegex(ValidationFailure, 'Bot scope belongs to reused file_id'):
            MediaFile('photo', b'\x89PNG', filename='a.png', bot_id=100)
        with self.assertRaisesRegex(InvalidType, 'MediaFile and an optional'):
            MediaItem('BQACAgIAAx0')
        with self.assertRaisesRegex(InvalidType, 'flags must be bool'):
            MediaItem(self.document.file, spoiler=1)
        with self.assertRaisesRegex(UnsupportedCapability, 'photo/video'):
            MediaItem(self.document.file, spoiler=True)
        self.assertIsInstance(media_edit(self.document, bot_id=100, inline_message_id='inline-1'), EditMessageMedia)
        for inline in ('', 'has space', 7):
            with self.subTest(inline=inline), self.assertRaisesRegex(ValidationFailure, 'opaque inline message ID'):
                media_edit(self.document, bot_id=100, inline_message_id=inline)

    async def test_download_requires_the_host_bot(self):
        with self.assertRaisesRegex(InvalidType, 'existing host Bot'):
            await download_media('not a bot', 'BQACAgIAAx0')


if __name__ == '__main__':
    unittest.main()
