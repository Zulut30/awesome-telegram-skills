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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_identity import (  # noqa: E402
    ReleaseIdentityError, parse_release_tag, parse_release_version, read_release_identity,
)

ROOT = Path(__file__).resolve().parents[1]
UNRELEASED = 'Не выпущено'
HEADING = re.compile(r'^## (.+)$', re.M)


def key(version: str) -> tuple[int, ...]:
    return parse_release_version(version).precedence_key


def sections(text: str) -> tuple[list[str], list[str]]:
    """Versions of the released sections in order, and problems with the headings themselves."""
    headings = HEADING.findall(text)
    found, versions = [], []
    if not headings or headings[0] != UNRELEASED:
        found.append(f'the first section must be "## {UNRELEASED}"')
    for heading in headings[1:]:
        candidate = heading.partition(' — ')[0]
        try:
            release = parse_release_version(candidate)
            if candidate != release.identity:
                raise ReleaseIdentityError('Use canonical release identity')
        except ReleaseIdentityError:
            found.append(f'"## {heading}" is not a version section (use "## X.Y.Z" or "## X.Y.Z — note")')
            continue
        versions.append(release.identity)
    for version in sorted({version for version in versions if versions.count(version) > 1}, key=key):
        found.append(f'{version}: more than one section')
    if versions != sorted(versions, key=key, reverse=True):
        found.append('version sections must go from newest to oldest')
    return versions, found


def problems(text: str, tags: list[str], package_version: str, require_tag: str | None = None) -> list[str]:
    versions, found = sections(text)
    canonical_tags = set()
    for tag in tags:
        try:
            canonical_tags.add(parse_release_tag(tag).identity)
        except ReleaseIdentityError:
            continue  # non-release tags do not participate in release history
    tagged = sorted(canonical_tags, key=key)
    package_version = parse_release_version(package_version).identity
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
        try:
            version = parse_release_tag(require_tag).identity
        except ReleaseIdentityError:
            found.append(f'{require_tag}: not a canonical release tag')
            return found
        if version not in versions:
            found.append(f'{require_tag}: add a "## {version}" section before releasing')
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--tag', help='release tag that must have its own section')
    args = parser.parse_args()
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    tags = subprocess.run(['git', 'tag', '--list', 'v*'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    try:
        package = read_release_identity(ROOT / 'packages/python/pyproject.toml',
                                        ROOT / 'packages/typescript/package.json').identity
    except ReleaseIdentityError as error:
        sys.stderr.write(str(error) + '\n')
        return 1
    found = problems(text, tags, package, args.tag)
    if found:
        sys.stderr.write('\n'.join(found) + '\n')
        return 1
    print(json.dumps({'passed': True, 'sections': len(sections(text)[0]), 'tags': len(tags), 'package_version': package}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
