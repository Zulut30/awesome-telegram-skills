"""Run the Python library tests in parallel shards; --unit runs the fast in-process scope.

    python scripts/run_python_tests.py                  # every test, min(4, CPUs) shards
    python scripts/run_python_tests.py --unit           # unit scope: no child processes
    python scripts/run_python_tests.py --unit --budget 30 --jobs 2

Each shard is one interpreter that imports the SDKs once (aiogram alone takes seconds) and runs a group of test
modules with plain unittest. The library comes from that interpreter: an installed wheel, or PYTHONPATH pointing at
packages/python/src. Integration tests carry tests/_support.integration; in the unit scope they are skipped and any
child process a remaining test starts fails its shard, so the split cannot silently drift.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'packages/python/tests'
WORKER = r'''
import os, sys, traceback, unittest
spawned = []
if os.environ.get('TELEGRAM_PATTERNS_TESTS') == 'unit':
    import multiprocessing.process, subprocess
    def refuse(*args, **kwargs):
        frames = [f for f in traceback.extract_stack() if os.path.basename(f.filename).startswith('test_')]
        spawned.append(f'{os.path.basename(frames[-1].filename)}:{frames[-1].lineno}' if frames else 'unknown')
        raise AssertionError('A unit test started a child process; mark it with _support.integration')
    subprocess.Popen.__init__ = refuse
    multiprocessing.process.BaseProcess.start = refuse
program = unittest.main(module=None, argv=['unittest', *sys.argv[1:]], exit=False)
if spawned:
    print('Unit scope started child processes at: ' + ', '.join(sorted(set(spawned))), file=sys.stderr)
sys.exit(0 if program.result.wasSuccessful() and not spawned else 1)
'''
SUMMARY = re.compile(r'^Ran (\d+) tests? in [\d.]+s\s*\n\s*\n(OK|FAILED)(?: \(([^)]*)\))?', re.M)


def shards(modules: list[Path], jobs: int) -> list[list[str]]:
    """Greedy split by file size, integration-heavy modules counted heavier; deterministic for a tree."""
    weighted = sorted(
        ((path.stat().st_size + 200_000 * path.read_text(encoding='utf-8').count('@integration'), path.stem)
         for path in modules), reverse=True)
    groups: list[tuple[int, list[str]]] = [(0, []) for _ in range(max(1, min(jobs, len(weighted))))]
    for weight, name in weighted:
        index = min(range(len(groups)), key=lambda i: groups[i][0])
        groups[index] = (groups[index][0] + weight, groups[index][1] + [name])
    return [sorted(names) for _, names in groups if names]


def run(names: list[str], python: str, unit: bool, timeout: float, tests: Path, verbose: bool) -> dict:
    environment = dict(os.environ)
    environment.pop('TELEGRAM_PATTERNS_TESTS', None)
    if unit:
        environment['TELEGRAM_PATTERNS_TESTS'] = 'unit'
    started = time.perf_counter()
    try:
        command = [python, '-c', WORKER, *(['-v'] if verbose else []), *names]
        result = subprocess.run(command, cwd=tests, env=environment, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=timeout)
        output, code = result.stdout + result.stderr, result.returncode
    except subprocess.TimeoutExpired as error:
        partial = ''.join(value.decode('utf-8', 'replace') if isinstance(value, bytes) else value or ''
                          for value in (error.stdout, error.stderr))
        output, code = f'{partial}\nTIMEOUT after {timeout} seconds', 124
    match = SUMMARY.search(output)
    counts = dict(re.findall(r'(\w+)=(\d+)', match.group(3) or '')) if match else {}
    return {'modules': names, 'exit_code': code, 'seconds': round(time.perf_counter() - started, 1),
            'tests': int(match.group(1)) if match else 0, 'skipped': int(counts.get('skipped', 0)),
            'output': output}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--unit', action='store_true', help='skip integration tests and refuse child processes')
    parser.add_argument('--jobs', type=int, default=min(4, os.cpu_count() or 1), help='parallel shards')
    parser.add_argument('--budget', type=float, help='fail when the wall time exceeds this many seconds')
    parser.add_argument('--python', default=sys.executable, help='interpreter with the library and SDKs')
    parser.add_argument('--timeout', type=float, default=900, help='per-shard deadline in seconds')
    parser.add_argument('--json', action='store_true', help='print the report as JSON (last stdout line)')
    parser.add_argument('--verbose', action='store_true', help='unittest -v; print every shard log to stderr')
    parser.add_argument('--tests', type=Path, default=TESTS, help='test directory (default: the library tests)')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    tests = args.tests.resolve()
    modules = sorted(tests.glob('test_*.py'))
    if not modules:
        parser.error(f'No test_*.py modules in {tests}')
    groups = shards(modules, args.jobs)
    started = time.perf_counter()
    with ThreadPoolExecutor(len(groups)) as pool:
        results = list(pool.map(lambda names: run(names, args.python, args.unit, args.timeout, tests, args.verbose), groups))
    wall = round(time.perf_counter() - started, 1)
    failed = [item for item in results if item['exit_code'] != 0]
    over_budget = args.budget is not None and wall > args.budget
    report = {'passed': not failed and not over_budget, 'scope': 'unit' if args.unit else 'all', 'jobs': len(groups),
              'modules': len(modules), 'tests': sum(item['tests'] for item in results),
              'skipped': sum(item['skipped'] for item in results), 'seconds': wall, 'budget': args.budget,
              'shards': [{key: item[key] for key in ('modules', 'tests', 'skipped', 'seconds', 'exit_code')}
                         for item in results]}
    for item in results if args.verbose else failed:
        sys.stderr.write(f"--- shard {', '.join(item['modules'])} (exit {item['exit_code']}) ---\n{item['output']}\n")
    if over_budget:
        sys.stderr.write(f'Wall time {wall} s exceeds the budget of {args.budget} s\n')
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        for shard in report['shards']:
            print(f"{shard['seconds']:6.1f} s  {shard['tests']:4} tests  exit {shard['exit_code']}  {' '.join(shard['modules'])}")
        print(f"{'PASS' if report['passed'] else 'FAIL'} {report['scope']}: {report['tests']} tests "
              f"({report['skipped']} skipped) in {wall} s with {report['jobs']} shards")
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
