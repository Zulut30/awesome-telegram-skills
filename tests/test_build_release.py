"""Заметки к релизу и проверка входных данных скрипта сборки релиза."""
import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_release', ROOT / 'scripts/build_release.py')
build_release = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = build_release
spec.loader.exec_module(build_release)


class BuildReleaseTests(unittest.TestCase):
    def test_notes_name_the_version_and_explain_verification(self):
        version = build_release._version('HEAD')
        self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        text = build_release.notes('HEAD')
        self.assertTrue(text.startswith(f'awesome-telegram-patterns и @awesome-telegram/patterns {version}.'))
        self.assertIn('sha256sum -c SHA256SUMS', text)

    def test_workflow_validates_tags_and_publishes_prereleases(self):
        workflow = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
        self.assertIn('^v[0-9]+\\.[0-9]+\\.[0-9]+$', workflow)
        self.assertIn('--prerelease', workflow)
        self.assertIn('scripts/build_release.py --ref "$tag"', workflow)
        for line in re.findall(r'uses: (\S+)', workflow):
            self.assertRegex(line, r'@[0-9a-f]{40}$', 'actions are pinned by commit SHA')


class ReleaseTagManifestTests(unittest.TestCase):
    def test_manifest_matches_history_where_available(self):
        import json, subprocess
        entries = json.loads((ROOT / '.github/release-tags.json').read_text(encoding='utf-8'))['tags']
        versions = [tuple(map(int, e['version'].split('.'))) for e in entries]
        self.assertEqual(versions, sorted(set(versions)), 'unique and ascending')
        checked = 0
        for entry in entries:
            self.assertEqual(entry['tag'], 'v' + entry['version'])
            self.assertRegex(entry['commit'], r'^[0-9a-f]{40}$')
            shown = subprocess.run(['git', 'show', f"{entry['commit']}:packages/python/pyproject.toml"], cwd=ROOT,
                                   capture_output=True, text=True)
            if shown.returncode != 0:
                continue  # shallow CI checkout: history is not available
            self.assertIn(f'version = "{entry["version"]}"', shown.stdout, entry['tag'])
            checked += 1
        self.assertGreaterEqual(len(entries), 23)


if __name__ == '__main__':
    unittest.main()
