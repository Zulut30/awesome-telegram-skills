"""Compare the newest aiogram release on PyPI with the version CI pins in requirements/sdk.txt.

A new aiogram moves the CI matrix, AIOGRAM_TESTED, the extra's bounds, the offline fixtures and the «Проверено»
lines of the skills together (docs/versioning.md), so Dependabot leaves aiogram alone and the weekly Telegram docs
watch calls this script: a newer release becomes one issue with that checklist. Read-only, one anonymous GET.

    python scripts/aiogram_release.py --markdown issue.md --github-output "$GITHUB_OUTPUT"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://pypi.org/pypi/aiogram/json'
STABLE = re.compile(r'(\d+)\.(\d+)\.(\d+)')


def fetch(url: str = SOURCE) -> dict[str, Any]:
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'awesome-telegram-skills-sdk-watch'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def pinned(requirements: Path = ROOT / 'requirements/sdk.txt') -> str:
    match = re.search(r'^aiogram==(\S+)$', requirements.read_text(encoding='utf-8'), re.M)
    if match is None:
        raise ValueError(f'{requirements}: no aiogram==X.Y.Z pin')
    return match.group(1)


def latest(releases: dict[str, list[dict]]) -> str:
    """Newest stable release that has files and none of them yanked; pre-releases and rc builds do not count."""
    versions = [version for version, files in releases.items()
                if STABLE.fullmatch(version) and files and not any(file.get('yanked') for file in files)]
    return max(versions, key=lambda version: tuple(map(int, version.split('.'))))


def compare(current: str, newest: str) -> dict[str, Any]:
    key = lambda version: tuple(map(int, version.split('.')))  # noqa: E731
    changed = key(newest) > key(current)
    major = changed and key(newest)[0] != key(current)[0]
    title = (f'aiogram {newest}: новая major-версия, решение о поддержке' if major
             else f'aiogram {newest}: перепроверить матрицу, фикстуры и скиллы')
    return {'current': current, 'latest': newest, 'changed': changed, 'major': major, 'title': title}


def markdown(result: dict[str, Any]) -> str:
    lines = [f'На PyPI вышел aiogram {result["latest"]}; CI закрепляет {result["current"]} в `requirements/sdk.txt`.',
             'Dependabot aiogram не обновляет: версия SDK меняется вместе со всем ниже (docs/versioning.md).', '']
    if result['major']:
        lines += ['Это новая major-версия: extra ограничен `<4`, поддержка — отдельное решение с проверкой API.', '']
    lines += [
        '- [ ] Матрица `python-unit` в `.github/workflows/repository-checks.yml` и `AIOGRAM_TESTED` в '
        '`packages/python/src/telegram_patterns/diagnostics.py`: добавить новую версию, убрать самую старую.',
        '- [ ] Нижняя граница extra `aiogram` в `packages/python/pyproject.toml` и `AIOGRAM_MINIMUM`.',
        '- [ ] `requirements/sdk.txt`, затем `python scripts/build_telegram_catalog.py` и '
        '`python scripts/build_recipe_gallery.py`: каталог и offline-фикстуры записываются на новой версии.',
        '- [ ] Скиллы со строкой «Проверено: …, aiogram X.Y.Z»: перепроверить по changelog aiogram и обновить '
        'версию и дату; `python -m unittest tests.test_skill_sources` называет каждый.',
        '- [ ] `docs/versioning.md`: таблица версий и матрица.',
        '',
        f'Changelog: https://docs.aiogram.dev/en/latest/changelog.html · PyPI: https://pypi.org/project/aiogram/{result["latest"]}/',
    ]
    return '\n'.join(lines) + '\n'


def main(get: Callable[[], dict[str, Any]] = fetch) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--markdown', type=Path, help='write the issue body here when a newer release exists')
    parser.add_argument('--github-output', type=Path, help='append changed=, title=, key= for GitHub Actions')
    args = parser.parse_args()
    result = compare(pinned(), latest(get()['releases']))
    if args.markdown and result['changed']:
        args.markdown.write_text(markdown(result), encoding='utf-8')
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as output:
            # key finds the issue of this release among open and closed ones; a title colon would read as a qualifier.
            output.write(f'changed={str(result["changed"]).lower()}\ntitle={result["title"]}\n'
                         f'key=aiogram {result["latest"]}\n')
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
