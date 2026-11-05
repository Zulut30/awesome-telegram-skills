"""Заметки к релизу и проверка входных данных скрипта сборки релиза."""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_release', ROOT / 'scripts/build_release.py')
build_release = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = build_release
spec.loader.exec_module(build_release)


class BuildReleaseTests(unittest.TestCase):
    def test_notes_name_the_version_and_explain_verification(self):
        version = build_release._version('HEAD')
        self.assertEqual(build_release.parse_release_tag('v' + version).identity, version)
        text = build_release.notes('HEAD')
        self.assertTrue(text.startswith(f'awesome-telegram-patterns и @awesome-telegram/patterns {version}.'))
        self.assertIn('sha256sum -c SHA256SUMS', text)

    def test_sbom_lists_both_artifacts_with_hashes_license_and_extras(self):
        release = build_release.read_release_identity(ROOT / 'packages/python/pyproject.toml', ROOT / 'packages/typescript/package.json')
        sums = {release.wheel_filename('awesome-telegram-patterns'): 'a' * 64,
                release.npm_tarball_filename('@awesome-telegram/patterns'): 'b' * 64}
        bom = build_release.sbom(ROOT, '0' * 40, 0, sums)
        self.assertEqual((bom['bomFormat'], bom['specVersion'], bom['metadata']['timestamp']), ('CycloneDX', '1.6', '1970-01-01T00:00:00Z'))
        python, npm, *optional = bom['components']
        self.assertEqual((python['purl'], python['hashes'][0]['content'], python['licenses']),
                         ('pkg:pypi/awesome-telegram-patterns@' + release.python_version, 'a' * 64, [{'license': {'id': 'MIT'}}]))
        self.assertTrue(npm['purl'].startswith('pkg:npm/%40awesome-telegram/patterns@'))
        self.assertEqual({c['name'] for c in optional}, {'aiogram', 'cryptography', 'python-telegram-bot', 'tzdata', 'react', 'vue'})
        self.assertTrue(all(c['scope'] == 'optional' for c in optional))
        package = json.loads((ROOT / 'packages/typescript/package.json').read_text(encoding='utf-8'))
        by_name = {component['name']: component for component in optional}
        for name, constraint in package['peerDependencies'].items():
            peer = by_name[name]
            properties = {prop['name']: prop['value'] for prop in peer['properties']}
            self.assertEqual(properties['npm:peerDependencies'], constraint)
            self.assertEqual(properties['npm:peer-host-provided'], 'true')
            self.assertEqual(properties['npm:peer-optional'], 'true')
            self.assertNotIn('version', peer, 'host peer ranges are not bundled installed copies')
        self.assertEqual(bom, build_release.sbom(ROOT, '0' * 40, 0, sums), 'deterministic')

    def test_workflow_validates_tags_and_publishes_prereleases(self):
        workflow = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
        self.assertIn('from scripts.release_identity import parse_release_tag', workflow)
        self.assertIn('validate_tag(tag)', workflow)
        self.assertIn('--prerelease', workflow)
        self.assertIn('scripts/build_release.py --ref "$tag"', workflow)
        self.assertIn('actions/attest@', workflow)
        self.assertIn('attestations: write', workflow)
        for line in re.findall(r'uses: (\S+)', workflow):
            self.assertRegex(line, r'@[0-9a-f]{40}$', 'actions are pinned by commit SHA')

    def test_workflow_embedded_python_compiles_without_running_publish_actions(self):
        for name in ['release', 'publish']:
            lines = (ROOT / f'.github/workflows/{name}.yml').read_text(encoding='utf-8').splitlines()
            blocks = []
            for index, line in enumerate(lines):
                if "<<'PY'" not in line:
                    continue
                end = next(end for end in range(index + 1, len(lines)) if lines[end].strip() == 'PY')
                block = textwrap.dedent('\n'.join(lines[index + 1:end]))
                compile(block, f'{name}:{index + 1}', 'exec')
                blocks.append(block)
            self.assertGreaterEqual(len(blocks), 2)

    def test_workflow_shell_blocks_have_valid_bash_syntax_without_executing_them(self):
        git_bash = Path('C:/Program Files/Git/bin/bash.exe')
        bash = str(git_bash) if git_bash.is_file() else shutil.which('bash')
        if bash is None:
            self.skipTest('Bash is unavailable for static workflow syntax checking')
        with tempfile.TemporaryDirectory(prefix='release-shell-') as temporary:
            for name in ['release', 'publish']:
                lines = (ROOT / f'.github/workflows/{name}.yml').read_text(encoding='utf-8').splitlines()
                checked = 0
                for index, line in enumerate(lines):
                    if line.strip() != 'run: |':
                        continue
                    indent = len(line) - len(line.lstrip())
                    end = index + 1
                    while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) > indent):
                        end += 1
                    script = Path(temporary) / f'{name}-{index}.sh'
                    script.write_text(textwrap.dedent('\n'.join(lines[index + 1:end])) + '\n', encoding='utf-8')
                    checked += 1
                    result = subprocess.run([bash, '-n', script.as_posix()], capture_output=True, text=True, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assertGreaterEqual(checked, 2)


class RefIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='release-identity-ref-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for args in [('init', '-q'), ('config', 'user.name', 'Fixture'),
                     ('config', 'user.email', 'fixture@example.invalid'), ('config', 'commit.gpgsign', 'false'),
                     ('config', 'tag.gpgsign', 'false')]:
            self.git(*args)
        self.python = self.root / 'packages/python/pyproject.toml'
        self.npm = self.root / 'packages/typescript/package.json'
        self.python.parent.mkdir(parents=True)
        self.npm.parent.mkdir(parents=True)

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, python='1.0.0rc1', npm='1.0.0-rc.1'):
        self.python.write_text('[tool.decoy]\nversion="9.9.9"\n[project]\nname="awesome-telegram-patterns"\n'
                               f'version="{python}"\nlicense="MIT"\n', encoding='utf-8')
        self.npm.write_text(json.dumps({'name': '@awesome-telegram/patterns', 'version': npm}), encoding='utf-8')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'fixture', '--allow-empty')
        return self.git('rev-parse', 'HEAD')

    def test_both_manifests_are_from_the_ref_despite_dirty_checkout_or_newer_head(self):
        old = self.commit()
        self.commit('2.0.0', '2.0.0')
        self.python.write_text('invalid checkout TOML', encoding='utf-8')
        self.npm.write_text('invalid checkout JSON', encoding='utf-8')
        identity = build_release.ref_identity(old, self.root)
        self.assertEqual((identity.identity, identity.python_version), ('1.0.0-rc.1', '1.0.0rc1'))
        with patch.object(build_release, 'ROOT', self.root):
            self.assertEqual(build_release._version(old), '1.0.0-rc.1')

    def test_missing_or_conflicting_manifest_in_ref_cannot_fall_back_to_checkout(self):
        self.commit(npm='1.0.0-rc.2')
        with self.assertRaises(build_release.ReleaseIdentityError):
            build_release.ref_identity('HEAD', self.root)
        self.npm.unlink()
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'missing fixture')
        self.npm.write_text('{"version":"1.0.0-rc.1"}', encoding='utf-8')
        with self.assertRaises(subprocess.CalledProcessError):
            build_release.ref_identity('HEAD', self.root)

    def test_tag_validation_binds_canonical_tag_to_both_committed_manifests(self):
        self.commit()
        self.git('tag', 'v1.0.0-rc.1')
        self.git('tag', 'v1.0.0-rc.2')
        self.assertEqual(build_release.validate_tag('v1.0.0-rc.1', self.root).identity, '1.0.0-rc.1')
        for tag in ['v1.0.0rc1', 'v1.0.0-rc.2', 'v1.0.0-rc.01']:
            with self.subTest(tag=tag), self.assertRaises(build_release.ReleaseIdentityError):
                build_release.validate_tag(tag, self.root)

    def test_rc_sbom_uses_registry_specific_versions_purls_names_and_hashes(self):
        self.commit()
        sums = {'awesome_telegram_patterns-1.0.0rc1-py3-none-any.whl': 'a' * 64,
                'awesome-telegram-patterns-1.0.0-rc.1.tgz': 'b' * 64}
        bom = build_release.sbom(self.root, '0' * 40, 0, sums)
        python, npm = bom['components']
        self.assertEqual((python['version'], python['purl'], python['hashes'][0]['content']),
                         ('1.0.0rc1', 'pkg:pypi/awesome-telegram-patterns@1.0.0rc1', 'a' * 64))
        self.assertEqual((npm['version'], npm['purl'], npm['hashes'][0]['content']),
                         ('1.0.0-rc.1', 'pkg:npm/%40awesome-telegram/patterns@1.0.0-rc.1', 'b' * 64))
        self.assertEqual(bom, build_release.sbom(self.root, '0' * 40, 0, sums))

    def test_sbom_preserves_required_and_extra_constraints_without_inventing_resolved_versions(self):
        self.commit()
        self.python.write_text(self.python.read_text('utf-8') +
            'dependencies=["some_lib>=1"]\n[project.optional-dependencies]\n'
            'first=["Some.Lib<3"]\nsecond=["Some_Lib<4", "other>=2"]\n', encoding='utf-8')
        npm = json.loads(self.npm.read_text('utf-8'))
        npm.update(license='BSD-3-Clause', dependencies={'required': '^1'}, optionalDependencies={'optional': '^2'})
        self.npm.write_text(json.dumps(npm), encoding='utf-8')
        sums = {'awesome_telegram_patterns-1.0.0rc1-py3-none-any.whl': 'a' * 64,
                'awesome-telegram-patterns-1.0.0-rc.1.tgz': 'b' * 64}
        bom = build_release.sbom(self.root, '0' * 40, 0, sums)
        by_ref = {component['bom-ref']: component for component in bom['components']}
        self.assertEqual(len(by_ref), len(bom['components']), 'shared extras must not duplicate bom-ref')
        dependency = by_ref['pkg:pypi/some-lib']
        self.assertEqual(dependency['scope'], 'required')
        self.assertNotIn('version', dependency, 'a range is not a resolved installed version')
        self.assertEqual({item['value'] for item in dependency['properties']},
                         {'some_lib>=1', 'Some.Lib<3; extra == "first"', 'Some_Lib<4; extra == "second"'})
        self.assertEqual(by_ref['pkg:pypi/other']['scope'], 'optional')
        self.assertEqual(by_ref['pkg:npm/required']['scope'], 'required')
        self.assertEqual(by_ref['pkg:npm/optional']['scope'], 'optional')
        self.assertEqual(bom['components'][1]['licenses'], [{'license': {'id': 'BSD-3-Clause'}}])
        self.assertEqual(len(bom['dependencies']), 2, 'unresolved transitive nodes must not claim empty dependencies')

    def test_sbom_peer_overlap_retains_effective_runtime_scope_and_separate_package_namespaces(self):
        self.commit()
        self.python.write_text(self.python.read_text('utf-8') + 'dependencies=["react>=1"]\n', encoding='utf-8')
        npm = json.loads(self.npm.read_text('utf-8'))
        npm.update(dependencies={'overlap': '^1', 'react': '^18'}, optionalDependencies={'overlap': '^2'},
                   peerDependencies={'overlap': '>=1', 'react': '>=18', 'vue': '^3', 'needed': '^2'},
                   peerDependenciesMeta={'overlap': {'optional': True}, 'react': {'optional': True},
                                         'vue': {'optional': True}})
        self.npm.write_text(json.dumps(npm), encoding='utf-8')
        sums = {'awesome_telegram_patterns-1.0.0rc1-py3-none-any.whl': 'a' * 64,
                'awesome-telegram-patterns-1.0.0-rc.1.tgz': 'b' * 64}
        bom = build_release.sbom(self.root, '0' * 40, 0, sums)
        by_ref = {component['bom-ref']: component for component in bom['components']}
        self.assertEqual(len(by_ref), len(bom['components']))
        self.assertIn('pkg:pypi/react', by_ref)
        self.assertIn('pkg:npm/react', by_ref)
        self.assertEqual(by_ref['pkg:npm/overlap']['scope'], 'optional')
        self.assertEqual({prop['name'] for prop in by_ref['pkg:npm/overlap']['properties']},
                         {'npm:dependencies', 'npm:optionalDependencies', 'npm:peerDependencies',
                          'npm:peer-host-provided', 'npm:peer-optional'})
        self.assertEqual(by_ref['pkg:npm/react']['scope'], 'required', 'optional peer cannot weaken required runtime')
        self.assertEqual(by_ref['pkg:npm/vue']['scope'], 'optional')
        self.assertEqual(by_ref['pkg:npm/needed']['scope'], 'required')
        npm_edges = bom['dependencies'][1]['dependsOn']
        self.assertEqual(len(npm_edges), 4)
        self.assertEqual(set(npm_edges), {'pkg:npm/overlap', 'pkg:npm/react', 'pkg:npm/vue', 'pkg:npm/needed'})

    def test_rc_notes_use_canonical_identity_in_changelog_and_heading(self):
        self.commit()
        (self.root / 'CHANGELOG.md').write_text('## Не выпущено\n\n## 1.0.0-rc.1\n\n- candidate fixture\n', encoding='utf-8')
        with patch.object(build_release, 'ROOT', self.root):
            text = build_release.notes('HEAD')
        self.assertIn('patterns 1.0.0-rc.1.', text)
        self.assertIn('candidate fixture', text)


class PublishWorkflowTests(unittest.TestCase):
    def test_registry_publishing_is_opt_in_oidc_and_verifies_checksums(self):
        workflow = (ROOT / '.github/workflows/publish.yml').read_text(encoding='utf-8')
        self.assertIn("if: vars.PUBLISH_TO_REGISTRIES == 'true'", workflow)
        self.assertIn('sha256sum -c SHA256SUMS', workflow)
        self.assertEqual(workflow.count('id-token: write'), 2)
        self.assertIn('validate_tag(os.environ[\'TAG\'])', workflow)
        self.assertIn("('rc' if release.is_prerelease else 'latest')", workflow)
        self.assertIn('release.wheel_filename', workflow)
        self.assertIn('release.npm_tarball_filename', workflow)
        self.assertIn('--tag "$DIST_TAG"', workflow)
        self.assertIn('scripts/device_report.py bundle --ref "$TAG"', workflow)
        self.assertIn('scripts/live_acceptance.py bundle --ref "$TAG"', workflow)
        self.assertNotIn('secrets.', workflow, 'no long-lived registry tokens')
        self.assertIn('verify_checksums(Path(\'dist\'), required=expected | {sbom})', workflow)
        for flag in ('--signer-workflow', '--source-ref', '--source-digest', '--signer-digest',
                     '--deny-self-hosted-runners', '--predicate-type'):
            self.assertIn(flag, workflow)
        self.assertIn('refs/tags/$TAG', workflow)
        self.assertIn('https://slsa.dev/provenance/v1', workflow)
        for line in re.findall(r'uses: (\S+)', workflow):
            self.assertRegex(line, r'@[0-9a-f]{40}$')

    def test_published_assets_and_run_scoped_reports_are_never_overwritten(self):
        release = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
        acceptance = (ROOT / '.github/workflows/full-acceptance.yml').read_text(encoding='utf-8')
        for workflow in (release, acceptance):
            self.assertNotIn('--clobber', workflow)
            self.assertIn('python scripts/release_assets.py', workflow)
        self.assertIn('distribution-report-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}.json', acceptance)
        self.assertIn('/releases/download/$TAG/$asset', acceptance)


class ReleaseTagManifestTests(unittest.TestCase):
    def test_manifest_matches_history_where_available(self):
        entries = json.loads((ROOT / '.github/release-tags.json').read_text(encoding='utf-8'))['tags']
        versions = [tuple(map(int, e['version'].split('.'))) for e in entries]
        self.assertEqual(versions, sorted(set(versions)), 'unique and ascending')
        checked = 0
        for entry in entries:
            self.assertEqual(entry['tag'], 'v' + entry['version'])
            self.assertRegex(entry['commit'], r'^[0-9a-f]{40}$')
            shown = subprocess.run(['git', 'show', f"{entry['commit']}:packages/python/pyproject.toml"], cwd=ROOT,
                                   capture_output=True, text=True, check=False)
            if shown.returncode != 0:
                continue  # shallow CI checkout: history is not available
            self.assertIn(f'version = "{entry["version"]}"', shown.stdout, entry['tag'])
            self.assertEqual(build_release.ref_identity(entry['commit']).identity, entry['version'], entry['tag'])
            checked += 1
        self.assertGreaterEqual(len(entries), 23)


if __name__ == '__main__':
    unittest.main()
