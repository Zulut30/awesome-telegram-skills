"""A newer aiogram on PyPI becomes one issue with the upgrade checklist; Dependabot leaves aiogram to it."""
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('aiogram_release', ROOT / 'scripts/aiogram_release.py')
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


class AiogramReleaseTests(unittest.TestCase):
    def test_latest_skips_prereleases_yanked_and_empty_releases(self):
        releases = {'3.31.0': [{}], '3.32.0rc1': [{}], '3.33.0': [{'yanked': True}], '3.32.0': [{}], '3.40.0': [],
                    '3.9.0': [{}]}
        self.assertEqual(watch.latest(releases), '3.32.0')

    def test_compare_reports_minor_and_major_releases(self):
        self.assertFalse(watch.compare('3.31.0', '3.31.0')['changed'])
        minor = watch.compare('3.31.0', '3.32.0')
        self.assertEqual((minor['changed'], minor['major']), (True, False))
        self.assertIn('aiogram 3.32.0', minor['title'])
        major = watch.compare('3.31.0', '4.0.0')
        self.assertEqual((major['changed'], major['major']), (True, True))
        self.assertIn('major', watch.markdown(major))

    def test_checklist_names_files_that_exist(self):
        body = watch.markdown(watch.compare('3.31.0', '3.32.0'))
        for path in re.findall(r'`((?:\.github|packages|requirements|scripts|docs)/[^`\s]+)`', body):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).exists(), path)
        self.assertIn('tests.test_skill_sources', body)

    def test_pin_is_read_from_requirements(self):
        self.assertRegex(watch.pinned(), r'^\d+\.\d+\.\d+$')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sdk.txt'
            path.write_text('aiogram>=3\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                watch.pinned(path)

    def test_dependabot_ignores_aiogram_and_the_watch_opens_one_issue(self):
        config = (ROOT / '.github/dependabot.yml').read_text(encoding='utf-8')
        self.assertIn('- dependency-name: aiogram', config)
        self.assertNotIn('aiogram', re.search(r'sdks:\n\s+patterns: \[([^\]]*)\]', config).group(1))
        workflow = (ROOT / '.github/workflows/telegram-docs-watch.yml').read_text(encoding='utf-8')
        block = workflow.split('\n  aiogram:\n', 1)[1]
        self.assertIn('python scripts/aiogram_release.py', block)
        self.assertIn('--state all --search "$KEY in:title"', block, 'a closed issue is not reopened weekly')
        self.assertIn('issues: write', block)


if __name__ == '__main__':
    unittest.main()
