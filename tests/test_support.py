"""Best-effort support target: unchanged overdue observations and real CLI file output."""

import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('support_response', ROOT / 'scripts/support_response.py')
support = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = support
spec.loader.exec_module(support)
NOW = dt.datetime(2026, 10, 7, 12, 0, tzinfo=dt.timezone.utc)  # Wednesday


def issue(number, created, author='user', association='NONE', state='open'):
    return {'number': number, 'title': f'Issue {number}', 'created_at': created, 'state': state,
            'user': {'login': author}, 'author_association': association, 'comments_url': ''}


def comment(created, author='maintainer', association='OWNER'):
    return {'created_at': created, 'user': {'login': author}, 'author_association': association}


class SupportResponseTests(unittest.TestCase):
    def test_business_days_skip_weekends(self):
        friday = dt.datetime(2026, 10, 2, 18, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(support.business_days(friday, dt.datetime(2026, 10, 5, 9, 0, tzinfo=dt.timezone.utc)), 1)
        self.assertEqual(support.business_days(friday, NOW), 3)
        self.assertEqual(support.business_days(NOW, NOW), 0)

    def test_overdue_answered_and_skipped_issues(self):
        issues = [
            issue(1, '2026-10-01T10:00:00Z'),                                   # 4 business days, no answer: overdue
            issue(2, '2026-10-02T10:00:00Z'),                                   # 3 business days: still within target
            issue(3, '2026-09-28T10:00:00Z', state='closed'),                   # answered on day 2
            issue(4, '2026-09-21T10:00:00Z'),                                   # answered late, on day 5
            issue(5, '2026-09-01T10:00:00Z', author='maintainer', association='OWNER'),  # opened by a maintainer
            dict(issue(6, '2026-09-01T10:00:00Z'), pull_request={}),            # pull request
        ]
        comments = {1: [comment('2026-10-01T11:00:00Z', author='user', association='NONE')],
                    3: [comment('2026-09-30T09:00:00Z')],
                    4: [comment('2026-09-25T09:00:00Z', association='COLLABORATOR'), comment('2026-09-28T09:00:00Z')]}
        report = support.evaluate(issues, comments, NOW)
        self.assertEqual(report['issues'], 4)
        self.assertEqual(report['answered'], 2)
        self.assertEqual(report['overdue'], [{'number': 1, 'title': 'Issue 1', 'waiting_business_days': 4}])
        self.assertEqual(report['median_first_response_business_days'], 3.0)
        self.assertEqual(report['answered_within_promise'], 0.5)
        self.assertEqual(report['answered_within_target'], 0.5)
        self.assertEqual(report['policy_mode'], 'best-effort-no-sla')
        self.assertEqual(report['target_business_days'], 3)
        self.assertEqual(report['promise_business_days'], report['target_business_days'])

    def test_channel_is_documented_and_forms_exist(self):
        text = (ROOT / 'SUPPORT.md').read_text(encoding='utf-8')
        self.assertIn('не гарантированный срок и не SLA', text)
        self.assertEqual(support.RESPONSE_TARGET_BUSINESS_DAYS, 3)
        self.assertEqual(support.PROMISE_BUSINESS_DAYS, support.RESPONSE_TARGET_BUSINESS_DAYS)
        for path in ('.github/ISSUE_TEMPLATE/question.yml', '.github/DISCUSSION_TEMPLATE/q-a.yml', '.github/workflows/support-response.yml'):
            self.assertTrue((ROOT / path).is_file(), path)
        for readme in ('README.md', 'README.en.md'):
            self.assertIn('(SUPPORT.md)', (ROOT / readme).read_text(encoding='utf-8'))
        workflow = (ROOT / '.github/workflows/support-response.yml').read_text(encoding='utf-8')
        self.assertIn("cron: '41 6 * * 1-5'", workflow)
        self.assertIn('python scripts/support_response.py --repo "$GITHUB_REPOSITORY"', workflow)

    def test_cli_keeps_overdue_failure_and_writes_target_metrics_with_legacy_aliases(self):
        created = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=14)
        stamp = lambda day: day.isoformat(timespec='seconds')
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if self.path.startswith('/issues?'):
                    payload = [dict(issue(number, stamp(created)), comments=int(number != 401),
                                    comments_url=f'http://127.0.0.1:{self.server.server_port}/comments/{number}')
                               for number in (401, 402, 403)]
                elif self.path == '/comments/402?per_page=100':
                    payload = [comment(stamp(created + dt.timedelta(days=2)))]
                elif self.path == '/comments/403?per_page=100':
                    payload = [comment(stamp(created + dt.timedelta(days=8)))]
                else:
                    self.send_error(404)
                    return
                raw = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_):
                pass

        wrapper = '''
import importlib.util,sys
script,base,target=sys.argv[1:]
spec=importlib.util.spec_from_file_location('support_cli_fixture',script)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
fetch=module.fetch
def loopback(url):
    prefix='https://api.github.com/repos/fixture/repo/issues?'
    if url.startswith(prefix): url=base+'/issues?'+url.split('?',1)[1]
    elif not url.startswith(base+'/'): raise AssertionError('Unexpected external URL')
    return fetch(url)
module.fetch=loopback
sys.argv=[script,'--repo','fixture/repo','--output',target]
sys.exit(module.main())
'''
        with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server, tempfile.TemporaryDirectory() as folder:
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
            thread.start()
            try:
                root = Path(folder)
                sentinel = root / 'caller-owned.txt'
                sentinel.write_bytes(b'caller-owned\n')
                target = root / 'reports' / 'support.json'
                environment = {**os.environ, 'GITHUB_TOKEN': '', 'BOT_TOKEN': 'SUPPORT_PRIVATE_CANARY'}
                result = subprocess.run(
                    [sys.executable, '-c', wrapper, str(ROOT / 'scripts/support_response.py'),
                     f'http://127.0.0.1:{server.server_port}', str(target)],
                    capture_output=True, text=True, encoding='utf8', env=environment, timeout=20, check=False)
                self.assertEqual(result.returncode, 1, result.stderr)
                saved = json.loads(target.read_text(encoding='utf8'))
                self.assertEqual(saved, json.loads(result.stdout))
                self.assertEqual(saved['policy_mode'], 'best-effort-no-sla')
                self.assertEqual(saved['target_business_days'], 3)
                self.assertEqual(saved['promise_business_days'], 3)
                self.assertEqual(saved['answered'], 2)
                self.assertEqual(saved['answered_within_target'], 0.5)
                self.assertEqual(saved['answered_within_promise'], 0.5)
                self.assertEqual([row['number'] for row in saved['overdue']], [401])
                self.assertGreater(saved['overdue'][0]['waiting_business_days'], 3)
                self.assertIn('#401 waits ', result.stderr)
                self.assertNotIn('SUPPORT_PRIVATE_CANARY', target.read_text() + result.stdout + result.stderr)
                self.assertEqual(sentinel.read_bytes(), b'caller-owned\n')
                self.assertEqual(len(requests), 3)
            finally:
                server.shutdown()
                thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
