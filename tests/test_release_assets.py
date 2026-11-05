"""Immutable release append and checksum boundaries with actual files and child processes."""
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import release_assets


class ReleaseAssetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='release asset caller ')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.assets = self.root / 'assets'
        self.assets.mkdir()
        self.marker = self.root / 'caller-owned.txt'
        self.marker.write_bytes(b'keep caller notes')

    def asset(self, name='example.whl', content=b'package bytes'):
        path = self.assets / name
        path.write_bytes(content)
        return {'name': name, 'size': len(content), 'digest': 'sha256:' + hashlib.sha256(content).hexdigest()}

    def manifest(self, names):
        manifest = self.assets / 'SHA256SUMS'
        manifest.write_text(''.join(hashlib.sha256((self.assets / name).read_bytes()).hexdigest() + '  ' + name + '\n'
                                    for name in names), encoding='ascii')
        return manifest

    def test_existing_bytes_match_or_the_entire_append_plan_is_refused(self):
        published = self.asset()
        self.asset('new.cdx.json', b'{"bomFormat":"CycloneDX"}')
        self.assertEqual(release_assets.append_plan(self.assets, [published]),
                         {'kept': ['example.whl'], 'upload': ['new.cdx.json']})
        (self.assets / 'example.whl').write_bytes(b'changed bytes')
        with self.assertRaisesRegex(release_assets.ReleaseAssetError, 'Published bytes differ'):
            release_assets.append_plan(self.assets, [published])
        self.assertEqual(self.marker.read_bytes(), b'keep caller notes')

    def test_duplicate_remote_names_and_unknown_hashes_cannot_be_assumed_equal(self):
        remote = self.asset()
        for rows in ([remote, dict(remote)], [dict(remote, digest=None)], [dict(remote, size=True)]):
            with self.subTest(rows=rows), self.assertRaises(release_assets.ReleaseAssetError):
                release_assets.append_plan(self.assets, rows)

    def test_checksum_verification_covers_required_files_and_detects_changed_bytes(self):
        names = {'example.whl', 'example.tgz', 'example.cdx.json'}
        for name in names:
            self.asset(name, name.encode())
        self.manifest(sorted(names))
        checked = release_assets.verify_checksums(self.assets, required=names)
        self.assertEqual(set(checked), names)
        (self.assets / 'example.tgz').write_bytes(b'tampered archive')
        with self.assertRaises(release_assets.ReleaseAssetError):
            release_assets.verify_checksums(self.assets, required=names)

    def test_manifest_traversal_duplicates_missing_required_and_self_reference_are_refused(self):
        self.asset()
        outside = self.root / 'outside'
        outside.write_bytes(b'never read this file')
        digest = hashlib.sha256(outside.read_bytes()).hexdigest()
        valid = self.manifest(['example.whl']).read_text('ascii')
        for text in [digest + '  ../outside\n', digest + '  /outside\n', valid + valid,
                     digest + '  SHA256SUMS\n', '', valid + digest + '  sub/file\n']:
            with self.subTest(text=text):
                (self.assets / 'SHA256SUMS').write_text(text, encoding='ascii')
                with self.assertRaises(release_assets.ReleaseAssetError):
                    release_assets.verify_checksums(self.assets, required={'example.whl'})
        self.manifest(['example.whl'])
        with self.assertRaises(release_assets.ReleaseAssetError):
            release_assets.verify_checksums(self.assets, required={'missing.tgz'})
        self.assertEqual(outside.read_bytes(), b'never read this file')

    def test_symbolic_artifact_is_not_read_or_published(self):
        target = self.root / 'private'
        target.write_bytes(b'private marker')
        try:
            (self.assets / 'example.whl').symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('Windows symbolic link creation is unavailable')
        with self.assertRaises(release_assets.ReleaseAssetError):
            release_assets.append_plan(self.assets, [])
        (self.assets / 'SHA256SUMS').write_text(hashlib.sha256(target.read_bytes()).hexdigest() + '  example.whl\n', 'ascii')
        with self.assertRaises(release_assets.ReleaseAssetError):
            release_assets.verify_checksums(self.assets, required={'example.whl'})

    def fake_gh(self, remote, *, conflict=False):
        state = self.root / 'remote-state.json'
        state.write_text(json.dumps({'remote': remote, 'calls': [], 'conflict': conflict}), 'utf-8')
        program = self.root / 'fake_gh.py'
        program.write_text('''import hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); args=sys.argv[2:]; state=json.loads(p.read_text()); state['calls'].append(args)
if args[:2]==['api','repos/example/repo/releases/tags/v1.0.0']:
    data=state['release_override'] if 'release_override' in state else {'id':19,'tag_name':'v1.0.0'}
elif args[:3]==['api','--paginate','--slurp']:
    data=[state['remote'][:1],state['remote'][1:]]
elif args[:3]==['api','-H','Accept: application/octet-stream']:
    p.write_text(json.dumps(state)); sys.stdout.buffer.write(b'package bytes'); sys.exit(0)
elif args[:2]==['release','upload']:
    assert '--clobber' not in args
    if state['conflict']:
        p.write_text(json.dumps(state)); print('PRIVATE_ERROR_CANARY',file=sys.stderr);sys.exit(1)
    for name in args[3:args.index('--repo')]:
        file=pathlib.Path(name); assert file.is_file()
        state['remote'].append({'name':file.name,'size':file.stat().st_size,'digest':'sha256:'+hashlib.sha256(file.read_bytes()).hexdigest()})
    data={}
else:
    raise AssertionError(args)
p.write_text(json.dumps(state)); print(json.dumps(data))
''', 'utf-8')
        actual_run = subprocess.run

        def run(command, **kwargs):
            self.assertEqual(command[0], 'gh')
            return actual_run([sys.executable, str(program), str(state), *command[1:]], **kwargs)
        return state, run

    def test_invalid_successful_release_responses_fail_before_any_upload(self):
        self.asset()
        for response in ([], None, {'id': True, 'tag_name': 'v1.0.0'}, {'id': 19, 'tag_name': 'v2.0.0'}):
            with self.subTest(response=response):
                state, transport = self.fake_gh([])
                data = json.loads(state.read_text()); data['release_override'] = response
                state.write_text(json.dumps(data))
                with patch.object(release_assets.subprocess, 'run', side_effect=transport), self.assertRaises(release_assets.ReleaseAssetError):
                    release_assets.append_assets(self.assets, 'example/repo', 'v1.0.0')
                calls = json.loads(state.read_text())['calls']
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][0], 'api')

    def test_actual_child_transport_downloads_legacy_hash_and_only_appends_new_files(self):
        existing = dict(self.asset(), id=11, digest=None)
        new = self.asset('new.tgz', b'new bytes')
        state, transport = self.fake_gh([existing])
        with patch.object(release_assets.subprocess, 'run', side_effect=transport):
            plan = release_assets.append_assets(self.assets, 'example/repo', 'v1.0.0')
        self.assertEqual(plan, {'kept': ['example.whl'], 'upload': ['new.tgz']})
        data = json.loads(state.read_text('utf-8'))
        writes = [args for args in data['calls'] if args[:2] == ['release', 'upload']]
        self.assertEqual(len(writes), 1)
        self.assertEqual(data['remote'][-1], new)
        self.assertTrue(any(args[:3] == ['api', '-H', 'Accept: application/octet-stream'] for args in data['calls']))
        self.assertEqual(self.marker.read_bytes(), b'keep caller notes')

    def test_conflicting_preflight_never_uploads_and_racing_collision_is_not_clobbered(self):
        remote = self.asset()
        self.asset('new.tgz', b'new')
        (self.assets / 'example.whl').write_bytes(b'conflicting')
        state, transport = self.fake_gh([remote])
        with patch.object(release_assets.subprocess, 'run', side_effect=transport), self.assertRaises(release_assets.ReleaseAssetError):
            release_assets.append_assets(self.assets, 'example/repo', 'v1.0.0')
        self.assertFalse(any(args[:2] == ['release', 'upload'] for args in json.loads(state.read_text())['calls']))
        self.asset()
        state, transport = self.fake_gh([remote], conflict=True)
        with patch.object(release_assets.subprocess, 'run', side_effect=transport), self.assertRaises(release_assets.ReleaseAssetError) as error:
            release_assets.append_assets(self.assets, 'example/repo', 'v1.0.0')
        self.assertNotIn('PRIVATE_ERROR_CANARY', str(error.exception))
        self.assertEqual(json.loads(state.read_text())['remote'], [remote])

    def test_failed_cli_hides_inherited_gh_error_and_preserves_local_files(self):
        remote = self.asset()
        self.asset('new.tgz', b'new')
        _, transport = self.fake_gh([remote], conflict=True)
        output = io.StringIO()
        with patch.object(release_assets.subprocess, 'run', side_effect=transport), redirect_stdout(output), patch.object(
                sys, 'argv', ['release-assets', '--directory', str(self.assets), '--repo', 'example/repo', '--tag', 'v1.0.0']):
            self.assertEqual(release_assets.main(), 1)
        self.assertFalse(json.loads(output.getvalue())['passed'])
        self.assertNotIn('PRIVATE_ERROR_CANARY', output.getvalue())
        self.assertEqual((self.assets / 'example.whl').read_bytes(), b'package bytes')


if __name__ == '__main__':
    unittest.main()
