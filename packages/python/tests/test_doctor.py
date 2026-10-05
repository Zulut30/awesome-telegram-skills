"""Repair guidance is actionable while diagnosis stays local and read only."""
from contextlib import redirect_stdout, redirect_stderr
import importlib.metadata
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from telegram_patterns.cli import doctor, main
import telegram_patterns.diagnostics as diagnostics

CANARY = 'DOCTOR_PRIVATE_CANARY'


class DoctorTests(unittest.TestCase):
    def setUp(self):
        # Installed-consumer verification exercises the real isolated SDK imports.
        # Error/manifest unit cases do not need to repeat SDK startup per payload.
        if self._testMethodName != 'test_isolated_sdk_probe_cannot_receive_project_or_secrets':
            sdk = patch.object(diagnostics, '_sdk_probe', return_value=True)
            sdk.start(); self.addCleanup(sdk.stop)

    def by_name(self, report, name):
        return next(item for item in report['checks'] if item['name'] == name)

    def assert_guidance(self, report):
        self.assertFalse(report['network'])
        self.assertFalse(report['suggestions_executed'])
        self.assertNotIn(CANARY, json.dumps(report))
        for check in report['checks']:
            self.assertIsInstance(check['reason'], str)
            self.assertTrue(check['reason'])
            if check['status'] != 'pass':
                self.assertTrue(check['remediation']['summary'])
                self.assertTrue(check['remediation']['commands'])
            for command in check['remediation']['commands']:
                self.assertTrue(command['argv'])
                self.assertIn(command['cwd'], ('project', 'mini-app'))
                self.assertIsInstance(command['requires_substitution'], bool)

    def manifest(self, root):
        (root / 'pyproject.toml').write_text('[project]\nname="doctor-fixture"\n', encoding='utf-8')
        mini = root / 'mini-app'; mini.mkdir()
        (mini / 'package.json').write_text(json.dumps({'dependencies': {'@awesome-telegram/patterns': 'file:provided.tgz'}}), encoding='utf-8')

    def test_valid_bot_stays_read_only_and_does_not_read_env_or_project_code(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'pyproject.toml').write_text('[project]\nname="fixture"\n')
            (root / '.env').write_text('BOT_TOKEN=' + CANARY)
            (root / 'app.py').write_text('raise RuntimeError("' + CANARY + '")')
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with patch.dict(os.environ, {'BOT_TOKEN': '100:' + CANARY}), \
                    patch.object(Path, 'write_text', side_effect=AssertionError('write forbidden')), \
                    patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')), \
                    patch.object(diagnostics, '_sdk_probe', return_value=True):
                report = doctor(root, require_token=True)
            self.assertTrue(report['passed']); self.assert_guidance(report)
            self.assertEqual(report['tool_probes_attempted'], ['python -I -B adapter imports'])
            self.assertEqual(self.by_name(report, 'token-format')['reason'], 'token-format-valid')
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_sdk_missing_invalid_and_unverified_version_have_distinct_repairs(self):
        original = importlib.metadata.version
        with tempfile.TemporaryDirectory() as folder:
            for version, reason, status in ((None, 'sdk-missing', 'fail'), ('2.25.1', 'sdk-incompatible', 'fail'),
                    (CANARY, 'sdk-incompatible', 'fail'), ('3.32.0', 'sdk-supported', 'pass')):
                def metadata(name):
                    if name != 'aiogram': return original(name)
                    if version is None: raise importlib.metadata.PackageNotFoundError(CANARY)
                    return version
                with self.subTest(version=version), patch.object(diagnostics.importlib.metadata, 'version', side_effect=metadata):
                    report = doctor(folder)
                    check = self.by_name(report, 'aiogram')
                    self.assertEqual((check['reason'], check['status']), (reason, status)); self.assert_guidance(report)
                    if version == '3.32.0': self.assertEqual(self.by_name(report, 'sdk-tested-version')['reason'], 'sdk-not-tested')
                    else: self.assertIn('<PROVIDED_WHEEL>[aiogram]', check['remediation']['commands'][-1]['argv'])

    def test_token_missing_and_invalid_are_safe_and_required_flag_is_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            for value, reason in (('', 'token-missing'), (CANARY, 'token-format-invalid')):
                with self.subTest(value=value), patch.dict(os.environ, {'BOT_TOKEN': value}):
                    optional = doctor(folder)
                    required = doctor(folder, require_token=True)
                self.assertEqual(self.by_name(optional, 'token-format')['status'], 'warn')
                self.assertEqual(self.by_name(required, 'token-format')['status'], 'fail')
                self.assertEqual(self.by_name(required, 'token-format')['reason'], reason)
                self.assert_guidance(optional); self.assert_guidance(required)

    def test_manifest_shapes_missing_oversized_and_malformed_are_reported_without_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.manifest(root)
            mini = root / 'mini-app/package.json'
            for payload, reason in ((CANARY, 'json-invalid'), ('[]', 'mini-app-dependency-missing'),
                    ('{"dependencies":null}', 'mini-app-dependency-missing'),
                    ('{"dependencies":"' + CANARY + '"}', 'mini-app-dependency-missing'),
                    ('{"dependencies":{"@awesome-telegram/patterns":false}}', 'mini-app-dependency-missing'),
                    ('{"dependencies":{"@awesome-telegram/patterns":""}}', 'mini-app-dependency-missing'),
                    ('x' * (256 * 1024 + 1), 'manifest-too-large')):
                mini.write_text(payload, encoding='utf-8')
                with self.subTest(reason=reason), patch.object(diagnostics.shutil, 'which', return_value=None):
                    report = doctor(root)
                self.assertEqual(self.by_name(report, 'mini-app-manifest')['reason'], reason)
                self.assert_guidance(report)
            mini.unlink()
            report = doctor(root)
            self.assertEqual(self.by_name(report, 'mini-app-manifest')['reason'], 'missing-manifest')
            (root / 'pyproject.toml').write_bytes(b'\xff' + CANARY.encode())
            report = doctor(root)
            self.assertEqual(self.by_name(report, 'pyproject')['reason'], 'manifest-encoding')
            (root / 'pyproject.toml').write_text(CANARY)
            self.assertEqual(self.by_name(doctor(root), 'pyproject')['reason'], 'toml-invalid')
            self.assert_guidance(report)

    def test_node_probe_uses_only_fixed_args_and_allowlisted_env_never_echoes_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.manifest(root)
            for stdout, code, reason in (('v24.19.0\n', 0, 'node-supported'), ('v18.1.0', 0, 'node-too-old'),
                    (CANARY, 0, 'node-probe-failed'), ('v24.19.0', 1, 'node-probe-failed')):
                with self.subTest(reason=reason), patch.dict(os.environ, {'BOT_TOKEN': '100:' + CANARY, 'NODE_OPTIONS': CANARY, 'PAYMENT_SECRET': CANARY}), \
                        patch.object(diagnostics.shutil, 'which', return_value='trusted-node'), \
                        patch.object(diagnostics.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, stdout, CANARY)) as run:
                    report = doctor(root)
                args, kwargs = run.call_args
                self.assertEqual(args, (['trusted-node', '--version'],))
                self.assertFalse(kwargs['shell']); self.assertEqual(kwargs['timeout'], 10)
                self.assertEqual(kwargs['cwd'], root)
                self.assertFalse(any(CANARY in value for value in kwargs['env'].values()))
                self.assertEqual(self.by_name(report, 'node')['reason'], reason); self.assert_guidance(report)
            for error in (OSError(CANARY), subprocess.TimeoutExpired(CANARY, 10, output=CANARY)):
                with patch.object(diagnostics.shutil, 'which', return_value='trusted-node'), \
                        patch.object(diagnostics.subprocess, 'run', side_effect=error):
                    report = doctor(root)
                self.assertEqual(self.by_name(report, 'node')['reason'], 'node-probe-failed'); self.assert_guidance(report)

    def test_unavailable_target_and_linked_or_unreadable_manifest_are_local_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.manifest(root)
            missing = doctor(root / CANARY)
            self.assertFalse(missing['passed']); self.assert_guidance(missing)
            file = root / 'file'; file.write_text(CANARY)
            self.assertEqual(self.by_name(doctor(file), 'project')['reason'], 'project-not-directory')
            pyproject = root / 'pyproject.toml'
            real_linked = diagnostics._linked
            with patch.object(diagnostics, '_linked', side_effect=lambda path: path == pyproject or real_linked(path)):
                report = doctor(root)
            self.assertEqual(self.by_name(report, 'pyproject')['reason'], 'linked-manifest'); self.assert_guidance(report)
            original_open = Path.open
            def read_file(path, *args, **kwargs):
                if path in (pyproject, root / 'mini-app/package.json'): raise PermissionError(CANARY)
                return original_open(path, *args, **kwargs)
            with patch.object(Path, 'open', read_file):
                report = doctor(root)
            self.assertEqual(self.by_name(report, 'pyproject')['reason'], 'manifest-unreadable'); self.assert_guidance(report)

    def test_corrupt_library_metadata_and_adapter_import_do_not_print_exception_data(self):
        original_version = importlib.metadata.version
        with tempfile.TemporaryDirectory() as folder:
            for version in (None, CANARY):
                def metadata(name):
                    if name != 'awesome-telegram-patterns': return original_version(name)
                    if version is None: raise importlib.metadata.PackageNotFoundError(CANARY)
                    return version
                with patch.object(diagnostics.importlib.metadata, 'version', side_effect=metadata):
                    report = doctor(folder)
                self.assertFalse(report['passed']); self.assert_guidance(report)
                self.assertEqual(self.by_name(report, 'library')['reason'], 'library-not-installed' if version is None else 'library-version-invalid')
            with patch.object(diagnostics, '_sdk_probe', return_value=False):
                report = doctor(folder)
            self.assertEqual(self.by_name(report, 'python-exports')['reason'], 'adapter-import-failed')
            self.assert_guidance(report)

    def test_isolated_sdk_probe_cannot_receive_project_or_secrets(self):
        with patch.dict(os.environ, {'BOT_TOKEN': CANARY, 'PYTHONPATH': CANARY, 'PAYMENT_SECRET': CANARY}), \
                patch.object(diagnostics.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'ready\n', CANARY)) as run:
            self.assertTrue(diagnostics._sdk_probe())
        args, kwargs = run.call_args
        self.assertEqual(args[0][:4], [diagnostics.sys.executable, '-I', '-B', '-c'])
        self.assertEqual(args[0][4], diagnostics._SDK_PROBE)
        self.assertEqual(kwargs['cwd'], diagnostics.sys.prefix)
        self.assertEqual(kwargs['timeout'], 30)
        self.assertFalse(any(CANARY in v for v in kwargs['env'].values()))
        for output in (CANARY, 'ready\n' + CANARY):
            with patch.object(diagnostics.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, CANARY)):
                self.assertFalse(diagnostics._sdk_probe())
        for error in (OSError(CANARY), subprocess.TimeoutExpired(CANARY, 30, output=CANARY)):
            with patch.object(diagnostics.subprocess, 'run', side_effect=error):
                self.assertFalse(diagnostics._sdk_probe())

    def test_cli_returns_actionable_json_for_failed_target_and_successful_bot(self):
        with tempfile.TemporaryDirectory() as folder:
            for target, expected in ((folder, 0), (str(Path(folder) / CANARY), 1)):
                with self.subTest(expected=expected), patch.dict(os.environ, {'BOT_TOKEN': ''}), \
                        redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as errors:
                    status = main(['doctor', target])
                self.assertEqual(status, expected); self.assertFalse(errors.getvalue())
                self.assert_guidance(json.loads(output.getvalue()))
