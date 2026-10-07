"""Fail when Python library coverage drops below its gate.

    python -m coverage json --rcfile=packages/python/pyproject.toml -o coverage.json
    python scripts/check_coverage.py coverage.json

The gate: at least 90% of statements of the whole package, and every statement and branch of the modules whose
mistakes cost the most - signed launch data, exactly-once operations, slot booking, message splitting and the
aiogram media adapter. Raise the gate here; lowering it needs a CHANGELOG entry with the reason.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MINIMUM_STATEMENTS = 90.0
FULL_BRANCHES = (
    'telegram_patterns/initdata.py',
    'telegram_patterns/sqlite_once.py',
    'telegram_patterns/slots.py',
    'telegram_patterns/message_text.py',
    'telegram_patterns/_aiogram/media.py',
)


def check(report: dict, *, minimum: float = MINIMUM_STATEMENTS, full: tuple[str, ...] = FULL_BRANCHES) -> dict:
    files = {path.replace('\\', '/'): data['summary'] for path, data in report['files'].items()}
    totals = report['totals']
    modules = {}
    for module in full:
        matches = [summary for path, summary in files.items() if path.endswith('/' + module) or path == module]
        if len(matches) != 1:
            modules[module] = {'passed': False, 'reason': 'not measured'}
            continue
        summary = matches[0]
        missing = (summary['missing_lines'], summary.get('missing_branches', 0), summary.get('num_partial_branches', 0))
        modules[module] = {'passed': missing == (0, 0, 0), 'missing_lines': missing[0], 'missing_branches': missing[1],
                           'partial_branches': missing[2], 'branches': summary.get('num_branches', 0)}
    statements = round(totals['percent_statements_covered'], 2)
    return {'passed': statements >= minimum and all(item['passed'] for item in modules.values()),
            'statements_percent': statements, 'minimum_statements_percent': minimum,
            'branches_percent': round(totals.get('percent_branches_covered', 0.0), 2), 'full_branch_modules': modules}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('report', type=Path, help='coverage json output (branch measurement on)')
    parser.add_argument('--minimum', type=float, default=MINIMUM_STATEMENTS, help='percent of statements')
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding='utf-8'))
    if not report.get('meta', {}).get('branch_coverage'):
        parser.error('Measure with branch coverage: [tool.coverage.run] branch = true')
    result = check(report, minimum=args.minimum)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result['passed']:
        failed = [name for name, item in result['full_branch_modules'].items() if not item['passed']]
        sys.stderr.write(f"Coverage gate failed: statements {result['statements_percent']}% "
                         f"(minimum {args.minimum}%); incomplete modules: {', '.join(failed) or 'none'}\n")
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
