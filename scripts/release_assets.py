"""Append release assets without replacing published bytes; verify local checksum boundaries."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

if __package__:
    from .release_identity import parse_release_tag
else:
    from release_identity import parse_release_tag


class ReleaseAssetError(ValueError):
    """Fixed diagnostics only: no inherited gh error bodies or credentials."""


def _name(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,239}', value):
        raise ReleaseAssetError('Invalid asset basename')
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_checksums(directory: Path, *, required: set[str]) -> dict[str, str]:
    """Check only regular files inside this directory; never follow manifest paths or links."""
    if directory.is_symlink() or not directory.is_dir():
        raise ReleaseAssetError('Use a regular artifact directory')
    manifest = directory / 'SHA256SUMS'
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 1024 * 1024:
        raise ReleaseAssetError('Missing or oversized checksum manifest')
    expected: dict[str, str] = {}
    for line in manifest.read_text(encoding='ascii').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]{0,239})', line)
        if match is None:
            raise ReleaseAssetError('Invalid checksum entry')
        digest, name = match.groups()
        _name(name)
        if name == 'SHA256SUMS' or name in expected:
            raise ReleaseAssetError('Duplicate or self-referential checksum entry')
        file = directory / name
        if file.is_symlink() or not file.is_file() or _sha256(file) != digest:
            raise ReleaseAssetError('An artifact is absent, linked or differs from its checksum')
        expected[name] = digest
    if not required or any(_name(name) not in expected for name in required):
        raise ReleaseAssetError('The checksum manifest does not cover the required artifacts')
    return expected


def append_plan(directory: Path, existing: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Every collision must already match; callers provide independently checked remote hashes."""
    if directory.is_symlink() or not directory.is_dir():
        raise ReleaseAssetError('Use a regular artifact directory')
    remote: dict[str, dict[str, Any]] = {}
    for asset in existing:
        name = _name(asset.get('name'))
        if name in remote:
            raise ReleaseAssetError('Ambiguous existing asset name')
        remote[name] = asset
    files = sorted(directory.iterdir(), key=lambda path: path.name)
    if not files:
        raise ReleaseAssetError('No local release assets')
    keep, upload = [], []
    for file in files:
        name = _name(file.name)
        if file.is_symlink() or not file.is_file():
            raise ReleaseAssetError('Release assets must be regular files')
        if name not in remote:
            upload.append(name)
            continue
        asset = remote[name]
        if (type(asset.get('size')) is not int or asset['size'] != file.stat().st_size
                or asset.get('digest') != 'sha256:' + _sha256(file)):
            raise ReleaseAssetError('Published bytes differ: keep the release intact and use a new version')
        keep.append(name)
    return {'kept': keep, 'upload': upload}


def _gh(command: list[str], *, maximum: int = 4 * 1024 * 1024) -> bytes:
    # A bounded temporary stream avoids storing a downloaded asset in memory or echoing gh stderr.
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run(['gh', *command], stdout=output, stderr=subprocess.PIPE, timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise ReleaseAssetError('GitHub operation did not establish an outcome') from None
        if result.returncode or output.tell() > maximum:
            raise ReleaseAssetError('GitHub operation failed or exceeded its bound')
        output.seek(0)
        return output.read(maximum + 1)


def append_assets(directory: Path, repository: str, tag: str) -> dict[str, list[str]]:
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ReleaseAssetError('Invalid repository')
    parse_release_tag(tag)
    release = json.loads(_gh(['api', f'repos/{repository}/releases/tags/{tag}']))
    if not isinstance(release, dict):
        raise ReleaseAssetError('Invalid GitHub release response')
    identifier = release.get('id')
    if type(identifier) is not int or identifier <= 0 or release.get('tag_name') != tag:
        raise ReleaseAssetError('GitHub release identity differs')
    pages = json.loads(_gh(['api', '--paginate', '--slurp',
                           f'repos/{repository}/releases/{identifier}/assets?per_page=100']))
    if not isinstance(pages, list) or not pages or any(not isinstance(page, list) for page in pages):
        raise ReleaseAssetError('Incomplete release asset response')
    existing = [asset for page in pages for asset in page]
    for asset in existing:
        if not isinstance(asset, dict):
            raise ReleaseAssetError('Invalid release asset response')
        name = _name(asset.get('name'))
        file = directory / name
        if not file.is_file() or asset.get('digest') is not None:
            continue
        # Old GitHub assets may have no digest. Read their actual bytes; never assume equality.
        asset_id, size = asset.get('id'), asset.get('size')
        if type(asset_id) is not int or asset_id <= 0 or type(size) is not int or size != file.stat().st_size:
            raise ReleaseAssetError('Existing asset identity or size differs')
        content = _gh(['api', '-H', 'Accept: application/octet-stream',
                       f'repos/{repository}/releases/assets/{asset_id}'], maximum=size)
        if len(content) != size:
            raise ReleaseAssetError('Existing asset content is incomplete')
        asset['digest'] = 'sha256:' + hashlib.sha256(content).hexdigest()
    plan = append_plan(directory, existing)
    if plan['upload']:
        # No --clobber: a remote collision appearing after the plan fails rather than replacing bytes.
        _gh(['release', 'upload', tag, *(str(directory / name) for name in plan['upload']), '--repo', repository])
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps({'passed': True, **append_assets(args.directory, args.repo, args.tag)}))
        return 0
    except (ReleaseAssetError, OSError, ValueError, UnicodeError):
        print(json.dumps({'passed': False, 'error': 'Release assets could not be appended safely; published files were not replaced'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
