"""Реальные временные caller files, CLI и установленный consumer при наличии SDK."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/check_local_operations.py'
HELPERS = runpy.run_path(str(SCRIPT))


def has_installed_consumer() -> bool:
    """Editable checkout imports are not the separate wheel consumer this test needs."""
    prefix = Path(sys.prefix).resolve()
    for name in ('telegram_patterns', 'telegram_shop_example'):
        spec = importlib.util.find_spec(name)
        if spec is None or spec.origin is None or not Path(spec.origin).resolve().is_relative_to(prefix):
            return False
    return True


class LocalOperationsTests(unittest.TestCase):
    def invoke(self, output: Path, cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, '-I', '-X', 'utf8', str(SCRIPT), '--python', sys.executable,
             '--output', str(output)], cwd=cwd, capture_output=True,
            text=True, encoding='utf-8', timeout=100)

    def test_no_activation_or_credential_argument_and_no_argument_echo(self):
        result = subprocess.run([sys.executable, '-I', str(SCRIPT), '--activate',
                                 '--bot-token', '100:PRIVATE_CANARY'],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('invalid-arguments', result.stderr)
        self.assertNotIn('PRIVATE_CANARY', result.stdout + result.stderr)

    def test_existing_output_is_never_replaced(self):
        with tempfile.TemporaryDirectory(prefix='operations-caller-') as folder:
            root = Path(folder)
            output = root / 'existing'
            output.mkdir()
            sentinel = output / 'owner.txt'
            sentinel.write_bytes(b'keep exact bytes')
            result = self.invoke(output, root)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(sentinel.read_bytes(), b'keep exact bytes')
            self.assertEqual(sorted(p.name for p in output.iterdir()), ['owner.txt'])
            self.assertNotIn(str(root), result.stdout + result.stderr)

    def test_synthetic_application_secrets_and_python_injection_are_not_forwarded(self):
        with patch.dict(os.environ, {'PATH': 'fixture-tools', 'SYSTEMROOT': 'fixture-system',
                                    'BOT_TOKEN': '100:PRIVATE_CANARY', 'PAYMENT_SECRET': 'PRIVATE_CANARY',
                                    'PYTHONPATH': 'caller-code', 'HTTPS_PROXY': 'http://PRIVATE_CANARY'}, clear=True):
            env = HELPERS['child_environment']()
        self.assertEqual(env['PATH'], 'fixture-tools')
        self.assertEqual(env['SYSTEMROOT'], 'fixture-system')
        self.assertEqual(env['PYTHONUTF8'], '1')
        self.assertFalse({'BOT_TOKEN', 'PAYMENT_SECRET', 'PYTHONPATH', 'HTTPS_PROXY'} & env.keys())

    def test_linked_output_preserves_destination(self):
        with tempfile.TemporaryDirectory(prefix='operations-link-') as folder:
            root = Path(folder).resolve()
            destination = root / 'owned'
            destination.mkdir()
            sentinel = destination / 'owner.txt'
            sentinel.write_bytes(b'unchanged')
            link = root / 'link'
            try:
                if os.name == 'nt':
                    made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(destination)],
                                          capture_output=True, timeout=10)
                    if made.returncode:
                        self.skipTest('Directory junction not available to this Windows account')
                else:
                    link.symlink_to(destination, target_is_directory=True)
            except OSError:
                self.skipTest('Directory symlink not available to this Windows account')
            try:
                result = self.invoke(link / 'report', root)
                self.assertEqual(result.returncode, 2)
                self.assertIn('output-link-refused', result.stderr)
                self.assertEqual(sentinel.read_bytes(), b'unchanged')
                self.assertFalse((destination / 'report').exists())
            finally:
                if os.name == 'nt':
                    link.rmdir()  # Remove only the created junction, never its target tree.
                else:
                    link.unlink()

    @unittest.skipUnless(has_installed_consumer(),
                         'Run with a separate installed wheel consumer; editable checkout is insufficient')
    def test_installed_cli_runs_real_http_backup_restore_restart_and_refusals(self):
        with tempfile.TemporaryDirectory(prefix='operations-consumer-caller-') as folder:
            root = Path(folder)
            sentinel = root / 'owner.txt'
            sentinel.write_bytes(b'preserve caller files')
            # Only synthetic values. A caller .env must never become runtime configuration.
            (root / '.env').write_text('BOT_TOKEN=100:PRIVATE_CANARY\n', encoding='utf-8')
            output = root / 'new-report'
            result = self.invoke(output, root)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
            self.assertTrue(report['passed'])
            self.assertTrue(report['installed_origins_verified'])
            self.assertFalse(report['candidate_ready'])
            self.assertEqual(report['external_network_attempts'], 0)
            self.assertEqual(set(report['stages']), {
                'installed-loopback-start', 'readiness-probe', 'active-writer-refused',
                'graceful-stop-and-lock-release', 'backup-cli', 'existing-backup-refused',
                'restore-new-cli', 'existing-restore-refused', 'unknown-identity-preserved',
                'prepare-closed-cli', 'inspect-maintenance-cli', 'marker-rollback-refused',
                'schema-rollback-refused', 'same-artifact-command-restart',
                'stopped-probe-unavailable'})
            serialized = json.dumps(report) + result.stdout + result.stderr
            self.assertNotIn('PRIVATE_CANARY', serialized)
            self.assertNotIn(str(root), serialized)
            self.assertEqual(sentinel.read_bytes(), b'preserve caller files')
            self.assertEqual((root / '.env').read_text(encoding='utf-8'),
                             'BOT_TOKEN=100:PRIVATE_CANARY\n')


if __name__ == '__main__':
    unittest.main()
