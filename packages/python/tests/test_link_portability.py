"""Known links stay refused; OS aliases under / (macOS /var, /tmp -> /private/...) are trusted."""

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import telegram_patterns.diagnostics as diagnostics
import telegram_patterns.starter as starter


def fake_stat(uid):
    return os.stat_result((stat.S_IFLNK | 0o755, 0, 0, 1, uid, 0, 0, 0, 0, 0))


class LinkPortabilityTests(unittest.TestCase):
    def test_user_links_are_refused_everywhere(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'target'
            target.mkdir()
            link = Path(folder) / 'link'
            link.symlink_to(target, target_is_directory=True)
            for module in (diagnostics, starter):
                with self.subTest(module=module.__name__):
                    self.assertTrue(module._linked(link))
                    self.assertFalse(module._linked(target))

    def test_root_owned_alias_directly_under_root_is_system_layout(self):
        alias = Path('/var-alias-fixture')
        with patch.object(Path, 'is_symlink', lambda self: self == alias):
            for module in (diagnostics, starter):
                with self.subTest(module=module.__name__):
                    with patch.object(Path, 'lstat', lambda self: fake_stat(0)):
                        self.assertFalse(module._linked(alias), 'macOS /var-like alias is trusted')
                    with patch.object(Path, 'lstat', lambda self: fake_stat(501)):
                        self.assertTrue(module._linked(alias), 'a user-owned link under / stays refused')
                    with patch.object(module.os, 'name', 'nt'), patch.object(Path, 'lstat', lambda self: fake_stat(0)):
                        self.assertTrue(module._linked(alias), 'Windows junctions stay refused')

    def test_nested_root_owned_link_is_still_refused(self):
        nested = Path('/var-alias-fixture/inner')
        with (
            patch.object(Path, 'is_symlink', lambda self: self == nested),
            patch.object(Path, 'lstat', lambda self: fake_stat(0)),
        ):
            self.assertTrue(diagnostics._linked(nested))
            self.assertTrue(starter._linked(nested))

    @unittest.skipUnless(Path('/var').is_symlink(), 'real check only where /var is an OS alias (macOS)')
    def test_real_macos_temp_directory_is_accepted(self):
        self.assertFalse(diagnostics._linked(Path('/var')))
        with tempfile.TemporaryDirectory() as folder:
            report = diagnostics.diagnose(folder, require_token=False)
        self.assertNotIn('linked-project', [check['reason'] for check in report['checks']])


if __name__ == '__main__':
    unittest.main()
