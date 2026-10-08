"""Telegram test environment: separate accounts and bots, requests to /bot<token>/test/<method>."""

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiogram import Dispatcher
from aiogram.client.telegram import PRODUCTION, TEST, TelegramAPIServer
from aiogram.methods import GetMe
from aiogram.types import User

import telegram_patterns.aiogram as adapter
import telegram_patterns.diagnostics as diagnostics
from telegram_patterns import BotSettings
from telegram_patterns.cli import doctor
from telegram_patterns.errors import AuthenticationRequired
from telegram_patterns.testing import StubSession

TOKEN = '100:TEST_ENV_PRIVATE_CANARY'
BOT_USER = User(id=100, is_bot=True, first_name='Fixture', username='component_bot')


class _Api(BaseHTTPRequestHandler):
    paths: list[str] = []
    status = 401
    body = b'{"ok":false,"error_code":401,"description":"Unauthorized"}'

    def do_GET(self):
        self.reply()

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length') or 0))
        self.reply()

    def reply(self):
        type(self).paths.append(self.path)
        self.send_response(type(self).status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(type(self).body)))
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *args):
        pass


class LocalApiCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), _Api)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'
        environment = patch.dict(os.environ, {'NO_PROXY': '127.0.0.1', 'no_proxy': '127.0.0.1'})
        environment.start()
        self.addCleanup(environment.stop)
        for name in ('BOT_TOKEN', 'TELEGRAM_TEST_ENVIRONMENT', 'WEBHOOK_SECRET'):
            os.environ.pop(name, None)
        _Api.paths = []


class SettingsTests(unittest.TestCase):
    def test_flag_values(self):
        for value, expected in (
            ('1', True),
            ('true', True),
            ('YES', True),
            (' on ', True),
            ('', False),
            ('0', False),
            ('false', False),
            ('No', False),
            ('off', False),
        ):
            with self.subTest(value=value):
                settings = BotSettings.from_env(environ={'BOT_TOKEN': TOKEN, 'TELEGRAM_TEST_ENVIRONMENT': value})
                self.assertIs(settings.test_environment, expected)
        self.assertFalse(BotSettings.from_env(environ={'BOT_TOKEN': TOKEN}).test_environment)
        with self.assertRaisesRegex(ValueError, 'TELEGRAM_TEST_ENVIRONMENT must be') as raised:
            BotSettings.from_env(environ={'BOT_TOKEN': TOKEN, 'TELEGRAM_TEST_ENVIRONMENT': 'SECRET_FLAG'})
        self.assertNotIn('SECRET_FLAG', str(raised.exception))
        custom = BotSettings.from_env(
            environ={'BOT_TOKEN': TOKEN, 'STAGING_TG': '1'}, test_environment_var='STAGING_TG'
        )
        self.assertTrue(custom.test_environment)
        with self.assertRaises(ValueError):
            BotSettings.from_env(environ={'BOT_TOKEN': TOKEN}, test_environment_var='bad name')
        with self.assertRaises(ValueError):
            BotSettings(TOKEN, test_environment='yes')
        self.assertNotIn('TEST_ENV_PRIVATE_CANARY', repr(BotSettings(TOKEN, test_environment=True)))

    def test_flag_from_env_file_and_environment_wins(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / '.env'
            env.write_text(f'BOT_TOKEN={TOKEN}\nTELEGRAM_TEST_ENVIRONMENT=1\n', encoding='utf-8')
            self.assertTrue(BotSettings.from_env(environ={}, env_file=env).test_environment)
            self.assertFalse(
                BotSettings.from_env(environ={'TELEGRAM_TEST_ENVIRONMENT': '0'}, env_file=env).test_environment
            )


class RunBotTests(LocalApiCase):
    async def test_default_session_targets_test_server(self):
        local_test = TelegramAPIServer(
            base=self.base + '/bot{token}/test/{method}', file=self.base + '/file/bot{token}/test/{path}'
        )
        dp = Dispatcher()
        with patch.object(adapter, 'TEST', local_test), patch.object(dp, 'start_polling', new=AsyncMock()) as polling:
            with self.assertRaises(AuthenticationRequired) as caught:
                await adapter.run_bot(dp, BotSettings(TOKEN, test_environment=True), handle_signals=False)
            polling.assert_not_called()
        self.assertEqual(_Api.paths, [f'/bot{TOKEN}/test/getMe'])
        self.assertIn('test environment', str(caught.exception))
        self.assertIn('@BotFather', str(caught.exception))
        self.assertNotIn('TEST_ENV_PRIVATE_CANARY', str(caught.exception))

    async def test_main_environment_unchanged(self):
        local_main = TelegramAPIServer.from_base(self.base)
        from aiogram.client.session.aiohttp import AiohttpSession

        dp = Dispatcher()
        with patch.object(dp, 'start_polling', new=AsyncMock()):
            with self.assertRaises(AuthenticationRequired) as caught:
                await adapter.run_bot(
                    dp, BotSettings(TOKEN), session=AiohttpSession(api=local_main), handle_signals=False
                )
        self.assertEqual(_Api.paths, [f'/bot{TOKEN}/getMe'])
        self.assertNotIn('test environment', str(caught.exception))

    async def test_supplied_session_must_already_target_test_server(self):
        production = StubSession()
        self.assertIs(production.api, PRODUCTION)
        with self.assertRaisesRegex(ValueError, 'api=aiogram.client.telegram.TEST'):
            await adapter.run_bot(Dispatcher(), BotSettings(TOKEN, test_environment=True), session=production)
        self.assertEqual(production.calls, [])
        session = StubSession(api=TEST).respond(GetMe, BOT_USER)
        dp = Dispatcher()
        with patch.object(dp, 'start_polling', new=AsyncMock()) as polling:
            await adapter.run_bot(dp, BotSettings(TOKEN, test_environment=True), session=session, handle_signals=False)
        polling.assert_awaited_once()
        self.assertEqual([type(call) for call in session.calls], [GetMe])
        self.assertTrue(session.closed)


class DoctorTests(LocalApiCase):
    def setUp(self):
        super().setUp()
        sdk = patch.object(diagnostics, '_sdk_probe', return_value=True)
        sdk.start()
        self.addCleanup(sdk.stop)
        api = patch.object(diagnostics, '_API_BASE', self.base)
        api.start()
        self.addCleanup(api.stop)

    def by_name(self, report, name):
        return next(item for item in report['checks'] if item['name'] == name)

    def test_doctor_uses_test_path_and_explains_separate_bots(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / '.env').write_text(f'BOT_TOKEN={TOKEN}\nTELEGRAM_TEST_ENVIRONMENT=1\n', encoding='utf-8')
            report = doctor(folder, webhook=True)
        self.assertEqual(_Api.paths, [f'/bot{TOKEN}/test/getWebhookInfo'])
        self.assertEqual(self.by_name(report, 'telegram-environment')['reason'], 'test-environment')
        rejected = self.by_name(report, 'token-valid')
        self.assertEqual(rejected['reason'], 'token-rejected')
        self.assertIn('тестового аккаунта', rejected['remediation']['summary'])
        self.assertNotIn('TEST_ENV_PRIVATE_CANARY', json.dumps(report, ensure_ascii=False))

    def test_doctor_commands_keep_test_path(self):
        _Api.status = 200
        _Api.body = json.dumps(
            {'ok': True, 'result': {'url': 'https://bot.example.com/hook', 'pending_update_count': 0}}
        ).encode()
        self.addCleanup(setattr, _Api, 'status', 401)
        self.addCleanup(setattr, _Api, 'body', b'{"ok":false,"error_code":401,"description":"Unauthorized"}')
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {'BOT_TOKEN': TOKEN, 'TELEGRAM_TEST_ENVIRONMENT': 'true'}),
        ):
            report = doctor(folder, webhook=True, expect='polling')
        delete = self.by_name(report, 'webhook')['remediation']['commands'][0]['argv'][2]
        self.assertIn("/test/deleteWebhook", delete)

    def test_invalid_flag_skips_request(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {'BOT_TOKEN': TOKEN, 'TELEGRAM_TEST_ENVIRONMENT': 'maybe'}),
        ):
            report = doctor(folder, webhook=True)
        self.assertEqual(_Api.paths, [])
        self.assertEqual(self.by_name(report, 'telegram-environment')['reason'], 'test-environment-invalid')
        self.assertFalse(report['passed'])
        self.assertFalse(report['network'])


if __name__ == '__main__':
    unittest.main()
