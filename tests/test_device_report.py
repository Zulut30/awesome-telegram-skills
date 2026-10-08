"""Release device report: validation rules, release-notes table and bundling from a git tag."""

import datetime as dt
import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('device_report', ROOT / 'scripts/device_report.py')
device_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(device_report)
ReportError = device_report.ReportError
PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 32
TODAY = dt.date(2026, 10, 7)


def valid():
    report = device_report.template('0.25.0')
    report.update(checked_at='2026-10-06', checked_by='QA team', limitations='Только тестовое окружение.')
    for name, entry in report['platforms'].items():
        entry.update(device=f'{name} device', os=f'{name} os', telegram=f'Telegram for {name} 12.0', status='passed',
                     screenshots=[f'{name}-light.png'])
        for case in entry['cases'].values():
            case.update(status='passed', note='')
    return report, {f'{name}-light.png': PNG for name in device_report.PLATFORMS}


class ValidationTests(unittest.TestCase):
    def check(self, report, files):
        return device_report.validate(report, '0.25.0', {**files, 'report.json': b'{}'}, today=TODAY)

    def test_template_claims_nothing_and_is_not_accepted_as_a_report(self):
        report = device_report.template('0.25.0')
        self.assertEqual(set(report['platforms']), {'ios', 'android', 'desktop', 'web'})
        for entry in report['platforms'].values():
            self.assertEqual({case['status'] for case in entry['cases'].values()}, {'not-run'})
        with self.assertRaises(ReportError):
            self.check(report, {})

    def test_complete_report_passes_and_renders_release_notes(self):
        report, files = valid()
        android = report['platforms']['android']
        android['cases']['back-button'].update(status='failed', note='Системный назад закрывает без подтверждения')
        android['status'] = 'failed'
        web = report['platforms']['web']
        for case in web['cases'].values():
            case.update(status='not-run', note='HTTPS-туннель недоступен')
        web.update(status='not-run', screenshots=[])
        del files['web-light.png']
        summary = self.check(report, files)
        self.assertEqual({name: item['status'] for name, item in summary['platforms'].items()},
                         {'ios': 'passed', 'android': 'failed', 'desktop': 'passed', 'web': 'not-run'})
        text = device_report.markdown(report, summary)
        self.assertIn('| android | failed | android device, android os | Telegram for android 12.0 | 1 |', text)
        self.assertIn('- android / back-button: failed — Системный назад закрывает без подтверждения', text)
        self.assertIn('- web / cold-launch: not-run — HTTPS-туннель недоступен', text)
        self.assertIn('Ограничения: Только тестовое окружение.', text)

    def test_every_rule_rejects_its_violation(self):
        cases = {
            'other release': (lambda r, f: r.update(release='0.24.0'), 'not 0.25.0'),
            'schema': (lambda r, f: r.update(schema_version=2), 'schema_version 1'),
            'missing platform': (lambda r, f: r['platforms'].pop('web'), 'platforms must be exactly'),
            'unknown case': (lambda r, f: r['platforms']['ios']['cases'].update(extra={'status': 'passed'}), 'ios.cases must list'),
            'bad status': (lambda r, f: r['platforms']['ios']['cases']['theme'].update(status='ok'), 'ios.theme.status'),
            'failed without note': (lambda r, f: (r['platforms']['ios']['cases']['theme'].update(status='failed'),
                                                  r['platforms']['ios'].update(status='failed')), 'ios.theme.note: required'),
            'platform status mismatch': (lambda r, f: r['platforms']['ios']['cases']['theme'].update(status='failed', note='x'),
                                         "ios.status must be 'failed'"),
            'checked without screenshot': (lambda r, f: r['platforms']['ios'].update(screenshots=[]), 'at least one screenshot'),
            'missing screenshot file': (lambda r, f: f.pop('ios-light.png'), 'ios-light.png is missing'),
            'not an image': (lambda r, f: f.update({'ios-light.png': b'GIF89a'}), 'PNG or JPEG'),
            'oversized image': (lambda r, f: f.update({'ios-light.png': PNG + b'\0' * device_report.MAX_IMAGE_BYTES}), 'up to 2 MiB'),
            'unsafe name': (lambda r, f: r['platforms']['ios'].update(screenshots=['../ios.png']), 'unique lowercase'),
            'duplicate screenshot': (lambda r, f: r['platforms']['android'].update(screenshots=['ios-light.png']), 'unique lowercase'),
            'unreferenced file': (lambda r, f: f.update({'notes.txt': b'x'}), 'Unreferenced files: notes.txt'),
            'future date': (lambda r, f: r.update(checked_at='2026-10-08'), 'in the future'),
            'no date': (lambda r, f: r.update(checked_at=''), 'checked_at: date'),
            'missing device': (lambda r, f: r['platforms']['ios'].update(device=''), 'ios.device: required'),
            'bot token': (lambda r, f: r.update(limitations='token 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawA'), 'private data'),
            'phone number': (lambda r, f: r['platforms']['ios']['cases']['theme'].update(note='аккаунт +7 900 123-45-67'), 'private data'),
            'e-mail': (lambda r, f: r.update(checked_by='qa@example.com'), 'private data'),
        }
        for name, (mutate, message) in cases.items():
            report, files = valid()
            mutate(report, files)
            with self.subTest(name), self.assertRaisesRegex(ReportError, re.escape(message)):
                self.check(report, files)
        report, files = valid()
        self.assertEqual(self.check(report, files)['release'], '0.25.0')


class BundleTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.repo = Path(folder.name) / 'repo'
        (self.repo / 'packages/python').mkdir(parents=True)
        self.git('init', '-q')
        self.git('config', 'user.email', 'release@example.invalid')
        self.git('config', 'user.name', 'Release fixture')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'tag.gpgsign', 'false')

    def git(self, *arguments):
        subprocess.run(['git', *arguments], cwd=self.repo, check=True, capture_output=True)

    def release(self, version, report=None, files=None, extra=None):
        (self.repo / 'packages/python/pyproject.toml').write_text(f'[project]\nversion = "{version}"\n', encoding='utf-8')
        if report is not None:
            folder = self.repo / device_report.REPORTS / version
            folder.mkdir(parents=True)
            (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
            for name, data in (files or {}).items():
                (folder / name).write_bytes(data)
            for name, data in (extra or {}).items():
                (folder / name).parent.mkdir(parents=True, exist_ok=True)
                (folder / name).write_bytes(data)
        self.git('add', '-A')
        self.git('commit', '-q', '-m', version, '--allow-empty')
        self.git('tag', f'v{version}')

    def test_older_releases_are_skipped_and_new_ones_require_a_report(self):
        self.release('0.24.0')
        out = Path(self.repo.parent / 'out')
        self.assertTrue(device_report.bundle('v0.24.0', out, self.repo)['skipped'])
        self.release('0.25.0')
        with self.assertRaisesRegex(ReportError, 'required from 0.25.0'):
            device_report.bundle('v0.25.0', out, self.repo)

    def test_bundle_reads_the_tag_and_writes_reproducible_assets(self):
        report, files = valid()
        report['checked_at'] = '2026-10-01'
        self.release('0.25.0', report, files)
        # The working tree may differ from the tag: the bundle must use the committed report.
        (self.repo / device_report.REPORTS / '0.25.0/report.json').write_text('{}', encoding='utf-8')
        first, second = self.repo.parent / 'a', self.repo.parent / 'b'
        result = device_report.bundle('v0.25.0', first, self.repo)
        device_report.bundle('v0.25.0', second, self.repo)
        self.assertFalse(result['skipped'])
        archive = first / 'device-report-0.25.0.zip'
        self.assertEqual(archive.read_bytes(), (second / 'device-report-0.25.0.zip').read_bytes())
        with zipfile.ZipFile(archive) as content:
            self.assertEqual(sorted(content.namelist()), sorted(['report.json', *files]))
        self.assertIn('| ios | passed |', (first / 'device-report-0.25.0.md').read_text(encoding='utf-8'))

    def test_nested_or_invalid_report_in_the_tag_fails(self):
        report, files = valid()
        report['checked_at'] = '2026-10-01'
        self.release('0.25.0', report, files, extra={'raw/ios.png': PNG})
        with self.assertRaisesRegex(ReportError, 'Nested files'):
            device_report.bundle('v0.25.0', self.repo.parent / 'out', self.repo)


if __name__ == '__main__':
    unittest.main()
