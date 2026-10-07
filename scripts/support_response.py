"""Measure the support promise: a maintainer answers every issue within 3 business days.

    python scripts/support_response.py --repo Zulut30/awesome-telegram-skills --output output/support.json

Reads issues of the last --days days through the GitHub REST API (GITHUB_TOKEN is used when set). Issues opened by
maintainers and pull requests are skipped. Business days are Monday to Friday in UTC; holidays are not excluded.
Exits with 1 when an open issue waits longer than the promise without a maintainer comment, so the scheduled
Support response workflow turns red and its owner is notified. The JSON report (median first response, share
answered in time, overdue issues) also feeds the quality board.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import urllib.request
from pathlib import Path

PROMISE_BUSINESS_DAYS = 3
MAINTAINERS = {'OWNER', 'MEMBER', 'COLLABORATOR'}


def parse(stamp: str) -> dt.datetime:
    return dt.datetime.fromisoformat(stamp.replace('Z', '+00:00'))


def business_days(start: dt.datetime, end: dt.datetime) -> int:
    """Weekdays after the start date up to and including the end date."""
    days, day = 0, start.date()
    while day < end.date():
        day += dt.timedelta(days=1)
        days += day.weekday() < 5
    return days


def evaluate(issues: list[dict], comments: dict[int, list[dict]], now: dt.datetime) -> dict:
    waits, overdue, answered_in_time, considered = [], [], 0, 0
    for issue in issues:
        if 'pull_request' in issue or issue.get('author_association') in MAINTAINERS:
            continue
        considered += 1
        created = parse(issue['created_at'])
        replies = [comment for comment in comments.get(issue['number'], [])
                   if comment.get('author_association') in MAINTAINERS and comment['user']['login'] != issue['user']['login']]
        if replies:
            wait = business_days(created, parse(min(reply['created_at'] for reply in replies)))
            waits.append(wait)
            answered_in_time += wait <= PROMISE_BUSINESS_DAYS
        elif issue['state'] == 'open' and business_days(created, now) > PROMISE_BUSINESS_DAYS:
            overdue.append({'number': issue['number'], 'title': issue['title'], 'waiting_business_days': business_days(created, now)})
    return {'promise_business_days': PROMISE_BUSINESS_DAYS, 'issues': considered, 'answered': len(waits),
            'median_first_response_business_days': statistics.median(waits) if waits else None,
            'answered_within_promise': round(answered_in_time / len(waits), 3) if waits else None,
            'overdue': overdue, 'checked_at': now.isoformat(timespec='seconds')}


def fetch(url: str) -> list[dict]:
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'awesome-telegram-skills support check'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    items: list[dict] = []
    while url:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:  # noqa: S310
            items += json.loads(response.read())
            links = response.headers.get('Link', '')
        url = next((part.split(';')[0].strip(' <>') for part in links.split(',') if 'rel="next"' in part), '')
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--repo', required=True, help='OWNER/REPO')
    parser.add_argument('--days', type=int, default=90)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(days=args.days)).isoformat(timespec='seconds')
    api = f'https://api.github.com/repos/{args.repo}'
    issues = [issue for issue in fetch(f'{api}/issues?state=all&since={since}&per_page=100') if parse(issue['created_at']) >= parse(since)]
    comments = {issue['number']: fetch(issue['comments_url'] + '?per_page=100') if issue['comments'] else [] for issue in issues
                if 'pull_request' not in issue}
    report = evaluate(issues, comments, now)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    for item in report['overdue']:
        sys.stderr.write(f"#{item['number']} waits {item['waiting_business_days']} business days: {item['title']}\n")
    return 1 if report['overdue'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
