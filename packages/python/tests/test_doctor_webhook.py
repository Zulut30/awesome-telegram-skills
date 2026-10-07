"""doctor --webhook: every getWebhookInfo situation gets a concrete recommendation; synthetic responses only."""

import json
import os
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import telegram_patterns.diagnostics as diagnostics
from telegram_patterns.cli import doctor, main

TOKEN = '100:WEBHOOK_PRIVATE_CANARY'
NOW = 1_800_000_000


def checks(info, *, expect=None, secret=None):
    return {
        name: (status, reason, detail, *repair)
        for name, status, reason, detail, *repair in diagnostics._webhook_checks(
            info, expect=expect, secret_env='WEBHOOK_SECRET', secret=secret, now=NOW
        )
    }


class WebhookAnalysisTests(unittest.TestCase):
    def assert_repair(self, finding):
        status, reason, detail, *repair = finding
        if status != 'pass':
            self.assertTrue(repair and repair[0], reason)
            self.assertTrue(repair[1], reason)
            for command in repair[1]:
                self.assertNotIn(TOKEN, json.dumps(command))

    def test_polling_without_webhook(self):
        found = checks({'url': '', 'pending_update_count': 0, 'has_custom_certificate': False})
        self.assertEqual(found['webhook'][:2], ('pass', 'polling-available'))
        self.assertEqual(found['webhook-pending'][:2], ('pass', 'queue-empty'))
        self.assertNotIn('webhook-secret', found)
        waiting = checks({'url': '', 'pending_update_count': 7}, expect='polling')
        self.assertEqual(waiting['webhook-pending'][:2], ('warn', 'updates-waiting'))
        self.assertIn('24 часов', waiting['webhook-pending'][2])
        self.assert_repair(waiting['webhook-pending'])

    def test_webhook_conflicts_with_polling(self):
        info = {
            'url': 'https://bot.example.com:8443/hook/PATH_SECRET?k=QUERY_SECRET',
            'pending_update_count': 3,
            'ip_address': '203.0.113.5',
            'max_connections': 40,
            'has_custom_certificate': True,
        }
        blocked = checks(info, expect='polling')['webhook']
        self.assertEqual(blocked[:2], ('fail', 'webhook-blocks-polling'))
        self.assertIn('409 Conflict', blocked[2])
        self.assertIn('https://bot.example.com:8443/…', blocked[2])
        self.assertIn('IP 203.0.113.5', blocked[2])
        self.assertNotIn('PATH_SECRET', json.dumps(blocked))
        self.assertNotIn('QUERY_SECRET', json.dumps(blocked))
        self.assertIn('drop_pending_updates', blocked[3])
        code = blocked[4][0]['argv'][2]
        self.assertIn("os.environ['BOT_TOKEN']", code)
        self.assertIn('/deleteWebhook', code)
        self.assert_repair(blocked)
        unknown = checks(info)['webhook']
        self.assertEqual(unknown[:2], ('warn', 'webhook-active'))
        self.assertIn('--expect', unknown[4][1]['argv'])
        self.assert_repair(unknown)
        self.assertEqual(checks(info, expect='webhook')['webhook'][:2], ('pass', 'webhook-set'))

    def test_expected_webhook_missing(self):
        found = checks({'url': '', 'pending_update_count': 2}, expect='webhook')
        self.assertEqual(found['webhook'][:2], ('fail', 'webhook-not-set'))
        command = found['webhook'][4][0]
        self.assertTrue(command['requires_substitution'])
        self.assertIn('<WEBHOOK_URL>', command['argv'][2])
        self.assertIn("os.environ['WEBHOOK_SECRET']", command['argv'][2])
        self.assertEqual(found['webhook-secret'][:2], ('warn', 'secret-not-found'))
        self.assert_repair(found['webhook'])

    def test_pending_backlog(self):
        url = 'https://bot.example.com/'
        self.assertEqual(
            checks({'url': url, 'pending_update_count': 0}, expect='webhook')['webhook-pending'][:2],
            ('pass', 'webhook-queue-ok'),
        )
        self.assertEqual(
            checks({'url': url, 'pending_update_count': 150}, expect='webhook')['webhook-pending'][:2],
            ('warn', 'webhook-backlog'),
        )
        recent = checks({'url': url, 'pending_update_count': 4, 'last_error_date': NOW - 60}, expect='webhook')
        self.assertEqual(recent['webhook-pending'][:2], ('warn', 'webhook-backlog'))
        self.assert_repair(recent['webhook-pending'])

    def test_last_error_messages_map_to_specific_repairs(self):
        cases = {
            'Connection refused': 'webhook-unreachable',
            'Connection timed out': 'webhook-unreachable',
            'Failed to resolve host: Name or service not known': 'webhook-unreachable',
            'Read timeout expired': 'webhook-unreachable',
            'SSL error {error:14094418:SSL routines:ssl3_read_bytes:tlsv1 alert unknown ca}': 'webhook-tls',
            'Wrong response from the webhook: 401 Unauthorized': 'webhook-auth-rejected',
            'Wrong response from the webhook: 403 Forbidden': 'webhook-auth-rejected',
            'Wrong response from the webhook: 404 Not Found': 'webhook-path-not-found',
            'Wrong response from the webhook: 502 Bad Gateway': 'webhook-server-error',
            'Wrong response from the webhook: 302 Found': 'webhook-bad-response',
            'Something unexpected': 'webhook-error',
        }
        fixes = set()
        for message, reason in cases.items():
            with self.subTest(message=message):
                finding = checks(
                    {
                        'url': 'https://bot.example.com/hook',
                        'pending_update_count': 1,
                        'last_error_date': NOW - 3 * 3600,
                        'last_error_message': message,
                    },
                    expect='webhook',
                )['webhook-error']
                self.assertEqual(finding[:2], ('warn', reason))
                self.assertIn('3 ч назад', finding[2])
                self.assertIn(message[:40], finding[2])
                self.assert_repair(finding)
                fixes.add(finding[3])
        self.assertEqual(len(fixes), len(set(cases.values())))
        old = checks(
            {
                'url': 'https://bot.example.com/',
                'pending_update_count': 0,
                'last_error_date': NOW - 3 * 86400,
                'last_error_message': 'Connection refused',
            },
            expect='webhook',
        )
        self.assertEqual(old['webhook-error'][:2], ('pass', 'webhook-error-old'))
        self.assertIn('3 дн назад', old['webhook-error'][2])
        clean = checks({'url': 'https://bot.example.com/', 'pending_update_count': 0}, expect='webhook')
        self.assertEqual(clean['webhook-error'][:2], ('pass', 'webhook-no-errors'))
        sync = checks({'url': '', 'pending_update_count': 0, 'last_synchronization_error_date': NOW - 120})
        self.assertEqual(sync['webhook-sync'][:2], ('warn', 'sync-error'))
        self.assert_repair(sync['webhook-sync'])

    def test_secret_token_is_checked_locally_only(self):
        info = {'url': 'https://bot.example.com/hook', 'pending_update_count': 0}
        missing = checks(info, expect='webhook')['webhook-secret']
        self.assertEqual(missing[:2], ('warn', 'secret-not-found'))
        self.assertIn('X-Telegram-Bot-Api-Secret-Token', missing[3])
        self.assertIn('secrets.token_urlsafe', missing[4][0]['argv'][2])
        self.assert_repair(missing)
        for bad in ('has space', 'x' * 257, 'кириллица'):
            with self.subTest(secret=bad):
                invalid = checks(info, expect='webhook', secret=bad)['webhook-secret']
                self.assertEqual(invalid[:2], ('fail', 'secret-invalid'))
                self.assertNotIn(bad, json.dumps(invalid))
        configured = checks(info, expect='webhook', secret='A-z_09' * 10)['webhook-secret']
        self.assertEqual(configured[:2], ('pass', 'secret-configured'))
        self.assertIn('не показывает', configured[2])

    def test_unexpected_field_types_do_not_crash(self):
        found = checks({'url': None, 'pending_update_count': '5', 'last_error_date': True, 'last_error_message': 7})
        self.assertEqual(found['webhook'][:2], ('pass', 'polling-available'))
        self.assertEqual(found['webhook-pending'][:2], ('pass', 'queue-empty'))
        self.assertNotIn('webhook-error', found)
        self.assertEqual(diagnostics._safe_url('https://[2001:db8::1]:88/x'), 'https://[2001:db8::1]:88/…')
        self.assertEqual(diagnostics._safe_url('https://bot.example.com'), 'https://bot.example.com')


class _BotApi(BaseHTTPRequestHandler):
    status = 200
    body = b''
    paths: list[str] = []

    def do_GET(self):
        type(self).paths.append(self.path)
        self.send_response(type(self).status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(type(self).body)))
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *args):
        pass


class DoctorWebhookTests(unittest.TestCase):
    def setUp(self):
        sdk = patch.object(diagnostics, '_sdk_probe', return_value=True)
        sdk.start()
        self.addCleanup(sdk.stop)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), _BotApi)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        base = f'http://127.0.0.1:{self.server.server_address[1]}'
        api = patch.object(diagnostics, '_API_BASE', base)
        api.start()
        self.addCleanup(api.stop)
        environment = patch.dict(os.environ, {'NO_PROXY': '127.0.0.1', 'no_proxy': '127.0.0.1'})
        environment.start()
        self.addCleanup(environment.stop)
        for name in ('BOT_TOKEN', 'WEBHOOK_SECRET'):
            os.environ.pop(name, None)
        _BotApi.paths = []

    def respond(self, status, payload):
        _BotApi.status = status
        _BotApi.body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def by_name(self, report, name):
        return next(item for item in report['checks'] if item['name'] == name)

    def test_live_answer_is_analysed_without_leaking_token(self):
        self.respond(
            200,
            {
                'ok': True,
                'result': {
                    'url': 'https://bot.example.com/hook/PATH_SECRET',
                    'pending_update_count': 12,
                    'last_error_date': int(time.time()) - 30,
                    'last_error_message': 'Wrong response from the webhook: 502 Bad Gateway',
                },
            },
        )
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'BOT_TOKEN': TOKEN}):
            report = doctor(folder, webhook=True, expect='polling')
        self.assertEqual(_BotApi.paths, [f'/bot{TOKEN}/getWebhookInfo'])
        self.assertTrue(report['network'])
        self.assertFalse(report['passed'])
        self.assertIn('getWebhookInfo', report['tool_probes_attempted'])
        self.assertIn('getWebhookInfo', report['limits'])
        self.assertEqual(self.by_name(report, 'token-valid')['reason'], 'token-accepted')
        self.assertEqual(self.by_name(report, 'webhook')['reason'], 'webhook-blocks-polling')
        self.assertEqual(self.by_name(report, 'webhook-pending')['reason'], 'webhook-backlog')
        self.assertEqual(self.by_name(report, 'webhook-error')['reason'], 'webhook-server-error')
        self.assertEqual(self.by_name(report, 'webhook-secret')['reason'], 'secret-not-found')
        dumped = json.dumps(report, ensure_ascii=False)
        self.assertNotIn('WEBHOOK_PRIVATE_CANARY', dumped)
        self.assertNotIn('PATH_SECRET', dumped)

    def test_token_and_secret_come_from_project_env_file(self):
        self.respond(200, {'ok': True, 'result': {'url': 'https://bot.example.com/hook', 'pending_update_count': 0}})
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / '.env').write_text(f'BOT_TOKEN={TOKEN}\nWEBHOOK_SECRET=abc_DEF-123\n', encoding='utf-8')
            report = doctor(folder, webhook=True, expect='webhook')
            plain = doctor(folder)
        self.assertTrue(report['passed'], report)
        self.assertIn('.env проекта', self.by_name(report, 'token-format')['detail'])
        self.assertEqual(self.by_name(report, 'webhook-secret')['reason'], 'secret-configured')
        self.assertNotIn('abc_DEF-123', json.dumps(report, ensure_ascii=False))
        # Without --webhook doctor keeps its contract: local only, .env is not read.
        self.assertFalse(plain['network'])
        self.assertEqual(self.by_name(plain, 'token-format')['reason'], 'token-missing')
        self.assertEqual(len(_BotApi.paths), 1)

    def test_rejected_token_unreachable_api_and_garbage(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'BOT_TOKEN': TOKEN}):
            self.respond(401, {'ok': False, 'error_code': 401, 'description': 'Unauthorized'})
            rejected = doctor(folder, webhook=True)
            self.respond(200, b'<html>proxy page</html>')
            garbage = doctor(folder, webhook=True)
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                closed = probe.getsockname()[1]
            with patch.object(diagnostics, '_API_BASE', f'http://127.0.0.1:{closed}'):
                unreachable = doctor(folder, webhook=True)
        self.assertEqual(self.by_name(rejected, 'token-valid')['reason'], 'token-rejected')
        self.assertEqual(self.by_name(garbage, 'webhook')['reason'], 'api-error')
        self.assertEqual(self.by_name(unreachable, 'webhook')['reason'], 'api-unreachable')
        for report in (rejected, garbage, unreachable):
            self.assertFalse(report['passed'])
            self.assertTrue(report['network'])
            self.assertNotIn('WEBHOOK_PRIVATE_CANARY', json.dumps(report, ensure_ascii=False))
            failed = [item for item in report['checks'] if item['status'] == 'fail']
            self.assertTrue(all(item['remediation']['summary'] and item['remediation']['commands'] for item in failed))

    def test_missing_or_placeholder_token_skips_the_request(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = doctor(folder, webhook=True)
            (Path(folder) / '.env').write_text(
                'BOT_TOKEN=123456789:REPLACE_WITH_YOUR_TEST_BOT_TOKEN\n', encoding='utf-8'
            )
            placeholder = doctor(folder, webhook=True)
            (Path(folder) / '.env').write_text('not a pair\n', encoding='utf-8')
            broken = doctor(folder, webhook=True)
        self.assertEqual(_BotApi.paths, [])
        self.assertEqual(self.by_name(missing, 'token-format')['reason'], 'token-missing')
        self.assertEqual(self.by_name(placeholder, 'token-format')['reason'], 'token-placeholder')
        self.assertEqual(self.by_name(broken, 'token-format')['reason'], 'env-file-invalid')
        for report in (missing, placeholder, broken):
            self.assertFalse(report['network'])
            self.assertFalse(report['passed'])
            self.assertEqual(self.by_name(report, 'webhook')['reason'], 'token-required')

    def test_cli_flags(self):
        self.respond(200, {'ok': True, 'result': {'url': '', 'pending_update_count': 0}})
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {'BOT_TOKEN': TOKEN}),
            patch('sys.stdout') as stdout,
            patch('sys.stderr'),
        ):
            self.assertEqual(main(['doctor', folder, '--webhook', '--expect', 'polling']), 0)
            printed = ''.join(call.args[0] for call in stdout.write.call_args_list)
            with self.assertRaises(SystemExit) as refused:
                main(['doctor', folder, '--expect', 'webhook'])
        self.assertEqual(json.loads(printed)['network'], True)
        self.assertEqual(refused.exception.code, 2)
        with self.assertRaises(ValueError):
            doctor('.', webhook=True, webhook_secret_env='BAD NAME')


if __name__ == '__main__':
    unittest.main()
