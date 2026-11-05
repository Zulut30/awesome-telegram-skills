"""Require every concrete GitHub Actions job to succeed, including matrix cells and reruns."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any


def fetch_jobs(repository: str, run_id: int, token: str, *,
               opener: Callable[..., Any] = urllib.request.urlopen) -> list[dict[str, Any]]:
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid repository identity')
    if type(run_id) is not int or run_id <= 0 or not token or any(char in token for char in '\r\n'):
        raise ValueError('A run identity and read-only token are required')
    collected: list[dict[str, Any]] = []
    expected: int | None = None
    for page in range(1, 101):
        url = f'https://api.github.com/repos/{repository}/actions/runs/{run_id}/jobs?filter=all&per_page=100&page={page}'
        request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json',
                                                       'Authorization': 'Bearer ' + token})
        with opener(request, timeout=20) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError('Job response exceeds the audit limit')
        data = json.loads(raw)
        if not isinstance(data, dict) or type(data.get('total_count')) is not int or not isinstance(data.get('jobs'), list):
            raise ValueError('Invalid job response schema')
        total, rows = data['total_count'], data['jobs']
        if total < 1 or len(rows) > 100 or (expected is not None and total != expected):
            raise ValueError('Job set is empty, changed or incomplete')
        expected = total
        if any(not isinstance(row, dict) or row.get('run_id') != run_id for row in rows):
            raise ValueError('Job belongs to a different run')
        collected.extend(rows)
        if len(collected) == expected:
            return collected
        if not rows or len(collected) > expected:
            raise ValueError('Job pagination is incomplete')
    raise ValueError('Too many job pages to audit')


def audit_jobs(jobs: list[dict[str, Any]], head_sha: str, *, current_job: str,
               minimum_jobs: int = 1) -> dict[str, Any]:
    if not re.fullmatch(r'[0-9a-f]{40}', head_sha) or not current_job or minimum_jobs < 1:
        raise ValueError('Invalid audit context')
    ids: set[int] = set()
    attempts: set[tuple[str, int]] = set()
    latest: dict[str, dict[str, Any]] = {}
    for job in jobs:
        identifier, attempt, name = job.get('id'), job.get('run_attempt'), job.get('name')
        if (type(identifier) is not int or identifier <= 0 or type(attempt) is not int or attempt < 1
                or not isinstance(name, str) or not name or len(name) > 512):
            raise ValueError('Invalid concrete job identity')
        if identifier in ids or (name, attempt) in attempts:
            raise ValueError('Duplicate job identity or ambiguous matrix name')
        ids.add(identifier)
        attempts.add((name, attempt))
        if job.get('head_sha') != head_sha:
            raise ValueError('Job source does not match the required commit')
        if name == current_job:
            continue
        if name not in latest or attempt > latest[name]['run_attempt']:
            latest[name] = job
    if len(latest) < minimum_jobs:
        raise ValueError('Not enough concrete jobs to prove required checks')
    failed = [{'name': name, 'status': job.get('status'), 'conclusion': job.get('conclusion')}
              for name, job in sorted(latest.items())
              if job.get('status') != 'completed' or job.get('conclusion') != 'success']
    return {'passed': not failed, 'head_sha': head_sha, 'checked': len(latest), 'failed': failed,
            'scope': 'Latest attempt of each concrete job; a matrix cancellation cannot be hidden by needs.result.'}


def main() -> int:
    try:
        needs = json.loads(os.environ['REQUIRED_NEEDS'])
        if not isinstance(needs, dict) or not needs or any(
                not isinstance(result, dict) or result.get('result') != 'success' for result in needs.values()):
            raise ValueError('A required dependency did not succeed')
        jobs = fetch_jobs(os.environ['GITHUB_REPOSITORY'], int(os.environ['GITHUB_RUN_ID']),
                          os.environ['GITHUB_TOKEN'])
        # pull_request jobs identify the PR head; GITHUB_SHA identifies the tested merge tree.
        # https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request
        report = audit_jobs(jobs, os.environ['REQUIRED_HEAD_SHA'],
                            current_job=os.environ['REQUIRED_JOB_NAME'], minimum_jobs=len(needs))
        tested_sha = os.environ['GITHUB_SHA']
        if not re.fullmatch(r'[0-9a-f]{40}', tested_sha):
            raise ValueError('Invalid tested checkout identity')
        report['tested_sha'] = tested_sha
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report['passed'] else 1
    except (KeyError, ValueError, UnicodeError, OSError, urllib.error.URLError):
        # No raw HTTP body, URL exception or inherited token appears in the CI log.
        print(json.dumps({'passed': False, 'error': 'Required job audit could not prove a complete successful run'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
