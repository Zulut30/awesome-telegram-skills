"""Report whether the package names of this repository are free or taken on PyPI and npm.

Read-only: the script sends anonymous GET requests and changes nothing. It cannot prove
ownership; for an existing name it lists the published maintainers so the owner can
compare them with their own accounts.

    python scripts/check_registry_names.py
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
Fetch = Callable[[str], tuple[int, Any]]


def fetch(url: str) -> tuple[int, Any]:
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'awesome-telegram-skills-name-check'})
    try:
        with urlopen(request, timeout=20) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, None


def names() -> tuple[str, str]:
    pyproject = (ROOT / 'packages/python/pyproject.toml').read_text(encoding='utf-8')
    python = re.search(r'^name\s*=\s*"([^"]+)"', pyproject, re.M).group(1)
    npm = json.loads((ROOT / 'packages/typescript/package.json').read_text(encoding='utf-8'))['name']
    return python, npm


def check(get: Fetch = fetch) -> dict[str, Any]:
    python, npm = names()
    status, body = get(f'https://pypi.org/pypi/{quote(python)}/json')
    pypi = {'name': python, 'taken': status == 200, 'status': status}
    if status == 200:
        pypi['maintainers'] = sorted({body['info'].get('author') or '', body['info'].get('maintainer') or ''} - {''})
    status, body = get('https://registry.npmjs.org/' + quote(npm, safe='@'))
    registry = {'name': npm, 'taken': status == 200, 'status': status}
    if status == 200:
        registry['maintainers'] = sorted(m.get('name', '') for m in body.get('maintainers', []))
    if npm.startswith('@'):
        scope = npm[1:].split('/', 1)[0]
        status, _ = get(f'https://registry.npmjs.org/-/org/{quote(scope)}/package')
        registry['scope'] = scope
        registry['scope_exists'] = status == 200
    return {'pypi': pypi, 'npm': registry, 'ownership_proven': False}


def main() -> int:
    print(json.dumps(check(), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
