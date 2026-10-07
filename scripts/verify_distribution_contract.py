"""Read-only checks of our wheel/tarball bytes and declared package boundary."""
from __future__ import annotations

import argparse
import base64
import configparser
import csv
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import sys
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MAX_FILES = 4096
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


class DistributionViolation(ValueError):
    """Controlled local diagnostic; never dumps archived file contents."""


def _require(condition: bool, detail: str) -> None:
    if not condition: raise DistributionViolation(detail)


def _safe_name(name: str) -> None:
    _require(bool(name) and '\\' not in name and ':' not in name and '\x00' not in name,
             'Archive contains an unsafe member name')
    _require(all(part not in {'', '.', '..'} for part in name.rstrip('/').split('/')),
             'Archive contains an unsafe member path')


def _read_archive(path: Path, *, wheel: bool) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    seen: set[str] = set()
    total = 0
    if wheel:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            _require(len(members) <= MAX_FILES, 'Too many wheel members')
            for item in members:
                _safe_name(item.filename)
                _require(item.filename not in seen, 'Duplicate wheel member')
                seen.add(item.filename)
                kind = stat.S_IFMT(item.external_attr >> 16)
                if item.is_dir():
                    _require(kind in {0, stat.S_IFDIR}, 'Wheel contains a non-regular directory')
                    continue
                _require(kind in {0, stat.S_IFREG}, 'Wheel contains a non-regular member')
                total += item.file_size
                _require(0 <= item.file_size <= MAX_FILE_BYTES and total <= MAX_TOTAL_BYTES,
                         'Wheel exceeds verification size budget')
                result[item.filename] = archive.read(item)
    else:
        with tarfile.open(path, 'r:gz') as archive:
            count = 0
            for item in archive:
                count += 1
                _require(count <= MAX_FILES, 'Too many tarball members')
                _safe_name(item.name)
                _require(item.name not in seen, 'Duplicate tarball member')
                seen.add(item.name)
                if item.isdir(): continue
                _require(item.isfile(), 'Tarball contains a link or special member')
                total += item.size
                _require(0 <= item.size <= MAX_FILE_BYTES and total <= MAX_TOTAL_BYTES,
                         'Tarball exceeds verification size budget')
                stream = archive.extractfile(item)
                _require(stream is not None, 'Unreadable tarball member')
                with stream:
                    result[item.name] = stream.read(MAX_FILE_BYTES + 1)
                _require(len(result[item.name]) == item.size, 'Truncated tarball member')
    return result


def _verify_record(payload: dict[str, bytes], record_path: str) -> None:
    try: rows = list(csv.reader(io.StringIO(payload[record_path].decode('utf-8'))))
    except (KeyError, UnicodeError): raise DistributionViolation('Missing or invalid wheel RECORD') from None
    paths = set()
    for row in rows:
        _require(len(row) == 3, 'Invalid wheel RECORD row')
        name, digest, size = row
        _require(name in payload and name not in paths, 'Duplicate or unknown wheel RECORD row')
        paths.add(name)
        if name == record_path:
            _require(digest == size == '', 'RECORD cannot hash itself')
            continue
        expected = base64.urlsafe_b64encode(hashlib.sha256(payload[name]).digest()).rstrip(b'=').decode('ascii')
        _require(digest == 'sha256=' + expected and size == str(len(payload[name])), 'Wheel RECORD digest or size mismatch')
    _require(paths == set(payload), 'Wheel RECORD does not cover all files')


def verify_distributions(root: Path, wheel: Path, tarball: Path) -> dict:
    python = tomllib.loads((root / 'packages/python/pyproject.toml').read_text(encoding='utf-8'))['project']
    ts_path = root / 'packages/typescript'
    ts = json.loads((ts_path / 'package.json').read_text(encoding='utf-8'))
    version = python['version']
    _require(ts['version'] == version, 'Package versions differ')
    normalized = re.sub(r'[-_.]+', '_', python['name']).lower()
    prefix = f'{normalized}-{version}.dist-info/'
    py_files = _read_archive(wheel, wheel=True)
    expected: dict[str, bytes] = {}
    source_root = root / 'packages/python/src'
    for source in (source_root / 'telegram_patterns').rglob('*'):
        if not source.is_file() or '__pycache__' in source.parts or source.suffix == '.pyc': continue
        relative = source.relative_to(source_root).as_posix()
        _require(source.suffix == '.py' or relative == 'telegram_patterns/py.typed'
                 or relative.startswith('telegram_patterns/resources/') and source.suffix in {'.json', '.txt'},
                 'Unexpected file in Python source package')
        expected[relative] = source.read_bytes()
    _require('telegram_patterns/py.typed' in expected and 'telegram_patterns/__init__.py' in expected,
             'Missing Python typing marker or root module')
    for name, value in expected.items():
        _require(py_files.get(name) == value, 'Wheel source/resource bytes mismatch')
    metadata_names = {'METADATA', 'WHEEL', 'RECORD', 'entry_points.txt', 'top_level.txt'}
    allowed = set(expected) | {prefix + name for name in metadata_names} | {prefix + 'licenses/LICENSE'}
    _require(set(py_files) == allowed, 'Wheel includes missing or undeclared files')
    metadata = BytesParser().parsebytes(py_files[prefix + 'METADATA'])
    _require(metadata.get('Name') == python['name'] and metadata.get('Version') == version,
             'Wheel identity mismatch')
    _require(metadata.get('Requires-Python') == python['requires-python'], 'Wheel Python constraint mismatch')
    _require(metadata.get('License-Expression') == python['license'] == 'MIT'
             and py_files.get(prefix + 'licenses/LICENSE') == (root / 'packages/python/LICENSE').read_bytes(),
             'Wheel license metadata or file mismatch')
    # Our current core has no runtime dependencies; every requirement belongs
    # to the explicitly enabled SDK or IANA-data extras. No mandatory core deps.
    _require(not python.get('dependencies'), 'Update the contract for a new core dependency')
    requirements = metadata.get_all('Requires-Dist', [])
    expected_requirements = {r'aiogram<4,>=3\.31;\s*extra == "aiogram"', r'tzdata<2027,>=2026\.5;\s*extra == "calendar"'}
    _require(len(requirements) == 2 and all(sum(re.fullmatch(pattern, value) is not None for value in requirements) == 1 for pattern in expected_requirements),
             'Wheel extra dependency boundary changed')
    wheel_metadata = BytesParser().parsebytes(py_files[prefix + 'WHEEL'])
    _require(wheel_metadata.get('Root-Is-Purelib') == 'true' and wheel_metadata.get_all('Tag') == ['py3-none-any'],
             'Unexpected wheel platform contract')
    entry = configparser.ConfigParser()
    entry.read_string(py_files[prefix + 'entry_points.txt'].decode('utf-8'))
    _require(dict(entry['console_scripts']) == python['scripts'], 'Wheel console entry points mismatch')
    _verify_record(py_files, prefix + 'RECORD')
    recipes = json.loads(py_files['telegram_patterns/resources/recipes.json'])
    _require(recipes.get('library_version') == version, 'Bundled recipe version mismatch')

    ts_files = _read_archive(tarball, wheel=False)
    ts_expected = {'package/package.json': (ts_path / 'package.json').read_bytes(),
                   'package/README.md': (ts_path / 'README.md').read_bytes(),
                   'package/LICENSE': (ts_path / 'LICENSE').read_bytes(),
                   'package/src/styles.css': (ts_path / 'src/styles.css').read_bytes()}
    sources = list((ts_path / 'src').rglob('*.ts'))
    for source in sources:
        module = source.relative_to(ts_path / 'src').with_suffix('').as_posix()
        for extension in ('.js', '.d.ts'):
            built = ts_path / 'dist' / (module + extension)
            _require(built.is_file(), 'Missing built TypeScript module or declarations')
            ts_expected['package/dist/' + module + extension] = built.read_bytes()
    _require(set(ts_files) == set(ts_expected), 'Tarball includes missing or undeclared files')
    _require(all(ts_files[name] == value for name, value in ts_expected.items()), 'Tarball bytes differ from built package')
    manifest = json.loads(ts_files['package/package.json'])
    _require(manifest['type'] == 'module' and not manifest.get('dependencies'), 'TypeScript runtime dependency/ESM contract changed')
    _require(manifest['exports'] == {'.': {'types': './dist/index.d.ts', 'import': './dist/index.js'}, './styles.css': './src/styles.css'},
             'TypeScript public export map changed')
    _require('**/*.css' in manifest.get('sideEffects', []), 'CSS must remain a declared side effect')
    _require(manifest.get('license') == 'MIT', 'TypeScript package license changed')
    return {'passed': True, 'version': version, 'network': False, 'extracts_files': False,
            'wheel': {'files': len(py_files), 'source_files_exact': len(expected), 'record_verified': True},
            'tarball': {'files': len(ts_files), 'modules_with_types': len(sources), 'css_exact': True},
            'limits': 'Content/metadata check; imports, installed types, CLI and browser runtime are separate consumer stages.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--tarball', type=Path, required=True)
    args = parser.parse_args()
    try: report = verify_distributions(args.root, args.wheel, args.tarball)
    except DistributionViolation as error:
        print(json.dumps({'passed': False, 'detail': str(error), 'extracts_files': False}), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile, tarfile.TarError, configparser.Error):
        print(json.dumps({'passed': False, 'detail': 'Invalid archive or package contract; no files extracted or replaced.'}), file=sys.stderr)
        return 1
    print(json.dumps(report))
    return 0


if __name__ == '__main__': raise SystemExit(main())
