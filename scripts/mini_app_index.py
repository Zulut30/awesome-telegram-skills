"""Index of the official Mini Apps page: WebApp functions, native modules, events and properties.

No dependencies and no Telegram calls. build_telegram_catalog.py imports it strictly (an unknown
module is an error there); the weekly docs watch runs it in watch mode, where a function of an
unknown module is still indexed, with min_version null when the page names no version gate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

MINI_URL = 'https://core.telegram.org/bots/webapps'
MODULE_VERSIONS = {'BackButton': '6.1', 'SettingsButton': '6.10', 'BottomButton': '6.1',
    'HapticFeedback': '6.1', 'CloudStorage': '6.9', 'BiometricManager': '7.2', 'LocationManager': '8.0',
    'Accelerometer': '8.0', 'DeviceOrientation': '8.0', 'Gyroscope': '8.0',
    'DeviceStorage': '9.0', 'SecureStorage': '9.0'}


class MiniParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.section, self.anchor, self.heading, self.cell, self.row = '', '', None, None, None
        self.tables = []
    def handle_starttag(self, tag, attrs):
        if tag in {'h3', 'h4'}:
            self.heading, self.anchor = [], ''
        elif tag == 'a' and self.heading is not None:
            self.anchor = dict(attrs).get('name', self.anchor)
        elif tag == 'tr': self.row = []
        elif tag in {'td', 'th'} and self.row is not None: self.cell = []
    def handle_data(self, text):
        if self.heading is not None: self.heading.append(text)
        if self.cell is not None: self.cell.append(text)
    def handle_endtag(self, tag):
        if tag in {'h3', 'h4'} and self.heading is not None:
            self.section = ''.join(self.heading).strip()
            self.heading = None
        elif tag in {'td', 'th'} and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row:
            self.tables.append((self.section, self.anchor, self.row))
            self.row = None


def mini_index(html: str, *, strict: bool = True, checked_date: str = '2026-10-04') -> dict:
    parser = MiniParser()
    parser.feed(html)
    methods, events, properties = {}, {}, []
    for section, anchor, row in parser.tables:
        if len(row) < 2: continue
        signature, kind = row[:2]
        name = signature.split('(')[0].removesuffix(' NEW').strip()
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9]*', name): continue
        if name in {'Field', 'Event', 'Method', 'eventType'}: continue
        url = MINI_URL + '#' + anchor
        description = row[2] if len(row) > 2 else ''
        if section == 'Events Available for Mini Apps':
            gates = re.findall(r'\b(\d+\.\d+)\+', kind)
            events[name] = {'name': name, 'min_version': gates[0] if gates else '6.0', 'url': url}
            continue
        known = section == 'Initializing Mini Apps' or section in MODULE_VERSIONS
        if not known and (strict or kind != 'Function'):
            if kind == 'Function' and strict: raise ValueError('Unmapped Mini App module: ' + section)
            continue
        if kind != 'Function':
            properties.append({'owner': 'WebApp' if section == 'Initializing Mini Apps' else section,
                               'name': name, 'type': kind, 'url': url})
            continue
        gates = re.findall(r'\b(\d+\.\d+)\+', description)
        # A function of a module this index does not know yet has no documented gate: null, not a guess.
        minimum = gates[0] if gates else (MODULE_VERSIONS.get(section, '6.0') if known else None)
        owners = [''] if section == 'Initializing Mini Apps' else (['MainButton', 'SecondaryButton'] if section == 'BottomButton' else [section])
        for owner in owners:
            path = f'{owner}.{name}' if owner else name
            if owner == 'SecondaryButton' and tuple(map(int, minimum.split('.'))) < (7, 10): minimum = '7.10'
            methods[path] = {'path': path, 'signature': signature.removesuffix(' NEW'), 'min_version': minimum, 'url': url}
    if not {'ready', 'showPopup', 'BackButton.show', 'LocationManager.getLocation'}.issubset(methods):
        raise ValueError('Mini App documentation layout changed; required methods missing')
    if not {'themeChanged', 'viewportChanged'}.issubset(events):
        raise ValueError('Mini App event table not found')
    return {'source': MINI_URL, 'source_sha256': hashlib.sha256(html.encode('utf-8')).hexdigest(),
            'checked_date': checked_date, 'scope': 'WebApp functions, named native modules, events and properties; not MTProto',
            'methods': sorted(methods.values(), key=lambda value: value['path']),
            'events': sorted(events.values(), key=lambda value: value['name']), 'properties': properties}



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html-file', type=Path, help='parse a saved copy of the official page instead of fetching it')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.html_file:
        html = args.html_file.read_text(encoding='utf-8')
    else:
        with urlopen(Request(MINI_URL, headers={'User-Agent': 'AwesomeTelegramSkills/1.0'}), timeout=30) as response:
            data = response.read(10_000_001)
        if len(data) > 10_000_000:
            raise ValueError('Documentation exceeds the fetch size limit')
        html = data.decode('utf-8')
    index = mini_index(html, strict=False, checked_date=datetime.now(timezone.utc).date().isoformat())
    index['retrieval'] = 'saved_html' if args.html_file else 'official_https'
    args.output.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"Mini Apps: {len(index['methods'])} methods, {len(index['events'])} events; wrote {args.output}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
