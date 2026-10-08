"""Quarterly review of external sources: what is stale, and what the live sources say today.

    python scripts/sources_review.py --output output/sources-review.json --markdown output/sources-review.md
    python scripts/sources_review.py --offline   # ages only, no network

Ages: the "Проверено: YYYY-MM-DD" line of every SKILL.md; older than a quarter (92 days) is stale. Live probes:
the newest Bot API version in the official changelog against the saved index, the newest aiogram on PyPI against
requirements/sdk.txt, and Crypto Pay API hosts, whose documentation page refuses automated requests (a request
without a token must return the documented {"ok": false, "error": {...}} envelope). The probes only report; dates
in skills and docs/sources.md change when a person has actually re-checked the content. The Sources review
workflow runs this every quarter and opens an issue with the checklist.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUARTER_DAYS = 92
CHECKED = re.compile(r'^Проверено: (\d{4}-\d{2}-\d{2}), (.+)$', re.M)
CRYPTO_PAY_HOSTS = ('pay.crypt.bot', 'testnet-pay.crypt.bot')
PROVIDERS = {'telegram-yookassa': 'ЮKassa', 'telegram-platega': 'Platega', 'telegram-cryptopay': 'Crypto Pay'}


def skill_ages(skills: Path, today: dt.date) -> list[dict]:
    rows = []
    for entry in sorted(skills.glob('*/SKILL.md')):
        match = CHECKED.search(entry.read_text(encoding='utf-8'))
        checked = dt.date.fromisoformat(match.group(1)) if match else None
        age = (today - checked).days if checked else None
        rows.append({'skill': entry.parent.name, 'checked': match.group(1) if match else None, 'age_days': age,
                     'stale': age is None or age > QUARTER_DAYS})
    return rows


def latest_bot_api(changelog_html: str) -> str | None:
    found = re.findall(r'<strong>Bot API (\d+\.\d+)</strong>', changelog_html)
    return max(found, key=lambda version: tuple(map(int, version.split('.')))) if found else None


def pinned_aiogram(requirements: str) -> str | None:
    match = re.search(r'^aiogram==([\d.]+)', requirements, re.M)
    return match.group(1) if match else None


def crypto_pay_envelope(body: bytes) -> bool:
    try:
        data = json.loads(body)
    except ValueError:
        return False
    return data.get('ok') is False and isinstance(data.get('error'), dict) and 'code' in data['error']


def get(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={'User-Agent': 'awesome-telegram-skills sources review'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed https URLs
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def probes() -> dict:
    result: dict = {}
    saved = json.loads((ROOT / '.agents/skills/telegram-bot-api/references/api-index.json').read_text(encoding='utf-8'))['bot_api_version']
    status, body = get('https://core.telegram.org/bots/api-changelog')
    latest = latest_bot_api(body.decode('utf-8', 'replace')) if status == 200 else None
    result['bot_api'] = {'saved_index': saved, 'latest_in_changelog': latest, 'current': latest == saved}
    status, body = get('https://pypi.org/pypi/aiogram/json')
    newest = json.loads(body)['info']['version'] if status == 200 else None
    pinned = pinned_aiogram((ROOT / 'requirements/sdk.txt').read_text(encoding='utf-8'))
    result['aiogram'] = {'pinned': pinned, 'latest_on_pypi': newest, 'current': newest == pinned}
    hosts = {}
    for host in CRYPTO_PAY_HOSTS:
        status, body = get(f'https://{host}/api/getMe')
        hosts[host] = {'status': status, 'documented_envelope': crypto_pay_envelope(body)}
    result['crypto_pay'] = {'hosts': hosts, 'reachable': all(item['documented_envelope'] for item in hosts.values()),
                            'note': 'without a token only the hosts and the error envelope are confirmed, not methods or webhook signatures'}
    return result


def markdown(report: dict) -> str:
    stale = [row for row in report['skills'] if row['stale']]
    lines = [f"Квартальная сверка источников, {report['date']}. Порядок: docs/sources.md, раздел о ежеквартальной сверке.", '',
             '## Что проверить', '',
             '- [ ] Bot API: изменения после версии сохраненного индекса; `python .agents/skills/telegram-bot-api/scripts/update_api_index.py`.',
             '- [ ] Mini Apps: страница core.telegram.org/bots/webapps и `catalog/telegram-capabilities.json`.',
             '- [ ] aiogram: новая версия, совместимость, `requirements/sdk.txt` и матрица CI.',
             '- [ ] Платежные провайдеры: ЮKassa, Platega, Crypto Pay — документация и примеры в скиллах.',
             '- [ ] Даты «Проверено» меняются только для того, что действительно сверено; запись в журнал docs/sources.md.', '']
    if 'probes' in report:
        probe = report['probes']
        hosts = ', '.join(f"{host} HTTP {item['status']}" for host, item in probe['crypto_pay']['hosts'].items())
        lines += ['## Живые пробы', '',
                  f"- Bot API: сохраненный индекс {probe['bot_api']['saved_index']}, в changelog {probe['bot_api']['latest_in_changelog']}"
                  f" — {'совпадает' if probe['bot_api']['current'] else 'нужна сверка'}.",
                  f"- aiogram: закреплен {probe['aiogram']['pinned']}, на PyPI {probe['aiogram']['latest_on_pypi']}"
                  f" — {'совпадает' if probe['aiogram']['current'] else 'нужна сверка'}.",
                  f"- Crypto Pay API: {hosts}"
                  f" — {'адреса и формат ошибки как в документации' if probe['crypto_pay']['reachable'] else 'ответ отличается от документации'}; "
                  'методы и подпись webhook без токена не проверяются.', '']
    lines += [f'## Скиллы старше {QUARTER_DAYS} дней ({len(stale)})', '']
    lines += [f"- [ ] `{row['skill']}` — проверено {row['checked'] or 'никогда'}" for row in stale] or ['Таких нет.']
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--offline', action='store_true', help='skip the live probes')
    parser.add_argument('--output', type=Path, help='JSON report')
    parser.add_argument('--markdown', type=Path, help='issue body with the checklist')
    args = parser.parse_args()
    today = dt.date.today()
    report: dict = {'date': today.isoformat(), 'quarter_days': QUARTER_DAYS, 'skills': skill_ages(ROOT / '.agents/skills', today)}
    if not args.offline:
        report['probes'] = probes()
    for path, text in ((args.output, json.dumps(report, ensure_ascii=False, indent=2) + '\n'), (args.markdown, markdown(report))):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
    print(json.dumps({'stale': sum(row['stale'] for row in report['skills']), **({'probes': report['probes']} if 'probes' in report else {})},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
