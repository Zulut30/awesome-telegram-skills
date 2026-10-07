import hmac
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from aiogram.utils.web_app import check_webapp_signature

from telegram_patterns import InvalidInitData, OperationConflict, SQLiteOnce, validate_init_data
from telegram_patterns.aiogram import ActionResult, action_keyboard, callback_router, stars_invoice, start_router

# Fixed synthetic compatibility vector, also verified by an independent SDK.
TOKEN = '42:TEST'
DATE = 1650385342
VECTOR = (
    'auth_date=1650385342&user=%7B%22id%22%3A42%2C%22first_name%22%3A%22Test%22%7D&query_id=test'
    '&hash=46d2ea5e32911ec8d30999b56247654460c0d20949b6277af519e76271182803'
)


def signed(**changes):
    fields = dict(parse_qsl(VECTOR))
    fields.pop('hash')
    fields.update(changes)
    secret = hmac.digest(b'WebAppData', TOKEN.encode(), 'sha256')
    check = '\n'.join(f'{k}={v}' for k, v in sorted(fields.items()))
    return urlencode({**fields, 'hash': hmac.digest(secret, check.encode(), 'sha256').hex()})


class AuthTests(unittest.TestCase):
    def test_fixed_vector_and_sdk_agree(self):
        self.assertTrue(check_webapp_signature(TOKEN, VECTOR))
        identity = validate_init_data(VECTOR, TOKEN, now=DATE)
        self.assertEqual(identity.user_id, 42)
        with self.assertRaises(TypeError):
            identity.user['id'] = 99

    def test_tampering_and_wrong_token(self):
        for raw, token in [(VECTOR.replace('query_id=test', 'query_id=other'), TOKEN), (VECTOR, '43:TEST')]:
            with self.subTest(raw=raw), self.assertRaises(InvalidInitData):
                validate_init_data(raw, token, now=DATE)

    def test_duplicate_fields_rejected_even_when_sdk_accepts(self):
        raw = VECTOR + '&query_id=test'
        self.assertTrue(check_webapp_signature(TOKEN, raw))
        with self.assertRaises(InvalidInitData):
            validate_init_data(raw, TOKEN, now=DATE)

    def test_signature_field_remains_in_hmac(self):
        raw = signed(signature='synthetic-signature')
        self.assertTrue(check_webapp_signature(TOKEN, raw))
        self.assertEqual(validate_init_data(raw, TOKEN, now=DATE).user_id, 42)
        with self.assertRaises(InvalidInitData):
            validate_init_data(raw.replace('synthetic-signature', 'modified'), TOKEN, now=DATE)

    def test_freshness_boundaries(self):
        validate_init_data(VECTOR, TOKEN, now=DATE + 299, max_age_seconds=300)
        for now in [DATE + 300, DATE - 31]:
            with self.subTest(now=now), self.assertRaises(InvalidInitData):
                validate_init_data(VECTOR, TOKEN, now=now, max_age_seconds=300)

    def test_signed_user_and_timestamp_validation(self):
        for changes in [
            {'user': '{}'},
            {'user': '{"id":true}'},
            {'user': '{"id":-1}'},
            {'user': 'not-json'},
            {'auth_date': 'nan'},
        ]:
            with self.subTest(changes=changes), self.assertRaises(InvalidInitData):
                validate_init_data(signed(**changes), TOKEN, now=DATE)

    def test_launch_fields_are_returned_and_deeply_read_only(self):
        user = '{"id":42,"first_name":"Test","photo":{"a":1},"tags":[{"x":1}]}'
        raw = signed(
            user=user,
            chat='{"id":-100,"type":"group"}',
            receiver='{"id":7,"first_name":"R"}',
            chat_type='group',
            chat_instance='-55',
            start_param='ref_1',
            can_send_after='15',
        )
        launch = validate_init_data(raw, TOKEN, now=DATE)
        self.assertEqual(
            (launch.query_id, launch.chat_type, launch.chat_instance, launch.start_param, launch.can_send_after),
            ('test', 'group', '-55', 'ref_1', 15),
        )
        self.assertEqual((launch.chat['id'], launch.receiver['id']), (-100, 7))
        for mutate in (
            lambda: launch.user.__setitem__('id', 1),
            lambda: launch.user['photo'].__setitem__('a', 2),
            lambda: launch.user['tags'][0].__setitem__('x', 2),
            lambda: launch.chat.__setitem__('id', 1),
            lambda: launch.user['tags'].append({}),
        ):
            with self.assertRaises((TypeError, AttributeError)):
                mutate()
        copy = launch.as_dict()
        self.assertEqual(json.loads(json.dumps(copy))['user'], json.loads(user))
        copy['user']['photo']['a'] = 99
        self.assertEqual(launch.user['photo']['a'], 1)
        minimal = validate_init_data(VECTOR, TOKEN, now=DATE)
        self.assertEqual(
            (minimal.chat, minimal.receiver, minimal.start_param, minimal.can_send_after), (None, None, None, None)
        )
        self.assertEqual(set(minimal.as_dict()), {'user_id', 'auth_date', 'user', 'query_id'})

    def test_non_standard_json_and_invalid_optional_objects_are_rejected(self):
        for changes in [
            {'user': '{"id":42,"score":NaN}'},
            {'user': '{"id":42,"score":Infinity}'},
            {'user': '{"id":42,"score":-Infinity}'},
            {'chat': '[1]'},
            {'chat': 'null'},
            {'receiver': 'oops'},
            {'can_send_after': '-1'},
            {'can_send_after': '1.5'},
            {'can_send_after': ''},
        ]:
            with self.subTest(changes=changes), self.assertRaises(InvalidInitData):
                validate_init_data(signed(**changes), TOKEN, now=DATE)

    def test_bad_encoding_size_hash_and_configuration(self):
        for raw in [VECTOR + '%ZZ', 'query_id=x&hash=abcd', VECTOR.replace('%7B', '%FF'), VECTOR + '&=x']:
            with self.subTest(raw=raw), self.assertRaises(InvalidInitData):
                validate_init_data(raw, TOKEN, now=DATE)
        with self.assertRaises(InvalidInitData):
            validate_init_data(VECTOR, TOKEN, now=DATE, max_length=10)
        with self.assertRaises(ValueError):
            validate_init_data(VECTOR, '', now=DATE)

    def test_literal_invalid_unicode_is_controlled_auth_failure(self):
        with self.assertRaises(InvalidInitData):
            validate_init_data(VECTOR + '&extra=\ud800', TOKEN, now=DATE)


class OnceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'orders.sqlite'
        self.store = SQLiteOnce(self.path)
        self.store.initialize()
        connection = sqlite3.connect(self.path)
        try:
            connection.execute('CREATE TABLE orders (id INTEGER PRIMARY KEY, owner TEXT, note TEXT)')
            connection.commit()
        finally:
            connection.close()

    def tearDown(self):
        self.temp.cleanup()

    def effect(self, connection):
        cursor = connection.execute('INSERT INTO orders(owner,note) VALUES (?,?)', ('a', 'test'))
        return {'order_id': cursor.lastrowid}

    def count(self):
        connection = sqlite3.connect(self.path)
        try:
            return connection.execute('SELECT count(*) FROM orders').fetchone()[0]
        finally:
            connection.close()

    def test_parallel_requests_one_effect(self):
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(
                executor.map(lambda _: self.store.run('owner:a:book', 'same', {'slot': 1}, self.effect), range(12))
            )
        self.assertEqual(self.count(), 1)
        self.assertEqual(sum(not r.replayed for r in results), 1)
        self.assertEqual({r.value['order_id'] for r in results}, {1})

    def test_payload_conflict_and_scope_isolation(self):
        self.store.run('a', 'key', {'slot': 1}, self.effect)
        with self.assertRaises(OperationConflict):
            self.store.run('a', 'key', {'slot': 2}, self.effect)
        self.store.run('b', 'key', {'slot': 1}, self.effect)
        self.assertEqual(self.count(), 2)

    def test_effect_and_ledger_rollback_together(self):
        def failing(connection):
            self.effect(connection)
            raise ValueError('temporary failure')

        with self.assertRaises(ValueError):
            self.store.run('a', 'key', {}, failing)
        self.assertEqual(self.count(), 0)
        self.assertFalse(self.store.run('a', 'key', {}, self.effect).replayed)

    def test_invalid_json_result_rolls_back(self):
        def invalid(connection):
            self.effect(connection)
            return float('nan')

        with self.assertRaises(ValueError):
            self.store.run('a', 'key', {}, invalid)
        self.assertEqual(self.count(), 0)

    def test_callback_commit_cannot_persist_effect_without_ledger(self):
        def premature(connection):
            result = self.effect(connection)
            connection.commit()
            return result

        with self.assertRaises((sqlite3.DatabaseError, RuntimeError)):
            self.store.run('a', 'key', {}, premature)
        self.assertEqual(self.count(), 0)
        self.assertFalse(self.store.run('a', 'key', {}, self.effect).replayed)
        self.assertEqual(self.count(), 1)

    def test_executescript_cannot_implicitly_commit_effect(self):
        def premature(connection):
            self.effect(connection)
            connection.executescript("INSERT INTO orders(owner,note) VALUES ('a','second')")
            return {'ok': True}

        with self.assertRaises((sqlite3.DatabaseError, RuntimeError)):
            self.store.run('a', 'key', {}, premature)
        self.assertEqual(self.count(), 0)
        self.assertFalse(self.store.run('a', 'key', {}, self.effect).replayed)

    def test_nested_savepoint_preserves_outer_atomic_operation(self):
        def nested(connection):
            connection.execute('SAVEPOINT business')
            result = self.effect(connection)
            connection.execute('RELEASE business')
            return result

        result = self.store.run('a', 'key', {}, nested)
        self.assertEqual(self.count(), 1)
        self.assertEqual(self.store.run('a', 'key', {}, self.effect).value, result.value)

    def test_process_restart_returns_persisted_result(self):
        self.store.run('a', 'key', {}, self.effect)
        code = (
            "from telegram_patterns import SQLiteOnce;import sys,json;s=SQLiteOnce(sys.argv[1]);"
            "r=s.run('a','key',{},lambda db: (_ for _ in ()).throw(AssertionError('must not run')));"
            "print(json.dumps({'value':r.value,'replayed':r.replayed}))"
        )
        result = subprocess.run(
            [sys.executable, '-c', code, str(self.path)], capture_output=True, text=True, check=True
        )
        self.assertEqual(json.loads(result.stdout), {'value': {'order_id': 1}, 'replayed': True})
        self.assertEqual(self.count(), 1)

    def test_configuration_and_payload_preflight(self):
        for path in ['', ':memory:']:
            with self.assertRaises(ValueError):
                SQLiteOnce(path)
        with self.assertRaises(ValueError):
            self.store.run('', 'key', {}, self.effect)
        with self.assertRaises(ValueError):
            self.store.run('a', 'key', {'bad': float('nan')}, self.effect)
        self.assertEqual(self.count(), 0)

    def test_payloads_that_would_collide_or_fail_late_are_rejected_before_database(self):
        from telegram_patterns.errors import ValidationFailure

        self.store.run('a', 'one', {'1': 'a', 'items': [1, 2]}, self.effect)
        for payload in (
            {1: 'a'},
            {'items': (1, 2)},
            {1: 'a', 'b': 2},
            {'x': {2: 'nested'}},
            {'x': float('inf')},
            {'x': {1, 2}},
            {'x': b'bytes'},
            {'x': object()},
            ('a',),
        ):
            with self.subTest(payload=repr(payload)), self.assertRaises(ValidationFailure):
                self.store.run('a', 'two', payload, self.effect)
        deep = current = {}
        for _ in range(70):
            current['x'] = {}
            current = current['x']
        with self.assertRaises(ValidationFailure):
            self.store.run('a', 'two', deep, self.effect)
        self.assertEqual(self.count(), 1)
        from collections import OrderedDict

        self.assertTrue(self.store.run('a', 'one', OrderedDict([('items', [1, 2]), ('1', 'a')]), self.effect).replayed)
        with self.assertRaises(OperationConflict):
            self.store.run('a', 'one', {'1': 'b', 'items': [1, 2]}, self.effect)
        fresh = Path(self.temp.name) / 'never-created.sqlite'
        with self.assertRaises(ValidationFailure):
            SQLiteOnce(fresh).run('a', 'k', {1: 'a'}, self.effect)
        self.assertFalse(fresh.exists())
        for timeout in (float('nan'), float('inf'), True, 0, -1, '5'):
            with self.subTest(timeout=timeout), self.assertRaises(ValidationFailure):
                SQLiteOnce(self.path, timeout=timeout)


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self):
        pass

    async def stream_content(self, url, **kwargs):
        yield b''

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, AnswerCallbackQuery):
            return True
        if isinstance(method, SendMessage):
            return Message(
                message_id=10, date=datetime.now(timezone.utc), chat=Chat(id=42, type='private'), text=method.text
            )
        raise AssertionError(type(method))


class SDKTests(unittest.IsolatedAsyncioTestCase):
    def test_colored_keyboard_and_emoji_fallback(self):
        safe = action_keyboard('Подтвердить', 'opaque-key', style='success', custom_emoji_id='123')
        button = safe.inline_keyboard[0][0]
        self.assertEqual(button.style, 'success')
        self.assertIsNone(button.icon_custom_emoji_id)
        enabled = action_keyboard(
            'Подтвердить', 'opaque-key', style='success', custom_emoji_id='123', emoji_entitlement_verified=True
        )
        self.assertEqual(enabled.model_dump(exclude_none=True)['inline_keyboard'][0][0]['icon_custom_emoji_id'], '123')
        boundary = action_keyboard('Ok', 'key', prefix='x' * 60 + ':')
        self.assertEqual(len(boundary.inline_keyboard[0][0].callback_data.encode()), 64)
        self.assertIsInstance(
            callback_router(lambda action: None, lambda query, result: None, prefix='x' * 60 + ':'), Router
        )
        for kwargs in [{'style': 'blue'}, {'key': 'bad!'}, {'prefix': 'x' * 61 + ':'}, {'custom_emoji_id': 'not-id'}]:
            values = {'text': 'Ok', 'key': 'key'}
            values.update(kwargs)
            with self.assertRaises(ValueError):
                action_keyboard(**values)

    async def test_callbacks_ack_before_service_and_notify_for_denial_and_invalid(self):
        session = FakeSession()
        bot = Bot(TOKEN, session=session)
        dp = Dispatcher()
        observations = []

        async def execute(action):
            self.assertIsInstance(session.calls[-1], AnswerCallbackQuery)
            observations.append(('execute', action.actor_id, action.key))
            return ActionResult('denied', 'Нет доступа')

        texts = []

        async def notify(query, result):
            observations.append(('notify', result.status))
            texts.append(result.text)

        dp.include_router(callback_router(execute, notify))
        for uid, data in [(99, 'act:key'), (99, 'act:bad!')]:
            update = Update(
                update_id=len(session.calls) + 1,
                callback_query=CallbackQuery(
                    id=str(len(session.calls) + 1),
                    from_user=User(id=uid, is_bot=False, first_name='Test'),
                    chat_instance='test',
                    data=data,
                ),
            )
            await dp.feed_update(bot, update)
        self.assertEqual(observations, [('execute', 99, 'key'), ('notify', 'denied'), ('notify', 'stale')])
        self.assertEqual(texts, ['Нет доступа', 'Кнопка недействительна. Откройте актуальное меню.'])
        self.assertEqual(len(session.calls), 2)
        await bot.session.close()

    async def test_start_plain_text_preserves_existing_router_stack(self):
        session = FakeSession()
        bot = Bot(TOKEN, session=session)
        dp = Dispatcher()
        dp.include_router(start_router('Привет <test>'))
        message = Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=42, type='private'),
            from_user=User(id=42, is_bot=False, first_name='Test'),
            text='/start',
        )
        await dp.feed_update(bot, Update(update_id=1, message=message))
        self.assertEqual(len(session.calls), 1)
        self.assertIsNone(session.calls[0].parse_mode)
        self.assertEqual(session.calls[0].text, 'Привет <test>')
        await bot.session.close()

    def test_stars_request_and_subscription_boundaries(self):
        request = stars_invoice('Доступ', 'Описание', 'order:1', 10, monthly_subscription=True)
        self.assertEqual(request.currency, 'XTR')
        self.assertEqual(request.subscription_period, 2592000)
        self.assertEqual([p.amount for p in request.prices], [10])
        self.assertEqual(request.provider_token, '')
        for value in [0, -1, True, 10001]:
            with self.assertRaises(ValueError):
                stars_invoice('Доступ', 'Описание', 'order:1', value, monthly_subscription=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
