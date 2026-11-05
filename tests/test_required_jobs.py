"""Concrete matrix failures must block the gate even when GitHub needs.result says success."""
from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from scripts import check_required_jobs as gate

HEAD = 'a' * 40
MERGE = 'b' * 40
SELF = 'Required checks passed'


def job(identifier, name, conclusion='success', *, attempt=1, status='completed', sha=HEAD):
    return {'id': identifier, 'name': name, 'run_id': 7, 'run_attempt': attempt,
            'head_sha': sha, 'status': status, 'conclusion': conclusion}


@contextmanager
def github_pages(rows, *, raw=None, total=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get('Authorization')))
            query = parse_qs(urlsplit(self.path).query)
            page = int(query['page'][0])
            payload = raw if raw is not None else json.dumps({
                'total_count': len(rows) if total is None else total,
                'jobs': rows[(page - 1) * 100:page * 100],
            }).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def local_opener(request, *, timeout):
        # Keep the production request shape, but send the synthetic credential only to our owned server.
        assert request.full_url.startswith('https://api.github.com/repos/owner/repo/actions/runs/7/jobs?')
        target = f'http://127.0.0.1:{server.server_port}' + urlsplit(request.full_url).path
        target += '?' + urlsplit(request.full_url).query
        return urlopen(Request(target, headers=dict(request.header_items())), timeout=timeout)

    try:
        yield local_opener, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class RequiredJobsTests(unittest.TestCase):
    def test_cancelled_matrix_cell_cannot_hide_behind_successful_parent_or_gate(self):
        rows = [job(1, 'Python 3.11 Windows'), job(2, 'Python 3.11 macOS', 'cancelled'),
                job(3, SELF)]
        result = gate.audit_jobs(rows, HEAD, current_job=SELF, minimum_jobs=2)
        self.assertFalse(result['passed'])
        self.assertEqual(result['checked'], 2)
        self.assertEqual(result['failed'], [{'name': 'Python 3.11 macOS', 'status': 'completed',
                                            'conclusion': 'cancelled'}])

    def test_latest_rerun_replaces_only_the_same_logical_job(self):
        rows = [job(1, 'A', 'cancelled'), job(2, 'B'), job(3, SELF),
                job(4, 'A', attempt=2), job(5, SELF, None, attempt=2, status='in_progress')]
        self.assertTrue(gate.audit_jobs(rows, HEAD, current_job=SELF)['passed'])
        rows[3] = job(4, 'A', None, attempt=2, status='queued')
        self.assertFalse(gate.audit_jobs(rows, HEAD, current_job=SELF)['passed'])
        rows[3] = job(4, 'A', 'skipped', attempt=2)
        self.assertFalse(gate.audit_jobs(rows, HEAD, current_job=SELF)['passed'])

    def test_source_mismatch_duplicates_ambiguous_matrix_names_and_empty_proof_are_refused(self):
        invalid = [[job(1, 'A', sha=MERGE)], [job(1, 'A'), job(1, 'B')],
                   [job(1, 'A'), job(2, 'A')], [job(1, SELF)],
                   [job(True, 'A')], [job(1, 'A', attempt=True)]]
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                gate.audit_jobs(rows, HEAD, current_job=SELF)

    def test_actual_paginated_http_reaches_a_failure_beyond_the_first_hundred_jobs(self):
        rows = [job(number, f'cell-{number}') for number in range(1, 102)]
        rows[-1]['conclusion'] = 'failure'
        with github_pages(rows) as (opener, requests):
            fetched = gate.fetch_jobs('owner/repo', 7, 'SYNTHETIC_CANARY', opener=opener)
        result = gate.audit_jobs(fetched, HEAD, current_job=SELF)
        self.assertFalse(result['passed'])
        self.assertEqual([item['name'] for item in result['failed']], ['cell-101'])
        self.assertEqual(len(requests), 2)
        self.assertTrue(all('filter=all' in path and auth == 'Bearer SYNTHETIC_CANARY'
                            for path, auth in requests))

    def test_incomplete_and_foreign_run_http_responses_fail_closed(self):
        for rows, total in [([job(1, 'A')], 2), ([{**job(1, 'A'), 'run_id': 8}], 1)]:
            with self.subTest(total=total), github_pages(rows, total=total) as (opener, _):
                with self.assertRaises(ValueError):
                    gate.fetch_jobs('owner/repo', 7, 'SYNTHETIC_CANARY', opener=opener)

    def test_pull_request_head_and_tested_merge_are_both_bound_without_equating_them(self):
        rows = [job(1, 'Python'), job(2, SELF, None, status='in_progress')]
        environment = {'REQUIRED_NEEDS': json.dumps({'python-package': {'result': 'success'}}),
                       'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '7', 'GITHUB_TOKEN': 'SYNTHETIC_CANARY',
                       'GITHUB_SHA': MERGE, 'REQUIRED_HEAD_SHA': HEAD, 'REQUIRED_JOB_NAME': SELF}
        with github_pages(rows) as (opener, _), patch.dict(os.environ, environment, clear=True):
            actual_fetch = gate.fetch_jobs
            with patch.object(gate, 'fetch_jobs', side_effect=lambda repo, run, token: actual_fetch(repo, run, token, opener=opener)):
                output = io.StringIO()
                with redirect_stdout(output):
                    code = gate.main()
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual((result['head_sha'], result['tested_sha']), (HEAD, MERGE))
        self.assertNotIn('SYNTHETIC_CANARY', output.getvalue())

    def test_malformed_http_data_never_exposes_raw_response_or_token(self):
        environment = {'REQUIRED_NEEDS': json.dumps({'python-package': {'result': 'success'}}),
                       'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '7', 'GITHUB_TOKEN': 'SYNTHETIC_CANARY',
                       'GITHUB_SHA': HEAD, 'REQUIRED_HEAD_SHA': HEAD, 'REQUIRED_JOB_NAME': SELF}
        with github_pages([], raw=b'SYNTHETIC_CANARY not-json') as (opener, _), patch.dict(os.environ, environment, clear=True):
            actual_fetch = gate.fetch_jobs
            with patch.object(gate, 'fetch_jobs', side_effect=lambda repo, run, token: actual_fetch(repo, run, token, opener=opener)):
                output = io.StringIO()
                with redirect_stdout(output):
                    code = gate.main()
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output.getvalue())['passed'])
        self.assertNotIn('SYNTHETIC_CANARY', output.getvalue())


if __name__ == '__main__':
    unittest.main()
