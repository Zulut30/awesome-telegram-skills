"""Live acceptance of the example applications in the Telegram test environment, one dated report per release.

    python scripts/live_acceptance.py new --version X.Y.Z
    TELEGRAM_TEST_BOT_TOKEN=... python scripts/live_acceptance.py probe --version X.Y.Z --scenario shop
    python scripts/live_acceptance.py check docs/live-checks/X.Y.Z --version X.Y.Z
    python scripts/live_acceptance.py bundle --ref vX.Y.Z --output dist/vX.Y.Z   # Release workflow

The service bot, the group bot and the shop (payments in test Telegram Stars) run as bots created in the test
environment (https://core.telegram.org/bots/features#testing-your-bot). `probe` asks the test Bot API
(https://api.telegram.org/bot<token>/test/METHOD) what a bot can confirm by itself: identity, webhook state,
commands and, for the shop, a Stars invoice link. People press the buttons and record each case. The token is
read from the environment and never written; reports reject tokens, phone numbers and e-mail addresses.
Steps: docs/live-acceptance.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared helpers live next to this script
from device_report import ReportError, _text, read_directory, read_ref, ref_version, version_tuple  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS = 'docs/live-checks'
REQUIRED_FROM = (0, 25, 0)
API = 'https://api.telegram.org'
STATUSES = ('passed', 'failed', 'blocked', 'not-run')
SCENARIOS = {
    'service-bot': {
        'start': '/start показывает меню записи',
        'book-slot': 'Запись на свободное время подтверждается одним сообщением',
        'double-press': 'Двойное нажатие «Подтвердить» создает одну запись',
        'reminder': 'Напоминание приходит в назначенное время',
        'cancel': 'Отмена записи освобождает время',
    },
    'group-bot': {
        'topic': 'Бот отвечает в теме форума, где его вызвали',
        'missing-rights': 'Без прав администратора бот называет недостающее право',
        'join-request': 'Заявка на вступление одобряется после подтверждения модератора',
        'moderation': 'Команда модерации действует только для администратора',
    },
    'shop': {
        'open-mini-app': 'Mini App открывается кнопкой меню, сервер принимает initData',
        'order': 'Заказ создается один раз на операцию',
        'stars-invoice': 'Счет в Stars открывается в тестовом окружении',
        'payment': 'Оплата тестовыми Stars подтверждается, материал открывается',
        'refund': 'Возврат через refundStarPayment закрывает доступ',
    },
}


def template(version: str) -> dict:
    """A report where nothing is claimed yet: every case is not-run until someone checks it in Telegram."""
    version_tuple(version)
    scenarios = {name: {'bot': '', 'status': 'not-run', 'automated': None,
                        'cases': {case: {'status': 'not-run', 'note': 'not checked yet'} for case in cases}}
                 for name, cases in SCENARIOS.items()}
    return {'schema_version': 1, 'release': version, 'environment': 'test', 'checked_at': '', 'checked_by': '',
            'scenarios': scenarios, 'limitations': ''}


def derived(statuses: list[str]) -> str:
    if all(status == 'passed' for status in statuses):
        return 'passed'
    if 'failed' in statuses:
        return 'failed'
    if 'blocked' in statuses:
        return 'blocked'
    return 'not-run' if all(status == 'not-run' for status in statuses) else 'partial'


def validate(report: object, version: str, *, today: dt.date | None = None) -> dict:
    """Check a parsed report and return its summary. Raises ReportError."""
    today = today or dt.date.today()
    if not isinstance(report, dict) or report.get('schema_version') != 1:
        raise ReportError('report.json must be an object with schema_version 1')
    if report.get('release') != version:
        raise ReportError(f'release must be {version}')
    if report.get('environment') != 'test':
        raise ReportError('environment must be "test": live acceptance runs in the Telegram test environment')
    try:
        checked = dt.date.fromisoformat(report.get('checked_at', ''))
    except (TypeError, ValueError):
        raise ReportError('checked_at: date YYYY-MM-DD') from None
    if checked > today:
        raise ReportError('checked_at is in the future')
    _text(report.get('checked_by'), 'checked_by', limit=80)
    _text(report.get('limitations'), 'limitations', required=False, limit=600)
    scenarios = report.get('scenarios')
    if not isinstance(scenarios, dict) or set(scenarios) != set(SCENARIOS):
        raise ReportError(f'scenarios must be exactly {", ".join(SCENARIOS)}')
    summary = {}
    for name, cases in SCENARIOS.items():
        entry = scenarios[name]
        if not isinstance(entry, dict) or not isinstance(entry.get('cases'), dict) or set(entry['cases']) != set(cases):
            raise ReportError(f'{name}.cases must list {", ".join(cases)}')
        statuses = []
        for case in cases:
            result = entry['cases'][case]
            if not isinstance(result, dict) or result.get('status') not in STATUSES:
                raise ReportError(f'{name}.{case}.status must be one of {", ".join(STATUSES)}')
            _text(result.get('note', ''), f'{name}.{case}.note', required=result['status'] != 'passed')
            statuses.append(result['status'])
        status = derived(statuses)
        if entry.get('status') != status:
            raise ReportError(f"{name}.status must be '{status}' for its cases")
        bot = _text(entry.get('bot', ''), f'{name}.bot', required=status != 'not-run', limit=40)
        if bot and not (bot.startswith('@') and bot.lower().endswith('bot')):
            raise ReportError(f'{name}.bot: public username like @example_bot')
        automated = entry.get('automated')
        if automated is not None:
            if not isinstance(automated, dict) or automated.get('api') != 'test':
                raise ReportError(f'{name}.automated must come from the test Bot API')
            if automated.get('username', '').lower() != bot.removeprefix('@').lower():
                raise ReportError(f'{name}.automated.username does not match {name}.bot')
        summary[name] = {'status': status, 'bot': bot, 'automated': automated is not None,
                         'failed': [case for case, value in entry['cases'].items() if value['status'] != 'passed']}
    return {'release': version, 'checked_at': report['checked_at'], 'scenarios': summary}


def markdown(report: dict, summary: dict) -> str:
    lines = [f"### Живая приемка в тестовом окружении Telegram — {summary['release']}", '',
             f"Проверено {report['checked_at']}, проверял: {report['checked_by']}.", '',
             '| Сценарий | Итог | Бот | Автоматическая проба |', '| --- | --- | --- | --- |']
    for name, item in summary['scenarios'].items():
        lines.append(f"| {name} | {item['status']} | {item['bot'] or '—'} | {'да' if item['automated'] else 'нет'} |")
    notes = [f"- {name} / {case}: {report['scenarios'][name]['cases'][case]['status']} — {report['scenarios'][name]['cases'][case]['note']}"
             for name, item in summary['scenarios'].items() for case in item['failed']]
    if notes:
        lines += ['', 'Не прошло или не проверено:', *notes]
    if report.get('limitations'):
        lines += ['', f"Ограничения: {report['limitations']}"]
    return '\n'.join(lines) + '\n'


def call(token: str, method: str, payload: dict | None = None, *, api: str = API) -> object:
    """One test-environment Bot API call; errors never include the token."""
    request = urllib.request.Request(f'{api}/bot{token}/test/{method}', data=json.dumps(payload or {}).encode(),
                                     headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https API or a local fake
            body = json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = json.loads(error.read() or b'{}')
    except OSError as error:
        raise ReportError(f'{method}: test Bot API unreachable ({type(error).__name__})') from None
    if not body.get('ok'):
        raise ReportError(f"{method}: {body.get('error_code')} {body.get('description', 'error')}")
    return body['result']


def probe(token: str, scenario: str, *, api: str = API, now: dt.datetime | None = None) -> dict:
    """What the bot itself can confirm in the test environment."""
    me = call(token, 'getMe', api=api)
    if not isinstance(me, dict) or me.get('is_bot') is not True:
        raise ReportError('getMe did not return a bot')
    webhook = call(token, 'getWebhookInfo', api=api)
    commands = call(token, 'getMyCommands', api=api)
    result = {'api': 'test', 'checked_at': (now or dt.datetime.now(dt.timezone.utc)).isoformat(timespec='seconds'),
              'username': me.get('username', ''), 'webhook_set': bool(webhook.get('url')),
              'pending_updates': webhook.get('pending_update_count', 0), 'commands': len(commands)}
    if scenario == 'shop':
        link = call(token, 'createInvoiceLink', {'title': 'Live acceptance', 'description': 'Test Stars invoice',
                                                 'payload': 'live-acceptance', 'currency': 'XTR',
                                                 'prices': [{'label': 'Test', 'amount': 1}]}, api=api)
        result['stars_invoice_link'] = isinstance(link, str) and link.startswith('https://t.me/')
    return result


def bundle(ref: str, output: Path, root: Path = ROOT) -> dict:
    version = ref_version(ref, root)
    found = read_ref(ref, version, root, REPORTS)
    if found is None:
        if version_tuple(version) >= REQUIRED_FROM:
            raise ReportError(f'{ref}: {REPORTS}/{version}/report.json is required from '
                              f'{".".join(map(str, REQUIRED_FROM))}; see docs/live-acceptance.md')
        return {'release': version, 'skipped': True, 'reason': 'released before live reports were required'}
    report, files = found
    if set(files) != {'report.json'}:
        raise ReportError(f'Only report.json belongs in {REPORTS}/{version}')
    summary = validate(report, version)
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output / f'live-report-{version}.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(zipfile.ZipInfo('report.json', date_time=(1980, 1, 1, 0, 0, 0)), files['report.json'], zipfile.ZIP_DEFLATED)
    (output / f'live-report-{version}.md').write_text(markdown(report, summary), encoding='utf-8', newline='\n')
    return {**summary, 'skipped': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    new = commands.add_parser('new', help='create docs/live-checks/X.Y.Z/report.json with every case not-run')
    new.add_argument('--version', required=True)
    run = commands.add_parser('probe', help='record what the test Bot API confirms for one scenario')
    run.add_argument('--version', required=True)
    run.add_argument('--scenario', required=True, choices=sorted(SCENARIOS))
    run.add_argument('--api', default=API, help=argparse.SUPPRESS)
    check = commands.add_parser('check', help='validate a report directory')
    check.add_argument('folder', type=Path)
    check.add_argument('--version', required=True)
    pack = commands.add_parser('bundle', help='validate the report of a tag and write the release assets')
    pack.add_argument('--ref', required=True)
    pack.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'new':
            target = ROOT / REPORTS / args.version / 'report.json'
            if target.exists():
                raise ReportError(f'{target.relative_to(ROOT)} already exists')
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps(template(args.version), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            result: dict = {'created': str(target.relative_to(ROOT))}
        elif args.command == 'probe':
            token = os.environ.get('TELEGRAM_TEST_BOT_TOKEN', '')
            if not token:
                raise ReportError('Set TELEGRAM_TEST_BOT_TOKEN to the token of the test-environment bot')
            target = ROOT / REPORTS / args.version / 'report.json'
            report = json.loads(target.read_text(encoding='utf-8'))
            automated = probe(token, args.scenario, api=args.api)
            report['scenarios'][args.scenario]['automated'] = automated
            report['scenarios'][args.scenario]['bot'] = '@' + automated['username']
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            result = {'scenario': args.scenario, **automated}
        elif args.command == 'check':
            report, files = read_directory(args.folder)
            if set(files) != {'report.json'}:
                raise ReportError(f'Only report.json belongs in {args.folder}')
            result = validate(report, args.version)
        else:
            result = bundle(args.ref, args.output)
    except ReportError as error:
        sys.stderr.write(f'{error}\n')
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
