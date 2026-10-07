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
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import uuid

ROOT = Path(__file__).resolve().parents[1]
NPM = 'npm.cmd' if os.name == 'nt' else 'npm'


def _git(*arguments: str) -> bytes:
    return subprocess.run(['git', *arguments], cwd=ROOT, check=True, capture_output=True).stdout


def _version(ref: str) -> str:
    pyproject = _git('show', f'{ref}:packages/python/pyproject.toml').decode('utf-8')
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    if match is None:
        raise SystemExit(f'{ref}: packages/python/pyproject.toml has no version')
    return match.group(1)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


REPOSITORY = 'https://github.com/Zulut30/awesome-telegram-skills'


def sbom(tree: Path, commit: str, epoch: int, sums: dict[str, str]) -> dict:
    """Deterministic CycloneDX 1.6 inventory of the two artifacts and their declared dependencies."""
    project = tomllib.loads((tree / 'packages/python/pyproject.toml').read_text(encoding='utf-8'))['project']
    package = json.loads((tree / 'packages/typescript/package.json').read_text(encoding='utf-8'))
    version = project['version']
    licenses = [{'license': {'id': project['license']}}] if isinstance(project.get('license'), str) else []
    python_ref = f"pkg:pypi/{project['name']}@{version}"
    npm_ref = 'pkg:npm/' + package['name'].replace('@', '%40', 1) + f'@{version}'
    wheel = f"{project['name'].replace('-', '_')}-{version}-py3-none-any.whl"
    tarball = f"{package['name'].lstrip('@').replace('/', '-')}-{version}.tgz"
    optional = []
    for extra, requirements in sorted(project.get('optional-dependencies', {}).items()):
        for requirement in requirements:
            name = re.match(r'[A-Za-z0-9_.-]+', requirement).group(0).lower()
            optional.append({'type': 'library', 'bom-ref': f'pkg:pypi/{name}', 'name': name, 'scope': 'optional',
                             'purl': f'pkg:pypi/{name}',
                             'properties': [{'name': 'python:requirement', 'value': f'{requirement}; extra == "{extra}"'}]})
    runtime = [{'type': 'library', 'bom-ref': f'pkg:npm/{name}', 'name': name, 'purl': 'pkg:npm/' + name.replace('@', '%40', 1),
                'properties': [{'name': 'npm:range', 'value': value}]} for name, value in sorted(package.get('dependencies', {}).items())]
    def component(ref: str, name: str, artifact: str) -> dict:
        return {'type': 'library', 'bom-ref': ref, 'name': name, 'version': version, 'purl': ref, 'licenses': licenses,
                'hashes': [{'alg': 'SHA-256', 'content': sums[artifact]}],
                'externalReferences': [{'type': 'vcs', 'url': f'{REPOSITORY}/tree/{commit}'}]}
    from datetime import datetime, timezone
    return {'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1,
            'serialNumber': 'urn:uuid:' + str(uuid.uuid5(uuid.NAMESPACE_URL, f'{REPOSITORY}@{commit}')),
            'metadata': {'timestamp': datetime.fromtimestamp(epoch, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                         'tools': {'components': [{'type': 'application', 'name': 'scripts/build_release.py'}]}},
            'components': [component(python_ref, project['name'], wheel), component(npm_ref, package['name'], tarball),
                           *optional, *runtime],
            'dependencies': [{'ref': python_ref, 'dependsOn': [c['bom-ref'] for c in optional]},
                             {'ref': npm_ref, 'dependsOn': [c['bom-ref'] for c in runtime]},
                             *({'ref': c['bom-ref'], 'dependsOn': []} for c in optional + runtime)]}


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
        expected = {f'awesome_telegram_patterns-{version}-py3-none-any.whl', f'awesome-telegram-patterns-{version}.tgz'}
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
    sections = re.split(r'^## ', changelog, flags=re.M)[1:]
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
