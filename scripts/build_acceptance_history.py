"""Keep the acceptance history small: one summary line per report, the full report behind a link.

    python scripts/build_acceptance_history.py            # write docs/acceptance-history.md from the JSON summary
    python scripts/build_acceptance_history.py --check    # fail when the table or the summary is out of date or invalid
    python scripts/build_acceptance_history.py --add output/pattern-library-X.Y.Z/distribution-report.json \\
        --name X.Y.Z-distribution.json --url https://github.com/OWNER/REPO/releases/download/vX.Y.Z/distribution-report.json

Full reports are not stored in the working tree. Reports up to 0.24.0 stay in git history and are linked by commit
permalinks; newer ones are release assets (the Full acceptance workflow uploads distribution-report.json to the
release of its tag). The summary keeps version, result, date, stage and test counts, size and SHA-256, so a
downloaded report can be matched to its line.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / 'docs/acceptance-history.json'
TABLE = ROOT / 'docs/acceptance-history.md'
URL = re.compile(r'https://github\.com/[\w.-]+/[\w.-]+/(blob/[0-9a-f]{40}/docs/v1-checks/|releases/download/v[0-9][\w.-]*/)[\w.-]+\.json')
FIELDS = ('name', 'version', 'passed', 'checked_date', 'stages', 'python_tests', 'typescript_tests', 'bytes', 'sha256', 'url')


def summarize(name: str, data: bytes, url: str) -> dict:
    report = json.loads(data)
    report = report if isinstance(report, dict) else {}
    python = report.get('python_tests')
    stages = report.get('distribution_stages', report.get('stages'))
    return {
        'name': name,
        'version': report.get('version') or report.get('library_version'),
        'passed': report.get('passed'),
        'checked_date': report.get('checked_date'),
        'stages': stages if isinstance(stages, int) else len(stages) if isinstance(stages, list) else None,
        'python_tests': python.get('passed') if isinstance(python, dict) else python if isinstance(python, int) else None,
        'typescript_tests': report.get('typescript_tests') if isinstance(report.get('typescript_tests'), int) else None,
        'bytes': len(data),
        'sha256': hashlib.sha256(data).hexdigest(),
        'url': url,
    }


def problems(summary: dict) -> list[str]:
    found = []
    names = [entry.get('name') for entry in summary['reports']]
    for name in sorted({name for name in names if names.count(name) > 1}):
        found.append(f'{name}: listed more than once')
    for entry in summary['reports']:
        if tuple(entry) != FIELDS:
            found.append(f"{entry.get('name')}: fields must be {', '.join(FIELDS)}")
        if not URL.fullmatch(entry.get('url', '')):
            found.append(f"{entry.get('name')}: url must be a commit permalink or a release asset")
        if not re.fullmatch(r'[0-9a-f]{64}', entry.get('sha256', '')):
            found.append(f"{entry.get('name')}: sha256 must be 64 hex characters")
    if (ROOT / 'docs/v1-checks').exists():
        found.append('docs/v1-checks must not return: keep full reports in release assets and add a summary line')
    return found


def render(summary: dict) -> str:
    def cell(value):
        return '—' if value is None else 'да' if value is True else 'нет' if value is False else str(value)

    lines = ['# История приемки', '',
             'Каждая строка — один отчет приемки: версия, результат, дата, число этапов и тестов, размер и SHA-256 '
             'полного отчета. Сами отчеты не лежат в рабочем дереве: отчеты до 0.24.0 открываются по постоянной ссылке '
             'на коммит, новые прикладываются к релизу workflow `Full acceptance`. Скачанный файл сверяется со строкой '
             'по SHA-256. Строки до 0.24.0 перенесены из `docs/v1-checks` без изменений содержимого отчетов.', '',
             '| Отчет | Версия | Принят | Дата | Этапы | Python | TypeScript | Размер | SHA-256 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for entry in summary['reports']:
        size = f"{entry['bytes'] / 1024:.1f} КиБ"
        lines.append(f"| [{entry['name']}]({entry['url']}) | {cell(entry['version'])} | {cell(entry['passed'])} | "
                     f"{cell(entry['checked_date'])} | {cell(entry['stages'])} | {cell(entry['python_tests'])} | "
                     f"{cell(entry['typescript_tests'])} | {size} | `{entry['sha256'][:12]}` |")
    lines += ['', 'Таблица собирается из `docs/acceptance-history.json` командой `python scripts/build_acceptance_history.py`; '
              'новый отчет добавляет `--add` (см. [выпуск версии](releasing.md)).', '']
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='fail instead of writing when something is out of date')
    parser.add_argument('--add', type=Path, help='full report to summarize; the file itself is not copied')
    parser.add_argument('--name', help='report name in the table (defaults to the file name)')
    parser.add_argument('--url', help='where the full report lives: a release asset URL')
    args = parser.parse_args()
    summary = json.loads(SUMMARY.read_text(encoding='utf-8'))
    if args.add:
        if args.check or not args.url:
            parser.error('--add needs --url and cannot be combined with --check')
        summary['reports'].append(summarize(args.name or args.add.name, args.add.read_bytes(), args.url))
    found = problems(summary)
    text = render(summary)
    if args.check and (not TABLE.exists() or TABLE.read_text(encoding='utf-8') != text):
        found.append('docs/acceptance-history.md is out of date: run python scripts/build_acceptance_history.py')
    if found:
        sys.stderr.write('\n'.join(found) + '\n')
        return 1
    if not args.check:
        if args.add:
            SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if not TABLE.exists() or TABLE.read_text(encoding='utf-8') != text:
            TABLE.write_text(text, encoding='utf-8')
    print(json.dumps({'passed': True, 'reports': len(summary['reports']), 'mode': 'check' if args.check else 'write'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
