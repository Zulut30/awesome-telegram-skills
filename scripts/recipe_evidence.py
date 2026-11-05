"""Bind existing recipe results to exact distributions and source bytes, without running recipes."""
from __future__ import annotations

import argparse
import ast
import configparser
import hashlib
import json
import subprocess
import sys
import tarfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath

if __package__:
    from .verify_distribution_contract import verify_distributions
else:
    # This repository maintainer helper also runs under -I in a separate consumer.
    # Only sibling verification tooling is imported; no runtime source package is imported.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from verify_distribution_contract import verify_distributions


class EvidenceError(ValueError):
    """Controlled diagnostic without dumping caller file contents."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(value, dict), 'Expected a JSON object')
    return value


def source_file(root: Path, name: str) -> Path:
    parts = PurePosixPath(name)
    require(bool(name) and '\\' not in name and ':' not in name and '\n' not in name
            and not parts.is_absolute() and all(p not in {'', '.', '..'} for p in parts.parts),
            'Unsafe source-relative path')
    path = root.joinpath(*parts.parts)
    require(path.resolve().is_relative_to(root.resolve()) and path.is_file(), 'Missing or escaping source file')
    # Do not follow caller-planted directory links, including Windows junctions.
    for item in (path, *path.parents):
        if item == root.parent:
            break
        require(not item.is_symlink() and not getattr(item.lstat(), 'st_file_attributes', 0) & 0x400,
                'Linked source paths are not accepted')
    return path


RUNNERS = (
    'scripts/verify_pattern_packages.py', 'scripts/verify_recipe_execution.py',
    'scripts/build_recipe_gallery.py', 'scripts/build_telegram_catalog.py',
    'scripts/verify_gallery_export.py', 'scripts/verify_distribution_contract.py',
    'tests/native-recipes-consumer.mjs', 'tests/gallery-browser.mjs',
    'examples/mini-app/src/native-recipes.ts',
)


def producer_command(source: Path, execution: dict) -> list[str]:
    """Recover argv from the hashed producer, rather than pretending the report captured it."""
    tree = ast.parse(source_file(source, 'scripts/verify_recipe_execution.py').read_text(encoding='utf-8'))
    batches = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == 'run' and n.args and isinstance(n.args[0], ast.Constant)
               and n.args[0].value == 'all-python-fixtures']
    require(len(batches) == 1 and len(batches[0].args) >= 3, 'Unknown recipe producer command profile')
    arguments = ast.literal_eval(batches[0].args[2])
    # These reports come from the SDK environment. Do not guess a future extra/environment layout.
    require(isinstance(batches[0].args[1], ast.Attribute) and batches[0].args[1].attr == 'sdk_python',
            'Recipe producer interpreter profile changed')
    launches = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == 'subprocess'
                and n.func.attr == 'run' and n.args and isinstance(n.args[0], ast.List)]
    require(len(launches) == 1, 'Unknown recipe producer launch profile')
    elements = launches[0].args[0].elts
    require(len(elements) >= 2 and isinstance(elements[-1], ast.Starred), 'Unknown recipe argv profile')
    flags = [ast.literal_eval(n) for n in elements[1:-1]]
    require(all(isinstance(x, str) for x in [*flags, *arguments]), 'Invalid recipe producer argv')
    origins = execution.get('installed_origins', [])
    require(len(origins) == 2 and isinstance(origins[1].get('prefix'), str), 'Missing installed SDK interpreter origin')
    prefix = origins[1]['prefix']
    python = str(PureWindowsPath(prefix) / 'Scripts/python.exe') if '\\' in prefix else str(PurePosixPath(prefix) / 'bin/python')
    return [python, *flags, *arguments]


def verify_git_source(root: Path, repository: Path, ref: str, names: list[str]) -> dict:
    """Read Git objects only. The supplied source may be a plain archive without .git."""
    require(7 <= len(ref) <= 40 and all(c in '0123456789abcdef' for c in ref), 'Use an immutable source commit SHA')
    resolved = subprocess.run(['git', '-C', str(repository), 'rev-parse', '--verify', ref + '^{commit}'],
                              capture_output=True, check=False, timeout=30)
    require(resolved.returncode == 0, 'Source ref is unavailable in the supplied local repository')
    commit = resolved.stdout.decode('ascii').strip()
    require(len(commit) == 40 and all(c in '0123456789abcdef' for c in commit), 'Invalid source commit')
    requests = ''.join(commit + ':' + name + '\n' for name in names).encode('utf-8')
    objects = subprocess.run(['git', '-C', str(repository), 'cat-file', '--batch'], input=requests,
                             capture_output=True, check=False, timeout=60)
    require(objects.returncode == 0, 'Cannot read source objects')
    offset = 0
    for name in names:
        end = objects.stdout.find(b'\n', offset)
        header = objects.stdout[offset:end].split()
        require(end >= offset and len(header) == 3 and header[1] == b'blob', 'Source ref lacks a required file')
        size = int(header[2]); start = end + 1; content = objects.stdout[start:start + size]
        require(len(content) == size and content == source_file(root, name).read_bytes(),
                'Source bytes differ from the supplied Git ref: ' + name)
        offset = start + size + 1
    require(offset == len(objects.stdout), 'Invalid source object stream')
    return {'commit': commit, 'files_verified': len(names), 'mode': 'read-only-git-object-byte-comparison'}


def validate_inputs(report_path: Path, wheel: Path, tarball: Path, source: Path) -> tuple[dict, dict, dict]:
    report = read_json(report_path)
    require(report.get('passed') is True, 'Distribution report did not pass')
    stages = report.get('stages')
    require(isinstance(stages, list) and bool(stages)
            and all(isinstance(s, dict) and type(s.get('exit_code')) is int and s['exit_code'] == 0 for s in stages)
            and any(s.get('stage') == 'recipe-execution-consumer' for s in stages),
            'Missing or unsuccessful distribution stages')
    artifacts = report.get('artifacts', [])
    require(isinstance(artifacts, list) and len(artifacts) == 2, 'Expected exact wheel and tarball report bindings')
    for path in (wheel, tarball):
        matches = [a for a in artifacts if a.get('name') == path.name]
        require(len(matches) == 1 and matches[0].get('sha256') == digest(path.read_bytes())
                and matches[0].get('bytes') == path.stat().st_size, 'Stale or substituted distribution artifact')
    # Existing read-only archive verifier checks all Python source/resources, built JS/types/CSS,
    # identities and RECORD; nothing is extracted, imported from the archive, or executed.
    contract = verify_distributions(source, wheel, tarball)
    require(contract['version'] == report.get('version'), 'Source, report and distribution versions differ')
    gallery = read_json(source_file(source, 'catalog/recipe-gallery.json'))
    require(gallery.get('library_version') == report['version'], 'Recipe catalog version differs')
    with zipfile.ZipFile(wheel) as archive:
        bundled = archive.read('telegram_patterns/resources/recipes.json')
    require(bundled == source_file(source, 'catalog/recipe-gallery.json').read_bytes(),
            'Source recipe catalog differs from the exact wheel')
    return report, gallery, contract


def make_registry(report_path: Path, wheel: Path, tarball: Path, source: Path,
                  *, git_repository: Path | None = None, source_ref: str | None = None) -> dict:
    report, gallery, contract = validate_inputs(report_path, wheel, tarball, source)
    recipes = gallery.get('recipes', [])
    require(isinstance(recipes, list) and bool(recipes), 'Recipe scope is empty')
    ids = [r['id'] for r in recipes]
    require(len(ids) == len(set(ids)), 'Duplicate recipe IDs')
    execution = report.get('recipe_execution', {})
    runs = execution.get('recipes', [])
    require(execution.get('passed') is True and execution.get('version') == report['version']
            and isinstance(runs, list) and execution.get('python_recipes') == len(runs),
            'Invalid recipe execution report')
    require(len({r['recipe_id'] for r in runs}) == len(runs), 'Duplicate recipe result IDs')
    require({r['recipe_id'] for r in runs} <= set(ids), 'Execution report contains unknown recipe IDs')
    by_id = {r['recipe_id']: (i, r) for i, r in enumerate(runs)}
    batch_argv = producer_command(source, execution)
    names = {'catalog/recipe-gallery.json', *RUNNERS}
    # Bind all package source/build inputs, not only files mentioned by a recipe card.
    for relative in ('packages/python/src/telegram_patterns', 'packages/typescript/src', 'packages/typescript/dist'):
        names.update(p.relative_to(source).as_posix() for p in (source / relative).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    names.update({'packages/python/pyproject.toml', 'packages/python/LICENSE', 'packages/typescript/package.json',
                  'packages/typescript/README.md', 'packages/typescript/LICENSE'})
    records = []
    for recipe in recipes:
        code_hash = digest(recipe['code'].encode('utf-8'))
        require(code_hash == recipe['code_sha256'], 'Recipe code hash differs: ' + recipe['id'])
        require(recipe['maturity'] in {'reference', 'experimental', 'stable'}, 'Unknown recipe maturity')
        dependencies = sorted(set(recipe['source_files'] + recipe['check_files']))
        names.update(dependencies)
        limits = [recipe['scope'], 'Synthetic/offline evidence only; no live Telegram, provider, physical device or user study.',
                  'Evidence is retained at its observed level; maturity is copied without promotion.']
        evidence = {'status': 'not_run', 'report_pointer': None, 'checks': [], 'kind': recipe['execution']['kind'],
                    'producer_command': None, 'command_provenance': 'No per-recipe execution result exists.'}
        if recipe['id'] in by_id:
            index, run = by_id[recipe['id']]
            require(recipe['language'] == 'python' and run.get('library_version') == report['version']
                    and run.get('kind') == recipe['execution']['kind']
                    and run.get('passed') is True and run.get('telegram_requests') is False
                    and type(run.get('external_network_attempts')) is int and run['external_network_attempts'] == 0
                    and isinstance(run.get('checks'), list) and bool(run['checks'])
                    and all(isinstance(c, str) and bool(c) for c in run['checks']),
                    'Invalid per-recipe execution result: ' + recipe['id'])
            evidence.update(status='offline_pass', report_pointer=f'/recipe_execution/recipes/{index}',
                            checks=run['checks'], result=run,
                            producer_command=batch_argv,
                            reproduction_command=['python', '-m', 'telegram_patterns', 'run-recipe', recipe['id'], '--offline', '--json'],
                            command_provenance='Batch command reconstructed from bound verify_recipe_execution.py; original report did not capture argv. Interpreter origin is preserved in suite evidence.')
            if run['kind'] == 'sdk-request':
                limits.append('SDK request construction and method-name check only; not a sent request or verified Telegram permission.')
            else:
                limits.append('Known fixture/composition is executed; this is not arbitrary execution of recipe.code in a real application.')
        else:
            limits.append('Catalog listing/export/browser preview is not per-recipe runtime evidence. Native flow suite tests two authored examples, not every native.* fragment.')
        records.append({'recipe_id': recipe['id'], 'library_version': report['version'], 'maturity': recipe['maturity'],
                        'catalog_verification': recipe['verification'], 'code_sha256': code_hash,
                        'source_files': dependencies, 'evidence': evidence, 'limits': limits})
    # Built JS/.d.ts are verified against the tarball above, but normally ignored in Git.
    names = sorted(names)
    source_hashes = {name: digest(source_file(source, name).read_bytes()) for name in names}
    git_proof = None
    require((source_ref is None) == (git_repository is None), 'Supply source-ref and git-repository together')
    if source_ref is not None:
        tracked = [name for name in names if not name.startswith('packages/typescript/dist/')]
        git_proof = verify_git_source(source, git_repository, source_ref, tracked)
    stable = [r for r in records if r['maturity'] == 'stable']
    gaps = [r['recipe_id'] for r in stable if r['evidence']['status'] != 'offline_pass']
    stable_gate = {'status': 'no_stable_scope' if not stable else 'missing_evidence' if gaps else 'bound_offline_evidence',
                   'stable_recipes': len(stable), 'missing_recipe_ids': gaps,
                   'evidence_complete': bool(stable) and not gaps,
                   'quality_or_production_approved': False}
    return {'schema_version': 1, 'library_version': report['version'], 'binding_verified': True,
            'quality_or_production_approved': False,
            'bindings': {'distribution_report_sha256': digest(report_path.read_bytes()),
                         'artifacts': report['artifacts'], 'source_files_sha256': source_hashes, 'git_source': git_proof,
                         'source_fingerprint': digest(json.dumps(source_hashes, sort_keys=True).encode('utf-8'))},
            'summary': {'recipes': len(records), 'offline_pass': sum(r['evidence']['status'] == 'offline_pass' for r in records),
                        'not_run': sum(r['evidence']['status'] == 'not_run' for r in records),
                        'maturity': dict(Counter(r['maturity'] for r in records))},
            'stable_gate': stable_gate, 'recipes': records,
            'suite_evidence': {key: report.get(key) for key in ('recipe_gallery', 'gallery_export', 'gallery_browser', 'native_recipes')},
            'installed_origins': execution.get('installed_origins', []), 'distribution_contract': contract,
            'limits': ['A locally supplied report is trusted evidence, not a signed attestation; hashes detect substitution after binding.',
                       'Report dates and docs/sources.md dates are not execution evidence.',
                       'Gallery/native suites remain aggregate evidence; no invented per-recipe PASS.',
                       'Rechecking the registry reads and compares inputs; it does not rerun the distribution suite.',
                       'No maturity, exports, catalogs or caller files are modified.']}


def check_registry(registry: dict, report: Path, wheel: Path, tarball: Path, source: Path) -> dict:
    expected = registry.get('bindings', {})
    require(expected.get('distribution_report_sha256') == digest(report.read_bytes()), 'Distribution report changed since binding')
    require(isinstance(expected.get('source_files_sha256'), dict) and bool(expected['source_files_sha256']), 'Missing source binding')
    for name, checksum in expected['source_files_sha256'].items():
        require(digest(source_file(source, name).read_bytes()) == checksum, 'Stale source: ' + name)
    current = make_registry(report, wheel, tarball, source)
    current['bindings']['git_source'] = expected.get('git_source')
    require(current == registry, 'Registry content differs from its source/report-derived evidence')
    return current


def write_new(path: Path, value: dict) -> None:
    # Exclusive creation preserves any caller file; never truncate, replace, or create parents.
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create', 'check'])
    for name in ('report', 'wheel', 'tarball', 'source', 'registry'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-ref')
    parser.add_argument('--git-repository', type=Path)
    parser.add_argument('--require-stable', action='store_true', help='Fail also when stable scope is empty')
    args = parser.parse_args(argv)
    try:
        if args.action == 'create':
            require(not args.registry.exists() and not args.registry.is_symlink(), 'Registry output already exists')
            result = make_registry(args.report, args.wheel, args.tarball, args.source,
                                   git_repository=args.git_repository, source_ref=args.source_ref)
            if args.require_stable:
                require(result['stable_gate']['evidence_complete'], 'Stable scope is empty or lacks individual execution evidence')
            write_new(args.registry, result)
        else:
            require(args.source_ref is None and args.git_repository is None, 'Check uses the persisted source binding')
            result = check_registry(read_json(args.registry), args.report, args.wheel, args.tarball, args.source)
            if args.require_stable:
                require(result['stable_gate']['evidence_complete'], 'Stable scope is empty or lacks individual execution evidence')
        print(json.dumps({'binding_verified': True, 'action': args.action, 'registry': str(args.registry),
                          'summary': result['summary'], 'stable_gate': result['stable_gate'],
                          'quality_or_production_approved': False}))
        return 0
    except (EvidenceError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError,
            zipfile.BadZipFile, tarfile.TarError, configparser.Error) as error:
        # Do not echo arbitrary exception text from untrusted JSON/archive payloads.
        detail = str(error) if isinstance(error, EvidenceError) else 'Invalid or unavailable local evidence input; no caller file replaced.'
        print(json.dumps({'binding_verified': False, 'detail': detail, 'quality_or_production_approved': False}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
