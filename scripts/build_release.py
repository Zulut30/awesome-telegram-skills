"""Build the release artifacts of one git ref reproducibly and print its release notes.

The ref is exported with `git archive` into a temporary tree, so uncommitted files of
the current checkout never leak into a release. SOURCE_DATE_EPOCH is the commit time:
two builds of the same ref with the same tool versions give identical bytes.

    python scripts/build_release.py --ref v0.24.0 --output dist/v0.24.0
    python scripts/build_release.py --ref v0.24.0 --notes
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path

import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_identity import (
    ReleaseIdentity,
    ReleaseIdentityError,
    parse_release_tag,
    read_release_identity,
)

ROOT = Path(__file__).resolve().parents[1]
NPM = 'npm.cmd' if os.name == 'nt' else 'npm'


def _git(*arguments: str) -> bytes:
    return subprocess.run(['git', *arguments], cwd=ROOT, check=True, capture_output=True).stdout


def ref_identity(ref: str, root: Path | None = None) -> ReleaseIdentity:
    """Read both manifests from one immutable commit, never from the working checkout."""
    repository = ROOT if root is None else root
    commit = subprocess.run(['git', 'rev-parse', f'{ref}^{{commit}}'], cwd=repository,
                            check=True, capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix='release-manifests-') as temporary:
        paths = []
        for source, basename in [('packages/python/pyproject.toml', 'pyproject.toml'),
                                 ('packages/typescript/package.json', 'package.json')]:
            content = subprocess.run(['git', 'show', f'{commit}:{source}'], cwd=repository,
                                     check=True, capture_output=True).stdout
            path = Path(temporary) / basename
            path.write_bytes(content)
            paths.append(path)
        return read_release_identity(*paths)


def _version(ref: str) -> str:
    return ref_identity(ref).identity


def validate_tag(tag: str, root: Path | None = None) -> ReleaseIdentity:
    """Canonical existing tag whose two committed manifests have exactly this identity."""
    release = parse_release_tag(tag)
    actual = ref_identity('refs/tags/' + tag, root)
    if actual.identity != release.identity:
        raise ReleaseIdentityError('Release tag differs from its committed package manifests')
    return release


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


REPOSITORY = 'https://github.com/Zulut30/awesome-telegram-skills'


def sbom(tree: Path, commit: str, epoch: int, sums: dict[str, str]) -> dict:
    """Deterministic CycloneDX 1.6 inventory of the two artifacts and their declared dependencies."""
    project = tomllib.loads((tree / 'packages/python/pyproject.toml').read_text(encoding='utf-8'))['project']
    package = json.loads((tree / 'packages/typescript/package.json').read_text(encoding='utf-8'))
    release = read_release_identity(tree / 'packages/python/pyproject.toml', tree / 'packages/typescript/package.json')
    def licenses(value: object) -> list[dict]:
        if not isinstance(value, str) or not value:
            return []
        if re.fullmatch(r'[A-Za-z0-9.-]+', value):
            return [{'license': {'id': value}}]
        return [{'expression': value}] if ' OR ' in value or ' AND ' in value else [{'license': {'name': value}}]
    python_ref = f"pkg:pypi/{project['name']}@{release.python_version}"
    npm_ref = 'pkg:npm/' + package['name'].replace('@', '%40', 1) + f'@{release.npm_version}'
    wheel = release.wheel_filename(project['name'])
    tarball = release.npm_tarball_filename(package['name'])
    python_dependencies: dict[str, dict] = {}
    declared_requirements = [(requirement, None) for requirement in project.get('dependencies', [])]
    for extra, extra_requirements in sorted(project.get('optional-dependencies', {}).items()):
        declared_requirements += [(requirement, extra) for requirement in extra_requirements]
    for requirement, extra in declared_requirements:
        match = re.match(r'[A-Za-z0-9_.-]+', requirement)
        if match is None:
            raise ValueError('Unsupported Python dependency declaration')
        name = re.sub(r'[-_.]+', '-', match.group(0)).lower()
        ref = f'pkg:pypi/{name}'
        dependency = python_dependencies.setdefault(ref, {'type': 'library', 'bom-ref': ref, 'name': name,
                                                          'purl': ref, 'scope': 'optional', 'properties': []})
        if extra is None:
            dependency['scope'] = 'required'
        value = requirement if extra is None else f'{requirement}; extra == "{extra}"'
        item = {'name': 'python:requirement', 'value': value}
        if item not in dependency['properties']:
            dependency['properties'].append(item)
    python_declared = list(python_dependencies.values())
    npm_dependencies: dict[str, dict] = {}
    for field, scope in [('dependencies', 'required'), ('optionalDependencies', 'optional')]:
        for name, value in sorted(package.get(field, {}).items()):
            ref = 'pkg:npm/' + name.replace('@', '%40', 1)
            dependency = npm_dependencies.setdefault(ref, {'type': 'library', 'bom-ref': ref, 'name': name,
                                                           'purl': ref, 'properties': []})
            dependency['scope'] = scope  # npm optionalDependencies overrides the same required declaration.
            dependency['properties'].append({'name': f'npm:{field}', 'value': value})
    peer_metadata = package.get('peerDependenciesMeta', {})
    for name, value in sorted(package.get('peerDependencies', {}).items()):
        ref = 'pkg:npm/' + name.replace('@', '%40', 1)
        details = peer_metadata.get(name, {})
        optional = isinstance(details, dict) and details.get('optional') is True
        scope = 'optional' if optional else 'required'
        dependency = npm_dependencies.setdefault(ref, {'type': 'library', 'bom-ref': ref, 'name': name,
                                                       'purl': ref, 'scope': scope, 'properties': []})
        if not optional:
            dependency['scope'] = 'required'
        dependency['properties'].extend([
            {'name': 'npm:peerDependencies', 'value': value},
            {'name': 'npm:peer-host-provided', 'value': 'true'},
            {'name': 'npm:peer-optional', 'value': str(optional).lower()},
        ])
    npm_declared = list(npm_dependencies.values())
    def component(ref: str, name: str, artifact: str, version: str, license_value: object) -> dict:
        return {'type': 'library', 'bom-ref': ref, 'name': name, 'version': version, 'purl': ref,
                'licenses': licenses(license_value),
                'hashes': [{'alg': 'SHA-256', 'content': sums[artifact]}],
                'externalReferences': [{'type': 'vcs', 'url': f'{REPOSITORY}/tree/{commit}'}]}
    from datetime import datetime, timezone
    return {'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1,
            'serialNumber': 'urn:uuid:' + str(uuid.uuid5(uuid.NAMESPACE_URL, f'{REPOSITORY}@{commit}')),
            'metadata': {'timestamp': datetime.fromtimestamp(epoch, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                         'tools': {'components': [{'type': 'application', 'name': 'scripts/build_release.py'}]},
                         'properties': [{'name': 'awesome-telegram:inventory-scope', 'value': 'artifacts-and-declared-direct-dependencies'},
                                        {'name': 'awesome-telegram:transitive-dependencies', 'value': 'not-resolved'},
                                        {'name': 'awesome-telegram:source-commit', 'value': commit}]},
            'components': [component(python_ref, project['name'], wheel, release.python_version, project.get('license')),
                           component(npm_ref, package['name'], tarball, release.npm_version, package.get('license')),
                           *python_declared, *npm_declared],
            'dependencies': [{'ref': python_ref, 'dependsOn': [c['bom-ref'] for c in python_declared]},
                             {'ref': npm_ref, 'dependsOn': [c['bom-ref'] for c in npm_declared]}]}


def build(ref: str, output: Path) -> dict[str, str]:
    commit = _git('rev-parse', f'{ref}^{{commit}}').decode().strip()
    version = _version(commit)
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f'{output} is not empty')
    output.mkdir(parents=True, exist_ok=True)
    epoch = int(_git('log', '-1', '--format=%ct', commit).decode().strip())
    environment = {**os.environ, 'SOURCE_DATE_EPOCH': str(epoch), 'PYTHONHASHSEED': '0'}
    with tempfile.TemporaryDirectory(prefix='release-tree-') as temporary:
        tree = Path(temporary) / 'tree'
        tree.mkdir()
        with tarfile.open(fileobj=io.BytesIO(_git('archive', '--format=tar', commit))) as archive:
            archive.extractall(tree, filter='data')
        subprocess.run([sys.executable, '-m', 'build', '--wheel', '--outdir', str(output), str(tree / 'packages/python')],
                       env=environment, check=True, stdout=subprocess.DEVNULL)
        subprocess.run([NPM, 'ci', '--no-audit', '--no-fund'], cwd=tree, env=environment, check=True, stdout=subprocess.DEVNULL)
        subprocess.run([NPM, 'pack', '-w', '@awesome-telegram/patterns', '--pack-destination', str(output.resolve())],
                       cwd=tree, env=environment, check=True, stdout=subprocess.DEVNULL)
        artifacts = sorted(p for p in output.iterdir() if p.suffix in {'.whl', '.tgz'})
        release = read_release_identity(tree / 'packages/python/pyproject.toml', tree / 'packages/typescript/package.json')
        project = tomllib.loads((tree / 'packages/python/pyproject.toml').read_text(encoding='utf-8'))['project']
        package = json.loads((tree / 'packages/typescript/package.json').read_text(encoding='utf-8'))
        expected = {release.wheel_filename(project['name']), release.npm_tarball_filename(package['name'])}
        if {p.name for p in artifacts} != expected:
            raise SystemExit(f'{ref}: unexpected artifacts {[p.name for p in artifacts]}')
        sums = {p.name: _sha256(p) for p in artifacts}
        bom = output / f'awesome-telegram-patterns-{version}.cdx.json'
        bom.write_text(json.dumps(sbom(tree, commit, epoch, sums), indent=2, sort_keys=True) + '\n', encoding='utf-8')
        sums[bom.name] = _sha256(bom)
    (output / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in sums.items()), encoding='utf-8')
    return {'ref': ref, 'commit': commit, 'version': version, **sums}


def notes(ref: str) -> str:
    """Release notes from the current CHANGELOG: the version section, or the bullets naming it."""
    version = _version(ref)
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    sections = re.split(r'^## ', changelog, flags=re.MULTILINE)[1:]
    for section in sections:
        heading, _, body = section.partition('\n')
        if re.match(rf'{re.escape(version)}(\s|$)', heading):
            text = body.strip()
            break
    else:
        # "- Пункт 016, 0.13.0: ..." names the version before the first colon.
        bullets = [line for section in sections for line in section.splitlines()
                   if line.startswith('- ') and ':' in line
                   and re.search(rf'(?<![\d.]){re.escape(version)}(?![\d])', line.partition(':')[0])]
        text = '\n'.join(bullets) or 'Подробности — в CHANGELOG.md.'
    return (f'awesome-telegram-patterns и @awesome-telegram/patterns {version}.\n\n{text}\n\n'
            'Проверка: `sha256sum -c SHA256SUMS`. Пакеты поставляются файлами релиза; в PyPI/npm они пока не опубликованы.\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ref', required=True, help='Tag or commit to build, for example v0.24.0')
    parser.add_argument('--output', type=Path, help='New or empty directory for the wheel, tarball and SHA256SUMS')
    parser.add_argument('--notes', action='store_true', help='Print release notes instead of building')
    args = parser.parse_args()
    if args.notes:
        print(notes(args.ref), end='')
        return 0
    if args.output is None:
        parser.error('--output is required unless --notes is given')
    if shutil.which(NPM) is None:
        raise SystemExit('npm is required to pack the TypeScript package')
    print(json.dumps(build(args.ref, args.output)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
