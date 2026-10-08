"""Check what a skill names against Telegram's current API and that its source links still open.

Offline: every lowerCamel or snake_case word and every backticked identifier in SKILL.md is
looked up in the Bot API index (.agents/skills/telegram-bot-api/references/api-index.json)
and the Mini App index (catalog/telegram-capabilities.json). Unknown names are listed for a
person to review; many are legitimately outside Telegram (Python, SDK or provider names).
With --online each page linked from SKILL.md is fetched once and core.telegram.org anchors are
checked; a 401/403 answer is reported as unverified (bot protection), not as a broken link.
With --table docs/sources.md the per-skill table in that page is rebuilt from the same sections.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r'\]\((https?://[^)\s]+)\)')
WORD = re.compile(r'`([^`\n]+)`|\b([a-z]+(?:[A-Z][a-z0-9]*)+|[a-z0-9]+(?:_[a-z0-9]+)+)\b')


def telegram_names() -> set[str]:
    index = json.loads((ROOT / '.agents/skills/telegram-bot-api/references/api-index.json').read_text(encoding='utf-8'))
    names = set()
    for kind in ('methods', 'types'):
        for item in index[kind]:
            names.add(item['name'])
            names.update(field if isinstance(field, str) else field['name']
                         for field in item.get('fields') or item.get('parameters') or [])
    mini = json.loads((ROOT / 'catalog/telegram-capabilities.json').read_text(encoding='utf-8'))['mini_app']
    for method in mini['methods']:
        names.update(method['path'].split('.'))
    names.update(item['name'] for item in mini['events'])
    names.update(item['name'] for item in mini['properties'])
    return names


def body(path: Path) -> str:
    return re.sub(r'\A---\n.*?\n---\n', '', path.read_text(encoding='utf-8').replace('\r\n', '\n'), flags=re.S)


def names_in(text: str) -> set[str]:
    text = LINK.sub('', text)
    found = set()
    for quoted, word in WORD.findall(text):
        if quoted:
            found.update(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', quoted))
        else:
            found.add(word)
    return found


def offline(skills_root: Path) -> dict:
    known = telegram_names()
    report = {}
    for skill in sorted(path.parent for path in skills_root.glob('*/SKILL.md')):
        text = body(skill / 'SKILL.md')
        found = names_in(text)
        report[skill.name] = {'telegram': sorted(found & known), 'unknown': sorted(found - known),
                              'links': sorted(set(LINK.findall(text)))}
    return report


CHECKED = re.compile(r'^Проверено: (\d{4}-\d{2}-\d{2}), (.+?)\.?$', re.M)
TABLE_START, TABLE_END = '<!-- skills-table:start -->', '<!-- skills-table:end -->'


def skills_table(skills_root: Path) -> str:
    """One row per skill from its sources section: when it was checked, against what, and the primary links."""
    rows = ['| Скилл | Проверено | Что сверено | Первичные источники |', '| --- | --- | --- | --- |']
    for skill in sorted(path.parent for path in skills_root.glob('*/SKILL.md')):
        section = body(skill / 'SKILL.md').split('\n## Источники\n', 1)[1]
        checked, scope = CHECKED.search(section).groups()
        links = ', '.join(f'[{text}]({url})' for text, url in re.findall(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', section))
        rows.append(f'| `{skill.name}` | {checked} | {scope} | {links} |')
    return '\n'.join(rows) + '\n'


def write_table(document: Path, table: str) -> bool:
    """Replace the marked block; returns whether the file changed."""
    text = document.read_text(encoding='utf-8')
    start, end = text.index(TABLE_START) + len(TABLE_START), text.index(TABLE_END)
    updated = text[:start] + '\n' + table + text[end:]
    if updated != text:
        document.write_text(updated, encoding='utf-8', newline='\n')
    return updated != text


def fetch(page: str) -> tuple[int | None, str]:
    for _ in range(3):  # one retry pair for a dropped connection; a 4xx/5xx answer is final
        try:
            with urlopen(Request(page, headers={'User-Agent': 'awesome-telegram-skills source check'}), timeout=60) as response:
                return response.status, response.read().decode('utf-8', 'replace')
        except HTTPError as error:
            return error.code, ''
        except (URLError, TimeoutError, OSError):
            continue
    return None, ''


def check_links(urls: list[str]) -> list[dict]:
    pages = sorted({urldefrag(url)[0] for url in urls})
    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = dict(zip(pages, pool.map(fetch, pages)))
    result = []
    for url in urls:
        page, anchor = urldefrag(url)
        status, content = fetched[page]
        anchored = not anchor or 'core.telegram.org' not in page or re.search(
            rf'(?:name|id)="{re.escape(anchor.lower())}"', content.lower()) is not None
        # 401/403 is bot protection, not a missing page: the link cannot be checked automatically.
        result.append({'url': url, 'status': status, 'ok': status == 200 and anchored, 'anchor_found': anchored,
                       'unverified': status in {401, 403}})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skills', type=Path, default=ROOT / '.agents/skills')
    parser.add_argument('--online', action='store_true', help='fetch every link once and check Telegram anchors')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--table', type=Path, metavar='DOC',
                        help='rewrite the per-skill table between the skills-table markers of DOC (docs/sources.md) and exit')
    args = parser.parse_args()
    if args.table:
        changed = write_table(args.table, skills_table(args.skills))
        print(json.dumps({'table': args.table.as_posix(), 'changed': changed}))
        return 0
    report = {'skills': offline(args.skills)}
    if args.online:
        urls = sorted({url for entry in report['skills'].values() for url in entry['links']})
        report['links'] = check_links(urls)
        report['broken'] = [item for item in report['links'] if not item['ok'] and not item['unverified']]
        report['unverified'] = [item['url'] for item in report['links'] if item['unverified']]
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    summary = {'skills': len(report['skills']),
               'telegram_names': sum(len(entry['telegram']) for entry in report['skills'].values())}
    if args.online:
        summary.update(links=len(report['links']), broken=len(report['broken']), unverified=report['unverified'])
    print(json.dumps(summary))
    return 1 if args.online and report['broken'] else 0


if __name__ == '__main__':
    sys.exit(main())
