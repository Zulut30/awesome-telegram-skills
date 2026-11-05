"""Live acceptance report: validation, the test Bot API probe against a local fake and release bundling."""

import datetime as dt
import http.server
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from release_identity import parse_release_version
spec = importlib.util.spec_from_file_location('live_acceptance', ROOT / 'scripts/live_acceptance.py')
live = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = live
spec.loader.exec_module(live)
ReportError = live.ReportError
TODAY = dt.date(2026, 10, 7)
TOKEN = '123456:TEST-ENVIRONMENT-TOKEN-NEVER-STORED-xxxxxxxx'


def valid():
    report = live.template('0.25.0')
    report.update(checked_at='2026-10-06', checked_by='QA team', limitations='Только тестовое окружение.')
    for name, entry in report['scenarios'].items():
        entry.update(bot=f'@example_{name.replace("-", "_")}_bot', status='passed')
        for case in entry['cases'].values():
            case.update(status='passed', note='')
    return report


class FakeBotApi(http.server.BaseHTTPRequestHandler):
    calls: list = []
    fail = False

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])) or b'{}')
        FakeBotApi.calls.append((self.path, body))
        method = self.path.rsplit('/', 1)[1]
        results = {'getMe': {'id': 1, 'is_bot': True, 'username': 'example_shop_bot'},
                   'getWebhookInfo': {'url': '', 'pending_update_count': 0},
                   'getMyCommands': [{'command': 'start', 'description': 'Меню'}],
                   'createInvoiceLink': 'https://t.me/$test-invoice'}
        answer = {'ok': False, 'error_code': 401, 'description': 'Unauthorized'} if FakeBotApi.fail else {'ok': True, 'result': results[method]}
        data = json.dumps(answer).encode()
        self.send_response(401 if FakeBotApi.fail else 200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class ValidationTests(unittest.TestCase):
    def test_rc_cli_creates_canonical_not_run_report_and_check_never_claims_it_passed(self):
        with tempfile.TemporaryDirectory(prefix='live-template-') as temporary:
            root = Path(temporary)
            with patch.object(live, 'ROOT', root), patch('sys.argv', ['live_acceptance.py', 'new', '--version', '1.0.0rc0']), redirect_stdout(io.StringIO()):
                self.assertEqual(live.main(), 0)
            folder = root / 'docs/live-checks/1.0.0-rc.0'
            report = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['release'], '1.0.0-rc.0')
            self.assertTrue(all(entry['status'] == 'not-run' for entry in report['scenarios'].values()))
            self.assertFalse((root / 'docs/live-checks/1.0.0rc0').exists())
            with patch('sys.argv', ['live_acceptance.py', 'check', str(folder), '--version', '1.0.0rc0']), redirect_stderr(io.StringIO()):
                self.assertEqual(live.main(), 1)

    def test_template_claims_nothing_and_a_complete_report_passes(self):
        with self.assertRaises(ReportError):
            live.validate(live.template('0.25.0'), '0.25.0', today=TODAY)
        report = valid()
        shop = report['scenarios']['shop']
        shop['cases']['refund'].update(status='blocked', note='refundStarPayment недоступен для тестового платежа')
        shop['status'] = 'blocked'
        summary = live.validate(report, '0.25.0', today=TODAY)
        self.assertEqual({name: item['status'] for name, item in summary['scenarios'].items()},
                         {'service-bot': 'passed', 'group-bot': 'passed', 'shop': 'blocked'})
        text = live.markdown(report, summary)
        self.assertIn('| shop | blocked | @example_shop_bot | нет |', text)
        self.assertIn('- shop / refund: blocked — refundStarPayment недоступен для тестового платежа', text)

    def test_each_rule_rejects_its_violation(self):
        cases = {
            'release must be 0.25.0': lambda r: r.update(release='0.24.0'),
            'environment must be "test"': lambda r: r.update(environment='production'),
            'checked_at is in the future': lambda r: r.update(checked_at='2026-10-08'),
            'scenarios must be exactly': lambda r: r['scenarios'].pop('shop'),
            'shop.cases must list': lambda r: r['scenarios']['shop']['cases'].pop('refund'),
            'shop.order.status must be one of': lambda r: r['scenarios']['shop']['cases']['order'].update(status='ok'),
            'shop.order.note: required': lambda r: (r['scenarios']['shop']['cases']['order'].update(status='failed'),
                                                    r['scenarios']['shop'].update(status='failed')),
            "shop.status must be 'failed'": lambda r: r['scenarios']['shop']['cases']['order'].update(status='failed', note='x'),
            'shop.bot: public username': lambda r: r['scenarios']['shop'].update(bot='shop'),
            'shop.automated must come from the test Bot API': lambda r: r['scenarios']['shop'].update(automated={'api': 'production'}),
            'shop.automated.username does not match': lambda r: r['scenarios']['shop'].update(automated={'api': 'test', 'username': 'other_bot'}),
            'remove private data': lambda r: r.update(limitations=f'token {TOKEN.replace("TEST-ENVIRONMENT-", "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawA")}'),
        }
        for message, mutate in cases.items():
            report = valid()
            mutate(report)
            with self.subTest(message), self.assertRaisesRegex(ReportError, message.replace('(', r'\(').replace('.', r'\.')):
                live.validate(report, '0.25.0', today=TODAY)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        FakeBotApi.calls, FakeBotApi.fail = [], False
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeBotApi)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.api = f'http://127.0.0.1:{self.server.server_address[1]}'

    def test_probe_uses_the_test_environment_and_never_keeps_the_token(self):
        now = dt.datetime(2026, 10, 6, 12, 0, tzinfo=dt.timezone.utc)
        result = live.probe(TOKEN, 'shop', api=self.api, now=now)
        self.assertEqual([path for path, _ in FakeBotApi.calls],
                         [f'/bot{TOKEN}/test/{method}' for method in ('getMe', 'getWebhookInfo', 'getMyCommands', 'createInvoiceLink')])
        invoice = FakeBotApi.calls[-1][1]
        self.assertEqual((invoice['currency'], invoice['prices'][0]['amount']), ('XTR', 1))
        self.assertEqual(result, {'api': 'test', 'checked_at': '2026-10-06T12:00:00+00:00', 'username': 'example_shop_bot',
                                  'webhook_set': False, 'pending_updates': 0, 'commands': 1, 'stars_invoice_link': True})
        self.assertNotIn(TOKEN, json.dumps(result))
        report = valid()
        report['scenarios']['shop']['automated'] = result
        self.assertTrue(live.validate(report, '0.25.0', today=TODAY)['scenarios']['shop']['automated'])

    def test_a_refused_call_fails_without_echoing_the_token(self):
        FakeBotApi.fail = True
        with self.assertRaises(ReportError) as raised:
            live.probe(TOKEN, 'service-bot', api=self.api)
        self.assertIn('getMe: 401 Unauthorized', str(raised.exception))
        self.assertNotIn(TOKEN, str(raised.exception))


class BundleTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.repo = Path(folder.name) / 'repo'
        (self.repo / 'packages/python').mkdir(parents=True)
        for arguments in (('init', '-q'), ('config', 'user.email', 'release@example.invalid'), ('config', 'user.name', 'Fixture'),
                          ('config', 'commit.gpgsign', 'false'), ('config', 'tag.gpgsign', 'false')):
            self.git(*arguments)

    def git(self, *arguments):
        subprocess.run(['git', *arguments], cwd=self.repo, check=True, capture_output=True)

    def release(self, version, report=None):
        release = parse_release_version(version)
        (self.repo / 'packages/python/pyproject.toml').write_text(f'[project]\nversion = "{release.python_version}"\n', encoding='utf-8')
        (self.repo / 'packages/typescript').mkdir(exist_ok=True)
        (self.repo / 'packages/typescript/package.json').write_text(json.dumps({'version': release.npm_version}), encoding='utf-8')
        if report is not None:
            folder = self.repo / live.REPORTS / release.identity
            folder.mkdir(parents=True)
            (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', version, '--allow-empty')
        self.git('tag', release.tag)

    def test_old_releases_skip_new_ones_require_a_valid_report(self):
        self.release('0.24.0')
        self.assertTrue(live.bundle('v0.24.0', self.repo.parent / 'a', self.repo)['skipped'])
        self.release('0.25.0')
        with self.assertRaisesRegex(ReportError, 'required from 0.25.0'):
            live.bundle('v0.25.0', self.repo.parent / 'b', self.repo)

    def test_bundle_writes_the_report_assets(self):
        self.release('0.25.0', valid())
        result = live.bundle('v0.25.0', self.repo.parent / 'out', self.repo)
        self.assertFalse(result['skipped'])
        with zipfile.ZipFile(self.repo.parent / 'out/live-report-0.25.0.zip') as archive:
            self.assertEqual(archive.namelist(), ['report.json'])
        self.assertIn('| service-bot | passed |', (self.repo.parent / 'out/live-report-0.25.0.md').read_text(encoding='utf-8'))

    def test_rc_missing_report_cannot_bypass_base_threshold(self):
        self.release('0.25.0rc1')
        with self.assertRaisesRegex(ReportError, 'docs/live-checks/0.25.0-rc.1/report.json is required'):
            live.bundle('v0.25.0-rc.1', self.repo.parent / 'out', self.repo)

    def test_even_rc_below_historical_threshold_requires_a_report(self):
        self.release('0.24.0rc0')
        with self.assertRaisesRegex(ReportError, 'report.json is required'):
            live.bundle('v0.24.0-rc.0', self.repo.parent / 'out', self.repo)

    def test_rc_and_final_require_passed_while_numeric_zero_retains_blocked_report(self):
        for version in ['0.25.0', '0.25.1-rc.1', '1.0.0']:
            report = valid()
            report['release'] = version
            entry = report['scenarios']['shop']
            entry['status'] = 'blocked'
            for case in entry['cases'].values():
                case.update(status='blocked', note='Fixture lacks a test bot')
            self.release(version, report)
            out = self.repo.parent / version
            if version == '0.25.0':
                self.assertEqual(live.bundle('v' + version, out, self.repo)['scenarios']['shop']['status'], 'blocked')
            else:
                with self.assertRaisesRegex(ReportError, 'require every acceptance status to be passed'):
                    live.bundle('v' + version, out, self.repo)
                self.assertFalse(out.exists())

    def test_passed_rc_reads_committed_identity_and_keeps_canonical_archive_name(self):
        report = valid()
        report['release'] = '1.0.0-rc.1'
        self.release('1.0.0rc1', report)
        (self.repo / 'packages/python/pyproject.toml').write_text('[project]\nversion="9.9.9"', encoding='utf-8')
        (self.repo / 'packages/typescript/package.json').write_text('{"version":"invalid"}', encoding='utf-8')
        out = self.repo.parent / 'out'
        self.assertEqual(live.bundle('v1.0.0-rc.1', out, self.repo)['release'], '1.0.0-rc.1')
        self.assertTrue((out / 'live-report-1.0.0-rc.1.zip').is_file())
        report['release'] = '1.0.0rc1'
        with self.assertRaisesRegex(ReportError, 'release must be 1.0.0-rc.1'):
            live.validate(report, '1.0.0rc1', today=TODAY)

    def test_rc_templates_are_canonical_and_do_not_claim_acceptance(self):
        report = live.template('1.0.0rc0')
        self.assertEqual(report['release'], '1.0.0-rc.0')
        self.assertTrue(all(entry['status'] == 'not-run' for entry in report['scenarios'].values()))
        with self.assertRaisesRegex(ReportError, 'checked_at'):
            live.validate(report, '1.0.0-rc.0')


if __name__ == '__main__':
    unittest.main()
