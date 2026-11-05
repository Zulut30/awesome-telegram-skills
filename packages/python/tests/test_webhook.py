"""Webhook admission proves durable receipt, not SDK processing or Telegram delivery."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _support import integration

from telegram_patterns.errors import ValidationFailure
from telegram_patterns.inbox import SQLiteInbox
from telegram_patterns.webhook import WebhookReceiver, create_aiohttp_webhook_app

SECRET = 'owned_WEBHOOK-secret'


def body(update_id=1, **events):
    return json.dumps(
        {'update_id': update_id, **(events or {'message': {}})}, ensure_ascii=False, separators=(',', ':')
    ).encode('utf-8')


class WebhookAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.database = Path(self.folder.name) / 'inbox.sqlite'
        self.inbox = SQLiteInbox(self.database)
        self.inbox.initialize()
        self.receiver = WebhookReceiver(self.inbox, bot_id=100, secret_token=SECRET)

    def test_secret_checked_before_parse_or_storage_and_never_reflected(self):
        for secret in (None, '', 'wrong', SECRET + 'x', '\ud800', 'я' * 257):
            with self.subTest(secret_length=len(secret or '')):
                with patch.object(self.inbox, 'receive', side_effect=AssertionError('must not store')):
                    result = self.receiver.receive(b'not JSON', secret)
                self.assertEqual((result.status, result.code, result.accepted), (403, 'forbidden', False))
                self.assertNotIn(SECRET, repr(result.as_dict()))
        self.assertEqual(sum(self.inbox.counts(100).values()), 0)

    def test_receipt_is_committed_before_ack_and_survives_a_new_store(self):
        payload = body(message={'message_id': 9, 'date': 0, 'chat': {'id': 42, 'type': 'private'}, 'text': 'Привет'})
        first = self.receiver.receive(payload, SECRET)
        reopened = SQLiteInbox(self.database)
        record = reopened.get(100, 1)
        self.assertEqual((first.status, first.code, first.duplicate), (200, 'accepted', False))
        self.assertEqual(record.payload, json.loads(payload))
        self.assertEqual(record.state, 'pending')
        repeated = WebhookReceiver(reopened, bot_id=100, secret_token=SECRET).receive(payload, SECRET)
        self.assertEqual((repeated.status, repeated.code, repeated.duplicate), (200, 'duplicate', True))
        self.assertEqual(reopened.counts(100)['pending'], 1)

    def test_body_limit_has_exact_boundary_and_overflow_has_no_receipt(self):
        receiver = WebhookReceiver(self.inbox, bot_id=100, secret_token=SECRET, max_body_bytes=128)
        payload = body()
        exact = payload + b' ' * (128 - len(payload))
        self.assertEqual(receiver.receive(exact, SECRET).status, 200)
        self.assertEqual(receiver.receive(exact + b' ', SECRET).status, 413)
        self.assertEqual(self.inbox.counts(100)['pending'], 1)

    def test_malformed_json_duplicate_members_nonfinite_and_invalid_envelope_are_refused(self):
        malformed = [
            b'',
            b'[]',
            b'null',
            b'{}',
            b'\xff',
            b'\xef\xbb\xbf{}',
            b'{"update_id":1,"update_id":2,"message":{}}',
            b'{"update_id":1,"message":{"a":1,"a":2}}',
            b'{"update_id":1,"message":{"value":NaN}}',
            b'{"update_id":1,"message":{"value":1e999}}',
            body(True),
            body(-1),
            body(2**63),
            body(message=None),
            b'{"update_id":1}',
        ]
        for payload in malformed:
            with self.subTest(payload_length=len(payload)):
                self.assertEqual(self.receiver.receive(payload, SECRET).status, 400)
        nested = {'value': 1}
        for _ in range(70):
            nested = {'value': nested}
        self.assertEqual(self.receiver.receive(body(message=nested), SECRET).status, 400)
        self.assertEqual(sum(self.inbox.counts(100).values()), 0)

    def test_future_and_ambiguous_events_are_retained_in_quarantine(self):
        cases = [
            body(1, future_event={'safe': True}),
            body(2, message={}, callback_query={}),
            body(3, message={}, future_metadata=1),
        ]
        for update_id, payload in enumerate(cases, 1):
            response = self.receiver.receive(payload, SECRET)
            record = self.inbox.get(100, update_id)
            self.assertEqual((response.status, response.code), (200, 'quarantined'))
            self.assertEqual((record.reason, record.payload), ('unknown-update-kind', json.loads(payload)))
        self.assertEqual(self.inbox.counts(100)['quarantined'], 3)
        self.assertIsNone(self.inbox.claim(100, 'worker'))

    def test_changed_payload_is_a_conflict_and_does_not_replace_the_first_receipt(self):
        self.receiver.receive(body(message={'text': 'first'}), SECRET)
        result = self.receiver.receive(body(message={'text': 'other'}), SECRET)
        self.assertEqual((result.status, result.code), (409, 'payload-conflict'))
        self.assertEqual(self.inbox.get(100, 1).payload['message']['text'], 'first')

    def test_storage_failure_does_not_ack_or_reflect_diagnostic(self):
        with patch.object(self.inbox, 'receive', side_effect=sqlite3.OperationalError('100:PRIVATE_SECRET')):
            result = self.receiver.receive(body(), SECRET)
        self.assertEqual((result.status, result.code), (503, 'storage-unavailable'))
        self.assertNotIn('PRIVATE_SECRET', repr(result))
        self.assertEqual(sum(self.inbox.counts(100).values()), 0)

    def test_internal_unknown_version_is_durable_but_not_ready_for_processing(self):
        receiver = WebhookReceiver(self.inbox, bot_id=100, secret_token=SECRET, payload_version=2)
        self.assertEqual(receiver.receive(body(), SECRET).code, 'quarantined')
        self.assertEqual(self.inbox.get(100, 1).reason, 'unsupported-version')

    def test_configuration_refused_without_echoing_the_secret(self):
        for kwargs in (
            {'bot_id': True},
            {'bot_id': 0},
            {'secret_token': 'bad:PRIVATE_SECRET'},
            {'secret_token': ''},
            {'max_body_bytes': True},
            {'max_body_bytes': 127},
            {'max_body_bytes': 2**24},
            {'payload_version': True},
            {'payload_version': 0},
        ):
            with self.subTest(keys=list(kwargs)):
                config = {'bot_id': 100, 'secret_token': SECRET} | kwargs
                with self.assertRaises(ValidationFailure) as error:
                    WebhookReceiver(self.inbox, **config)
                self.assertNotIn('PRIVATE_SECRET', str(error.exception))


@integration
class AiohttpWebhookTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from aiohttp.test_utils import TestClient, TestServer

        self.folder = tempfile.TemporaryDirectory()
        self.inbox = SQLiteInbox(Path(self.folder.name) / 'http.sqlite')
        self.inbox.initialize()
        self.receiver = WebhookReceiver(self.inbox, bot_id=100, secret_token=SECRET, max_body_bytes=256)
        self.client = TestClient(TestServer(create_aiohttp_webhook_app(self.receiver)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.folder.cleanup()

    def headers(self):
        return {'Content-Type': 'application/json', 'X-Telegram-Bot-Api-Secret-Token': SECRET}

    async def test_real_http_persists_before_success_and_duplicate_is_safe(self):
        for code in ('accepted', 'duplicate'):
            response = await self.client.post('/telegram/webhook', data=body(), headers=self.headers())
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())['status'], code)
            self.assertIsNotNone(SQLiteInbox(self.inbox.database).get(100, 1))
        self.assertEqual(self.inbox.counts(100)['pending'], 1)

    async def test_http_wrong_or_duplicate_secret_never_admits_event(self):
        from multidict import CIMultiDict

        for headers in (
            {'Content-Type': 'application/json'},
            self.headers() | {'X-Telegram-Bot-Api-Secret-Token': 'wrong'},
            CIMultiDict([*self.headers().items(), ('X-Telegram-Bot-Api-Secret-Token', SECRET)]),
        ):
            response = await self.client.post('/telegram/webhook', data=body(), headers=headers)
            self.assertEqual(response.status, 403)
        self.assertEqual(sum(self.inbox.counts(100).values()), 0)

    async def test_http_malformed_content_compression_and_method_are_refused(self):
        for data, headers, status in [
            (b'bad', self.headers(), 400),
            (body(), self.headers() | {'Content-Type': 'text/plain'}, 415),
            (body(), self.headers() | {'Content-Encoding': 'gzip'}, 415),
            (body(), self.headers() | {'Content-Type': 'application/json; charset=latin1'}, 415),
        ]:
            response = await self.client.post('/telegram/webhook', data=data, headers=headers)
            self.assertEqual(response.status, status)
        response = await self.client.get('/telegram/webhook')
        self.assertEqual(response.status, 405)
        self.assertEqual(sum(self.inbox.counts(100).values()), 0)

    async def test_http_limits_chunked_body_and_does_not_write_overflow(self):
        async def chunks():
            yield b'{"update_id":1,"message":{"text":"'
            yield b'a' * 300
            yield b'"}}'

        response = await self.client.post('/telegram/webhook', data=chunks(), headers=self.headers())
        self.assertEqual(response.status, 413)
        self.assertEqual(sum(self.inbox.counts(100).values()), 0)

    async def test_http_storage_failure_is_503_and_does_not_leak(self):
        with patch.object(self.inbox, 'receive', side_effect=sqlite3.OperationalError('PRIVATE_SECRET')):
            response = await self.client.post('/telegram/webhook', data=body(), headers=self.headers())
        self.assertEqual(response.status, 503)
        self.assertNotIn('PRIVATE_SECRET', await response.text())

    async def test_sdk_decode_failure_can_be_quarantined_after_durable_receipt(self):
        from aiogram.types import Update
        from pydantic import ValidationError

        response = await self.client.post('/telegram/webhook', data=body(), headers=self.headers())
        self.assertEqual(response.status, 200)
        claim = self.inbox.claim(100, 'decoder')
        with self.assertRaises(ValidationError):
            Update.model_validate(claim.payload)
        self.inbox.quarantine(claim, reason='decode-failed')
        self.assertEqual(self.inbox.get(100, 1).reason, 'decode-failed')


if __name__ == '__main__':
    unittest.main()
