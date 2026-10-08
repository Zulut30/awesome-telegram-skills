"""Check that CHANGELOG.md matches the version tags and the package version.

    python scripts/check_changelog.py            # structure, package version and every local vX.Y.Z tag
    python scripts/check_changelog.py --tag v0.25.0   # release workflow: the tag must have its own section

Rules: the first section is "## Не выпущено"; then one "## X.Y.Z[ — note]" section per released version,
newest first, without duplicates; every vX.Y.Z tag has a section; every section between the oldest and the newest
tag has a tag when tags are available (a CI checkout without tags checks the structure only); the version in
packages/python/pyproject.toml has a section or is still unreleased.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNRELEASED = 'Не выпущено'
HEADING = re.compile(r'^## (.+)$', re.M)
VERSION = re.compile(r'(\d+)\.(\d+)\.(\d+)(?=$| — )')


def key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split('.'))


def sections(text: str) -> tuple[list[str], list[str]]:
    """Versions of the released sections in order, and problems with the headings themselves."""
    headings = HEADING.findall(text)
    found, versions = [], []
    if not headings or headings[0] != UNRELEASED:
        found.append(f'the first section must be "## {UNRELEASED}"')
    for heading in headings[1:]:
        match = VERSION.match(heading)
        if not match:
            found.append(f'"## {heading}" is not a version section (use "## X.Y.Z" or "## X.Y.Z — note")')
            continue
        versions.append(match.group(0))
    for version in sorted({version for version in versions if versions.count(version) > 1}, key=key):
        found.append(f'{version}: more than one section')
    if versions != sorted(versions, key=key, reverse=True):
        found.append('version sections must go from newest to oldest')
    return versions, found


def problems(text: str, tags: list[str], package_version: str, require_tag: str | None = None) -> list[str]:
    versions, found = sections(text)
    tagged = sorted({tag[1:] for tag in tags if re.fullmatch(r'v\d+\.\d+\.\d+', tag)}, key=key)
    for version in tagged:
        if version not in versions:
            found.append(f'tag v{version} has no CHANGELOG section')
    if tagged:
        for version in versions:
            # Versions older than the first tag (0.1.0-0.4.0 here) predate tagging and need none.
            if version not in tagged and key(tagged[0]) <= key(version) <= key(tagged[-1]):
                found.append(f'{version}: section without a v{version} tag')
    if package_version not in versions and versions and key(package_version) <= key(versions[0]):
        found.append(f'package version {package_version} has no section and is not newer than {versions[0]}')
    if require_tag:
        version = require_tag.removeprefix('v')
        if version not in versions:
            found.append(f'{require_tag}: add a "## {version}" section before releasing')
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--tag', help='release tag that must have its own section')
    args = parser.parse_args()
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    tags = subprocess.run(['git', 'tag', '--list', 'v*'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    package = tomllib.loads((ROOT / 'packages/python/pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    found = problems(text, tags, package, args.tag)
    if found:
        sys.stderr.write('\n'.join(found) + '\n')
        return 1
    print(json.dumps({'passed': True, 'sections': len(sections(text)[0]), 'tags': len(tags), 'package_version': package}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
