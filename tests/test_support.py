"""Support channel: forms, the 3-business-day promise and its measurement (fixtures, no network)."""

import datetime as dt
import importlib.util
import sys
import unittest
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
            issue(2, '2026-10-02T10:00:00Z'),                                   # 3 business days: still within the promise
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

    def test_channel_is_documented_and_forms_exist(self):
        text = (ROOT / 'SUPPORT.md').read_text(encoding='utf-8')
        self.assertIn('в течение 3 рабочих дней', text)
        self.assertEqual(support.PROMISE_BUSINESS_DAYS, 3)
        for path in ('.github/ISSUE_TEMPLATE/question.yml', '.github/DISCUSSION_TEMPLATE/q-a.yml', '.github/workflows/support-response.yml'):
            self.assertTrue((ROOT / path).is_file(), path)
        for readme in ('README.md', 'README.en.md'):
            self.assertIn('(SUPPORT.md)', (ROOT / readme).read_text(encoding='utf-8'))
        workflow = (ROOT / '.github/workflows/support-response.yml').read_text(encoding='utf-8')
        self.assertIn("cron: '41 6 * * 1-5'", workflow)
        self.assertIn('python scripts/support_response.py --repo "$GITHUB_REPOSITORY"', workflow)


if __name__ == '__main__':
    unittest.main()
