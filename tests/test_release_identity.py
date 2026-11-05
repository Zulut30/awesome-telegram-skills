"""Release identity: strict forms, safe artifact basenames and read-only manifests."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_identity', ROOT / 'scripts/release_identity.py')
identity = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = identity
spec.loader.exec_module(identity)


class ReleaseIdentityTests(unittest.TestCase):
    def test_numeric_release_preserves_all_registry_forms(self):
        release = identity.parse_release_version('0.24.0')
        self.assertEqual(release.release, (0, 24, 0))
        self.assertEqual((release.identity, release.python_version, release.npm_version, release.tag),
                         ('0.24.0', '0.24.0', '0.24.0', 'v0.24.0'))
        self.assertFalse(release.is_prerelease)

    def test_rc_forms_share_identity_without_losing_prerelease(self):
        python = identity.parse_release_version('1.2.3rc12')
        npm = identity.parse_release_version('1.2.3-rc.12')
        self.assertEqual(python, npm)
        self.assertEqual((python.identity, python.python_version, python.npm_version, python.tag),
                         ('1.2.3-rc.12', '1.2.3rc12', '1.2.3-rc.12', 'v1.2.3-rc.12'))
        self.assertTrue(python.is_prerelease)
        self.assertNotEqual(python, identity.parse_release_version('1.2.3'))

    def test_rc_zero_is_preserved_and_not_final(self):
        release = identity.parse_release_version('1.0.0rc0')
        self.assertEqual(release, identity.parse_release_version('1.0.0-rc.0'))
        self.assertEqual((release.rc, release.python_version, release.tag), (0, '1.0.0rc0', 'v1.0.0-rc.0'))
        self.assertTrue(release.is_prerelease)

    def test_canonical_roundtrips_at_supported_integer_boundary(self):
        release = identity.ReleaseIdentity(identity.MAX_COMPONENT, identity.MAX_COMPONENT,
                                           identity.MAX_COMPONENT, identity.MAX_COMPONENT)
        self.assertEqual(identity.parse_release_version(release.python_version), release)
        self.assertEqual(identity.parse_release_version(release.identity), release)
        self.assertEqual(identity.parse_release_tag(release.tag), release)

    def test_constructor_rejects_non_integer_negative_and_overflow_components(self):
        cases = [('bool', True), ('negative', -1), ('overflow', identity.MAX_COMPONENT + 1),
                 ('float', 1.0), ('text', '1'), ('none', None)]
        for field in ('major', 'minor', 'patch', 'rc'):
            for label, value in cases:
                if field == 'rc' and value is None:
                    continue
                with self.subTest(field=field, case=label):
                    values = dict(major=1, minor=0, patch=0, rc=1)
                    values[field] = value
                    with self.assertRaises(identity.ReleaseIdentityError):
                        identity.ReleaseIdentity(**values)

    def test_parser_refuses_ambiguous_unsupported_and_non_ascii_versions(self):
        cases = {
            'empty': '', 'partial': '1.0', 'four_parts': '1.0.0.0', 'tag': 'v1.0.0',
            'leading_major': '01.0.0', 'leading_minor': '1.00.0', 'leading_patch': '1.0.00',
            'leading_python_rc': '1.0.0rc01', 'leading_npm_rc': '1.0.0-rc.01',
            'upper_rc': '1.0.0RC1', 'missing_rc': '1.0.0rc', 'missing_dot': '1.0.0-rc1',
            'pep_separator': '1.0.0.rc1', 'negative_rc': '1.0.0rc-1',
            'epoch': '1!1.0.0', 'post': '1.0.0.post1', 'dev': '1.0.0.dev1',
            'local': '1.0.0+local', 'build': '1.0.0-rc.1+build', 'alpha': '1.0.0a1',
            'beta': '1.0.0-beta.1', 'space': ' 1.0.0', 'newline': '1.0.0\n',
            'unicode_number': '١.0.0', 'unicode_rc': '1.0.0rc١', 'nul': '1.0.0\0',
            'overflow': '9007199254740992.0.0', 'rc_overflow': '1.0.0rc9007199254740992',
            'non_string': None,
        }
        for label, value in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(identity.ReleaseIdentityError):
                    identity.parse_release_version(value)

    def test_tag_parser_accepts_only_prefixed_canonical_identity(self):
        self.assertEqual(identity.parse_release_tag('v1.0.0'), identity.ReleaseIdentity(1, 0, 0))
        self.assertEqual(identity.parse_release_tag('v1.0.0-rc.1'), identity.ReleaseIdentity(1, 0, 0, 1))
        for label, tag in [('bare', '1.0.0'), ('python', 'v1.0.0rc1'), ('upper', 'V1.0.0'),
                           ('double', 'vv1.0.0'), ('trailing', 'v1.0.0\n'), ('non_string', None)]:
            with self.subTest(case=label):
                with self.assertRaises(identity.ReleaseIdentityError):
                    identity.parse_release_tag(tag)

    def test_precedence_orders_rc_numerically_before_final_and_next_base(self):
        versions = ['1.0.0-rc.0', '1.0.0-rc.2', '1.0.0-rc.10', '1.0.0', '1.0.1-rc.0', '1.0.1']
        releases = [identity.parse_release_version(v) for v in versions]
        self.assertEqual(sorted(reversed(releases), key=lambda r: r.precedence_key), releases)
        self.assertEqual(releases[0].release, releases[3].release,
                         'base threshold is explicit and must not pretend RC equals final')

    def test_wheel_filename_normalizes_name_and_uses_python_rc_form(self):
        release = identity.parse_release_version('1.0.0-rc.1')
        self.assertEqual(release.wheel_filename('Awesome.Telegram--Patterns'),
                         'awesome_telegram_patterns-1.0.0rc1-py3-none-any.whl')
        self.assertEqual(identity.parse_release_version('0.24.0').wheel_filename('awesome-telegram-patterns'),
                         'awesome_telegram_patterns-0.24.0-py3-none-any.whl')

    def test_npm_tarball_filename_has_explicit_scoped_normalization(self):
        release = identity.parse_release_version('1.0.0rc1')
        self.assertEqual(release.npm_tarball_filename('@awesome-telegram/patterns'),
                         'awesome-telegram-patterns-1.0.0-rc.1.tgz')
        self.assertEqual(release.npm_tarball_filename('patterns'), 'patterns-1.0.0-rc.1.tgz')

    def test_artifact_names_refuse_paths_urls_traversal_and_wrong_ecosystem_names(self):
        release = identity.ReleaseIdentity(1, 0, 0)
        shared = [('empty', ''), ('parent', '../name'), ('windows', 'a\\name'), ('absolute', '/name'),
                  ('uri', 'https://example/name'), ('space', 'some name'), ('nul', 'a\0b')]
        for label, name in shared + [('scope', '@scope/name'), ('dot', '..'), ('trailing', 'name-')]:
            with self.subTest(kind='wheel', case=label):
                with self.assertRaises(identity.ReleaseIdentityError):
                    release.wheel_filename(name)
        for label, name in shared + [('upper', 'Name'), ('parent_scope', '@../name'),
                                     ('extra_path', '@scope/name/other'), ('dot', '..'), ('too_long', 'x' * 215)]:
            with self.subTest(kind='npm', case=label):
                with self.assertRaises(identity.ReleaseIdentityError):
                    release.npm_tarball_filename(name)


class ReleaseManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='release-identity-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.python = self.directory / 'python project' / 'pyproject.toml'
        self.npm = self.directory / 'node project' / 'package.json'
        self.python.parent.mkdir()
        self.npm.parent.mkdir()

    def manifests(self, python='1.0.0rc1', npm='1.0.0-rc.1'):
        self.python.write_text(f'# сохраняется без исправления\n[project]\nname = "example"\nversion = "{python}"\n', encoding='utf-8')
        self.npm.write_text(json.dumps({'name': '@example/patterns', 'version': npm}, indent=3) + '\n', encoding='utf-8')

    def snapshot(self):
        return {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (self.python, self.npm) if p.exists()}

    def test_reads_real_separate_paths_and_preserves_caller_files(self):
        self.manifests()
        before = self.snapshot()
        self.assertEqual(identity.read_release_identity(self.python, str(self.npm)), identity.ReleaseIdentity(1, 0, 0, 1))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual({p.name for p in self.directory.rglob('*') if p.is_file()}, {'pyproject.toml', 'package.json'})

    def test_numeric_manifest_identity_is_supported(self):
        self.manifests('0.24.0', '0.24.0')
        self.assertEqual(identity.read_release_identity(self.python, self.npm), identity.ReleaseIdentity(0, 24, 0))

    def test_rejects_manifest_mismatch_or_wrong_registry_form_without_rewrite(self):
        cases = [('different_rc', '1.0.0rc1', '1.0.0-rc.2'), ('final_vs_rc', '1.0.0', '1.0.0-rc.1'),
                 ('different_base', '1.0.0', '1.0.1'), ('python_uses_npm', '1.0.0-rc.1', '1.0.0-rc.1'),
                 ('npm_uses_python', '1.0.0rc1', '1.0.0rc1')]
        for label, python, npm in cases:
            with self.subTest(case=label):
                self.manifests(python, npm)
                before = self.snapshot()
                with self.assertRaises(identity.ReleaseIdentityError):
                    identity.read_release_identity(self.python, self.npm)
                self.assertEqual(self.snapshot(), before)

    def test_malformed_missing_or_ambiguous_manifest_fields_fail_without_rewrite(self):
        cases = [
            ('invalid_toml', '[project', '{"version":"1.0.0"}'),
            ('missing_project', 'version="1.0.0"', '{"version":"1.0.0"}'),
            ('missing_python_version', '[project]', '{"version":"1.0.0"}'),
            ('python_non_string', '[project]\nversion=1', '{"version":"1.0.0"}'),
            ('json_array', '[project]\nversion="1.0.0"', '[]'),
            ('invalid_json', '[project]\nversion="1.0.0"', '{'),
            ('missing_npm_version', '[project]\nversion="1.0.0"', '{}'),
            ('npm_non_string', '[project]\nversion="1.0.0"', '{"version":1}'),
            ('duplicate_npm_version', '[project]\nversion="1.0.0"', '{"version":"1.0.0","version":"1.0.1"}'),
            ('duplicate_python_version', '[project]\nversion="1.0.0"\nversion="1.0.1"', '{"version":"1.0.0"}'),
        ]
        for label, python, npm in cases:
            with self.subTest(case=label):
                self.python.write_text(python, encoding='utf-8')
                self.npm.write_text(npm, encoding='utf-8')
                before = self.snapshot()
                with self.assertRaises(identity.ReleaseIdentityError):
                    identity.read_release_identity(self.python, self.npm)
                self.assertEqual(self.snapshot(), before)

    def test_missing_and_non_utf8_files_fail_without_creating_or_replacing_files(self):
        with self.assertRaises(identity.ReleaseIdentityError):
            identity.read_release_identity(self.python, self.npm)
        self.assertFalse(self.python.exists())
        self.assertFalse(self.npm.exists())
        for label, target in [('python', self.python), ('npm', self.npm)]:
            with self.subTest(case=label):
                self.manifests()
                target.write_bytes(b'\xff')
                before = self.snapshot()
                with self.assertRaises(identity.ReleaseIdentityError):
                    identity.read_release_identity(self.python, self.npm)
                self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
