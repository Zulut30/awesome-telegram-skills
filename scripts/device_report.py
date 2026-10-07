"""Device check report of a release: Mini App demo in real Telegram on iOS, Android, Desktop and Web.

    python scripts/device_report.py new --version 0.25.0              # template in docs/device-checks/0.25.0
    python scripts/device_report.py check docs/device-checks/0.25.0 --version 0.25.0
    python scripts/device_report.py bundle --ref v0.25.0 --output dist/v0.25.0

`bundle` reads the report from the git ref (never the working tree), validates it and writes
device-report-<version>.zip (report.json and screenshots) and device-report-<version>.md for the release.
From REQUIRED_FROM on a release without a valid report fails; older tags are skipped.
The checklist and the meaning of every case are in docs/device-qa-checklist.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPORTS = 'docs/device-checks'
REQUIRED_FROM = (0, 25, 0)
PLATFORMS = ('ios', 'android', 'desktop', 'web')
CASES = ('cold-launch', 'theme', 'safe-areas', 'keyboard-form', 'validation-error', 'back-button',
         'minimize-resume', 'network-error', 'single-submit', 'window-size')
STATUSES = ('passed', 'failed', 'blocked', 'not-run')
IMAGE_SIGNATURES = (b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')
MAX_IMAGE_BYTES = 2 * 1024 * 1024
# A report is public: refuse what looks like a bot token, a phone number or an e-mail address.
PRIVATE = (re.compile(r'\b\d{6,12}:[A-Za-z0-9_-]{30,}\b'), re.compile(r'\+\d[\d ()-]{8,}\d'),
           re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'))


class ReportError(ValueError):
    """The report is missing, malformed or incomplete."""


def version_tuple(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', version)
    if match is None:
        raise ReportError(f'Not a release version: {version}')
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def template(version: str) -> dict:
    """A report where nothing is claimed yet: every case is not-run until someone checks it on a device."""
    version_tuple(version)
    platform = {'device': '', 'os': '', 'telegram': '', 'launch': 'menu button, Telegram test environment', 'status': 'not-run',
                'cases': {case: {'status': 'not-run', 'note': 'not checked yet'} for case in CASES}, 'screenshots': []}
    return {'schema_version': 1, 'release': version, 'app': 'examples/mini-app demo', 'checked_at': '', 'checked_by': '',
            'platforms': {name: json.loads(json.dumps(platform)) for name in PLATFORMS}, 'limitations': ''}


def _text(value: object, field: str, *, required: bool = True, limit: int = 300) -> str:
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ReportError(f'{field}: {"required " if required else ""}text up to {limit} characters')
    if any(pattern.search(value) for pattern in PRIVATE):
        raise ReportError(f'{field}: remove private data (token, phone number or e-mail)')
    return value


def validate(report: object, version: str, files: dict[str, bytes], *, today: dt.date | None = None) -> dict:
    """Check a parsed report and its screenshot bytes; return a summary. Raises ReportError."""
    if not isinstance(report, dict) or report.get('schema_version') != 1:
        raise ReportError('report.json must be an object with schema_version 1')
    if report.get('release') != version:
        raise ReportError(f'report.json is for {report.get("release")!r}, not {version}')
    _text(report.get('app'), 'app')
    _text(report.get('checked_by'), 'checked_by', limit=100)
    _text(report.get('limitations'), 'limitations', required=False, limit=2000)
    try:
        checked = dt.date.fromisoformat(report.get('checked_at', ''))
    except (TypeError, ValueError):
        raise ReportError('checked_at: date YYYY-MM-DD') from None
    if checked > (today or dt.date.today()):
        raise ReportError('checked_at is in the future')
    platforms = report.get('platforms')
    if not isinstance(platforms, dict) or set(platforms) != set(PLATFORMS):
        raise ReportError(f'platforms must be exactly {", ".join(PLATFORMS)}')
    summary, used = {}, set()
    for name in PLATFORMS:
        entry = platforms[name]
        if not isinstance(entry, dict):
            raise ReportError(f'{name}: object expected')
        for field in ('device', 'os', 'telegram', 'launch'):
            _text(entry.get(field), f'{name}.{field}', limit=200)
        cases = entry.get('cases')
        if not isinstance(cases, dict) or set(cases) != set(CASES):
            raise ReportError(f'{name}.cases must list exactly: {", ".join(CASES)}')
        for case in CASES:
            item = cases[case]
            if not isinstance(item, dict) or item.get('status') not in STATUSES:
                raise ReportError(f'{name}.{case}.status must be one of {", ".join(STATUSES)}')
            # Anything but passed must say why: the reason is the useful part of the report.
            _text(item.get('note', ''), f'{name}.{case}.note', required=item['status'] != 'passed', limit=500)
        statuses = [cases[case]['status'] for case in CASES]
        expected = 'passed' if all(s == 'passed' for s in statuses) else 'failed' if 'failed' in statuses \
            else 'blocked' if 'blocked' in statuses else 'not-run' if all(s == 'not-run' for s in statuses) else 'partial'
        if entry.get('status') != expected:
            raise ReportError(f'{name}.status must be {expected!r} for these cases')
        shots = entry.get('screenshots')
        if not isinstance(shots, list) or any(not isinstance(shot, str) for shot in shots):
            raise ReportError(f'{name}.screenshots must be a list of file names')
        if expected not in ('not-run', 'blocked') and not shots:
            raise ReportError(f'{name}: a checked platform needs at least one screenshot')
        for shot in shots:
            if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,80}\.(png|jpe?g)', shot) or shot in used:
                raise ReportError(f'{name}: screenshot name {shot!r} must be a unique lowercase .png/.jpg file name')
            used.add(shot)
            data = files.get(shot)
            if data is None:
                raise ReportError(f'{name}: screenshot {shot} is missing')
            if not data.startswith(IMAGE_SIGNATURES) or len(data) > MAX_IMAGE_BYTES:
                raise ReportError(f'{name}: {shot} must be a PNG or JPEG up to 2 MiB')
        summary[name] = {'status': expected, 'device': entry['device'], 'os': entry['os'], 'telegram': entry['telegram'],
                         'cases': dict(zip(CASES, statuses)), 'screenshots': len(shots)}
    extra = set(files) - used - {'report.json'}
    if extra:
        raise ReportError(f'Unreferenced files: {", ".join(sorted(extra))}')
    return {'release': version, 'checked_at': checked.isoformat(), 'platforms': summary}


def markdown(report: dict, summary: dict) -> str:
    """Release-notes section: one row per platform and every case that did not pass, with its note."""
    lines = [f"## Проверка на устройствах ({summary['checked_at']})", '',
             '| Платформа | Статус | Устройство и ОС | Telegram | Скриншоты |', '| --- | --- | --- | --- | --- |']
    for name in PLATFORMS:
        item = summary['platforms'][name]
        lines.append(f"| {name} | {item['status']} | {item['device']}, {item['os']} | {item['telegram']} | {item['screenshots']} |")
    notes = [f"- {name} / {case}: {status} — {report['platforms'][name]['cases'][case]['note']}"
             for name in PLATFORMS for case, status in summary['platforms'][name]['cases'].items() if status != 'passed']
    if notes:
        lines += ['', 'Не пройдено или не проверено:', '', *notes]
    if report.get('limitations', '').strip():
        lines += ['', 'Ограничения: ' + report['limitations'].strip()]
    return '\n'.join(lines) + '\n'


def read_directory(folder: Path) -> tuple[dict, dict[str, bytes]]:
    if not (folder / 'report.json').is_file():
        raise ReportError(f'{folder}/report.json is missing')
    files = {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}
    try:
        return json.loads(files['report.json']), files
    except ValueError:
        raise ReportError('report.json is not valid JSON') from None


def read_ref(ref: str, version: str, root: Path = ROOT) -> tuple[dict, dict[str, bytes]] | None:
    """Report files of the ref via git archive; None when the ref has no report directory."""
    prefix = f'{REPORTS}/{version}'
    listed = subprocess.run(['git', 'ls-tree', '--name-only', ref, prefix + '/'], cwd=root, capture_output=True, text=True)
    if listed.returncode or not listed.stdout.strip():
        return None
    archive = subprocess.run(['git', 'archive', '--format=tar', ref, prefix], cwd=root, check=True, capture_output=True).stdout
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                path = PurePosixPath(member.name)
                if path.parent != PurePosixPath(prefix):
                    raise ReportError(f'Nested files are not allowed: {member.name}')
                files[path.name] = tar.extractfile(member).read()  # type: ignore[union-attr]
    try:
        return json.loads(files['report.json']), files
    except KeyError:
        raise ReportError(f'{prefix}/report.json is missing') from None
    except ValueError:
        raise ReportError('report.json is not valid JSON') from None


def ref_version(ref: str, root: Path = ROOT) -> str:
    pyproject = subprocess.run(['git', 'show', f'{ref}:packages/python/pyproject.toml'], cwd=root, check=True,
                               capture_output=True, text=True).stdout
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    if match is None:
        raise ReportError(f'{ref}: no version in packages/python/pyproject.toml')
    return match.group(1)


def bundle(ref: str, output: Path, root: Path = ROOT) -> dict:
    version = ref_version(ref, root)
    found = read_ref(ref, version, root)
    if found is None:
        if version_tuple(version) >= REQUIRED_FROM:
            raise ReportError(f'{ref}: {REPORTS}/{version}/report.json is required from '
                              f'{".".join(map(str, REQUIRED_FROM))}; see docs/device-qa-checklist.md')
        return {'release': version, 'skipped': True, 'reason': 'released before device reports were required'}
    report, files = found
    summary = validate(report, version, files)
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output / f'device-report-{version}.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))  # reproducible archive bytes
            archive.writestr(info, files[name], zipfile.ZIP_DEFLATED)
    (output / f'device-report-{version}.md').write_text(markdown(report, summary), encoding='utf-8', newline='\n')
    return {**summary, 'skipped': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    new = commands.add_parser('new', help='write a not-run template for a release')
    new.add_argument('--version', required=True)
    check = commands.add_parser('check', help='validate a report directory')
    check.add_argument('folder', type=Path)
    check.add_argument('--version', required=True)
    pack = commands.add_parser('bundle', help='validate the report of a git ref and write release assets')
    pack.add_argument('--ref', required=True)
    pack.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'new':
            folder = ROOT / REPORTS / args.version
            folder.mkdir(parents=True, exist_ok=False)
            (folder / 'report.json').write_text(json.dumps(template(args.version), ensure_ascii=False, indent=2) + '\n',
                                                encoding='utf-8', newline='\n')
            result: dict = {'created': str(folder.relative_to(ROOT))}
        elif args.command == 'check':
            report, files = read_directory(args.folder)
            result = validate(report, args.version, files)
        else:
            result = bundle(args.ref, args.output)
    except (ReportError, FileExistsError) as error:
        print(json.dumps({'passed': False, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({'passed': True, **result}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
