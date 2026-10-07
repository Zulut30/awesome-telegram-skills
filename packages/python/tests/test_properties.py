"""Property-based tests of the parsers: initData, formatted text, callback/page data and order payloads.

Hypothesis is optional for a local run: without it the class below is skipped with a reason; CI installs it.
The default profile is deterministic (derandomize, no example database) so CI never flakes;
HYPOTHESIS_PROFILE=explore searches longer with a local database. Every counterexample found so far is kept
as an @example next to its property: a regression case that runs in every profile.
"""

import hmac
import html
import json
import math
import os
import re
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from telegram_patterns import (
    OperationConflict,
    SelectionContext,
    SelectionMenu,
    SelectionOption,
    SelectionSpec,
    SQLiteOnce,
    ValidationFailure,
    markup_page_number,
    validate_init_data,
)
from telegram_patterns.aiogram import page_number, stars_invoice
from telegram_patterns.message_text import (
    FormattedText,
    TextEntity,
    escape_html,
    escape_markdown_v2,
    split_formatted,
    utf16_length,
)

try:
    from hypothesis import HealthCheck, example, given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover - CI installs hypothesis
    st = None

TOKEN = '42:PROPERTY_FIXTURE'
NOW = 1_800_000_000
MARKDOWN_SPECIAL = set('_*[]()~`>#+-=|{}.!\\')


def signed(fields):
    secret = hmac.digest(b'WebAppData', TOKEN.encode(), 'sha256')
    check = '\n'.join(f'{key}={value}' for key, value in sorted(fields.items()))
    return urlencode({**fields, 'hash': hmac.digest(secret, check.encode(), 'sha256').hex()})


def reordered(value):
    """The same JSON value with every object's keys in reverse insertion order."""
    if isinstance(value, dict):
        return {key: reordered(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [reordered(item) for item in value]
    return value


def covered(value):
    result = {}
    for entity in value.entities:
        for unit in range(entity.offset, entity.offset + entity.length):
            result.setdefault(unit, set()).add(entity.kind)
    return result


if st is None:

    class PropertyTests(unittest.TestCase):
        @unittest.skip('install hypothesis to run the property-based tests')
        def test_properties(self):
            pass

else:
    settings.register_profile(
        'ci',
        max_examples=150,
        deadline=None,
        derandomize=True,
        database=None,
        print_blob=True,
        suppress_health_check=[HealthCheck.too_slow],
    )
    settings.register_profile('explore', max_examples=5000, deadline=None, print_blob=True)
    settings.load_profile(os.environ.get('HYPOTHESIS_PROFILE', 'ci'))

    names = st.text(st.characters(codec='utf-8', exclude_categories=('Cc', 'Cs')), min_size=1, max_size=40)
    json_values = st.recursive(
        st.none()
        | st.booleans()
        | st.integers(-(2**53), 2**53)
        | st.floats(allow_nan=False, allow_infinity=False)
        | st.text(max_size=20),
        lambda children: st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=8), children, max_size=4),
        max_leaves=20,
    )

    @st.composite
    def compositions(draw):
        alphabet = ('a', 'Я', '😀', 'é', '👍🏽', ' ', '\n', '\t')
        text = draw(st.lists(st.sampled_from(alphabet), min_size=1, max_size=60).map(''.join))
        size = utf16_length(text)
        entities = []
        for _ in range(draw(st.integers(0, 5))):
            offset = draw(st.integers(0, max(0, size - 1)))
            length = draw(st.integers(1, max(1, size - offset)))
            candidate = TextEntity(draw(st.sampled_from(('bold', 'italic', 'spoiler'))), offset, length)
            try:
                FormattedText(text, tuple(entities + [candidate]))
            except ValueError:
                continue
            entities.append(candidate)
        return FormattedText(text, tuple(entities)), draw(st.integers(4, 48))

    class PropertyTests(unittest.TestCase):
        # initData: a signed launch round-trips; any change to a signed field or the hash is refused.

        @given(
            user_id=st.integers(1, 2**52),
            first_name=names,
            age=st.integers(0, 3599),  # max_age_seconds=3600 is exclusive
            query=st.text(st.sampled_from('abcXYZ019_-'), min_size=1, max_size=32),
        )
        def test_signed_launch_round_trips(self, user_id, first_name, age, query):
            user = json.dumps({'id': user_id, 'first_name': first_name}, ensure_ascii=False)
            launch = validate_init_data(
                signed({'auth_date': str(NOW - age), 'user': user, 'query_id': query}), TOKEN, now=NOW
            )
            self.assertEqual((launch.user_id, launch.auth_date), (user_id, NOW - age))
            self.assertEqual(launch.user['first_name'], first_name)
            with self.assertRaises(ValidationFailure):  # exactly max_age old is already stale
                validate_init_data(signed({'auth_date': str(NOW - 3600), 'user': user}), TOKEN, now=NOW)

        @given(first_name=names, position=st.integers(0, 10_000), replacement=st.characters(codec='utf-8'))
        def test_any_tampering_is_refused(self, first_name, position, replacement):
            raw = signed({'auth_date': str(NOW), 'user': json.dumps({'id': 7, 'first_name': first_name})})
            index = position % len(raw)
            tampered = raw[:index] + replacement + raw[index + 1 :]
            try:
                launch = validate_init_data(tampered, TOKEN, now=NOW)
            except ValidationFailure:
                return
            # Only another encoding of the same signed fields may pass (for example %41 for A).
            self.assertEqual((launch.user_id, launch.user['first_name'], launch.auth_date), (7, first_name, NOW))

        @given(st.text(max_size=300))
        @example('auth_date=1&hash=' + '0' * 64)
        @example('user=%FF&hash=00')
        def test_arbitrary_text_is_only_ever_refused(self, raw):
            with self.assertRaises(ValidationFailure):
                validate_init_data(raw, TOKEN, now=NOW)

        # Formatted text: escaping is reversible; splitting loses nothing and every part is sendable.

        @given(st.text())
        @example('\x08')  # control characters are refused, not escaped
        def test_html_escape_is_reversible_and_inert(self, text):
            if any(ord(c) < 32 and c not in '\t\r\n' for c in text):
                with self.assertRaisesRegex(ValueError, 'control character'):
                    escape_html(text)
                return
            escaped = escape_html(text)
            self.assertEqual(html.unescape(escaped), text)
            self.assertFalse(set('<>"\'') & set(escaped))

        @given(st.text(), st.sampled_from(['text', 'code', 'link']))
        @example('\x08', 'text')
        def test_markdown_v2_escape_marks_every_special_character(self, text, context):
            if any(ord(c) < 32 and c not in '\t\r\n' for c in text):
                with self.assertRaisesRegex(ValueError, 'control character'):
                    escape_markdown_v2(text, context=context)
                return
            escaped = escape_markdown_v2(text, context=context)
            special = {'text': MARKDOWN_SPECIAL, 'code': set('`\\'), 'link': set(')\\')}[context]
            self.assertEqual(re.sub(r'\\(.)', r'\1', escaped, flags=re.S), text)
            unescaped = re.sub(r'\\.', '', escaped, flags=re.S)
            self.assertFalse(special & set(unescaped))

        @given(compositions())
        @example((FormattedText('a\n bab'), 3))
        def test_split_is_lossless_or_explicitly_refused(self, case):
            value, limit = case
            try:
                parts = split_formatted(value, limit=limit)
            except ValueError as error:
                self.assertRegex(str(error), 'whitespace-only part|exceeds the chunk limit')
                return
            self.assertEqual(''.join(part.text for part in parts), value.text)
            after, shift = {}, 0
            for part in parts:
                self.assertLessEqual(utf16_length(part.text), limit)
                self.assertTrue(part.text.strip())
                after.update({unit + shift: kinds for unit, kinds in covered(part).items()})
                shift += utf16_length(part.text)
            self.assertEqual(after, covered(value))

        # Callback data: both page parsers agree on any input and read back what a keyboard writes.

        @given(
            data=st.one_of(st.none(), st.text(max_size=80), st.integers(0, 10**60).map(lambda n: f'page:{n}')),
            prefix=st.sampled_from(['page:', 'p:', 'p' * 20 + ':']),
        )
        @example(data='p' * 20 + ':' + '1' * 44, prefix='p' * 20 + ':')  # 65 bytes: over the callback limit
        def test_page_parsers_agree_on_untrusted_data(self, data, prefix):
            expected = page_number(data, prefix=prefix)
            self.assertEqual(markup_page_number(data, prefix=prefix), expected)
            if expected is not None:
                self.assertEqual(f'{prefix}{expected}', data)
                self.assertLessEqual(len(data.encode('utf-8')), 64)

        @given(st.text(max_size=80))
        @example('sel:0000000000000000:0:s:tea')  # well-formed, but not this menu's session
        def test_selection_never_trusts_foreign_callback_data(self, data):
            context = SelectionContext(100, 42, 42, 1)
            menu = SelectionMenu(SelectionSpec([SelectionOption('tea', 'Tea')]), context)
            before = menu.state
            result = menu.apply(data, context)
            self.assertEqual((result.status, menu.state), ('stale', before))
            self.assertEqual(menu.apply(before.callback('s:tea'), context).status, 'accepted')

        # Order payloads: an invoice payload is accepted exactly within Telegram's 1..128 bytes; an operation
        # payload replays under any key order and conflicts when its content changes.

        @given(st.text(max_size=140))
        def test_invoice_payload_bounds(self, payload):
            size = len(payload.encode('utf-8'))
            if 1 <= size <= 128:
                self.assertEqual(stars_invoice('Order', 'One item', payload, 5).payload, payload)
            else:
                with self.assertRaises(ValidationFailure):
                    stars_invoice('Order', 'One item', payload, 5)

        @settings(max_examples=60)
        @given(payload=json_values, changed=json_values)
        def test_operation_payload_replays_and_conflicts(self, payload, changed):
            with tempfile.TemporaryDirectory() as folder:
                once = SQLiteOnce(Path(folder) / 'once.sqlite3')
                once.initialize()
                first = once.run('orders', 'op', payload, lambda connection: 'created')
                again = once.run('orders', 'op', reordered(payload), lambda connection: 'created twice')
                self.assertEqual((first.replayed, again.replayed, again.value), (False, True, 'created'))
                if json.dumps(changed, sort_keys=True) != json.dumps(payload, sort_keys=True):
                    with self.assertRaises(OperationConflict):
                        once.run('orders', 'op', changed, lambda connection: 'other')

        @given(st.sampled_from([{1: 'a'}, ('a',), {'a': math.nan}, {'a': {1, 2}}, b'bytes', {'a': object()}]))
        def test_non_json_payloads_are_refused_before_any_effect(self, payload):
            with tempfile.TemporaryDirectory() as folder:
                once = SQLiteOnce(Path(folder) / 'once.sqlite3')
                once.initialize()
                effects = []
                with self.assertRaises(ValidationFailure):
                    once.run('orders', 'op', payload, lambda connection: effects.append(1))
                self.assertEqual(effects, [])


if __name__ == '__main__':
    unittest.main()
