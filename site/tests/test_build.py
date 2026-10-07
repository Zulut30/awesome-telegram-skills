"""Exercise documentation helpers with real files in owned temporary directories."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_docs_site import Builder
from verify_docs_site import verify


class DocumentationOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(os.environ.get('DOCS_SOURCE', ROOT)).resolve()
        cls.temporary = TemporaryDirectory(prefix='telegram-documentation-operations-')
        cls.base = Path(cls.temporary.name).resolve()
        cls.site = cls.base / 'site'
        cls.manifest = Builder(cls.source, cls.site, 'https://zulut30.github.io/awesome-telegram-skills/', 'preview').build()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_build_and_local_link_closure(self):
        result = verify(self.site)
        self.assertTrue(result['passed'], result['errors'])
        self.assertEqual(result['skills'], len(list((self.source / '.agents/skills').glob('*/SKILL.md'))))

    def test_sidebar_follows_the_navigation_manifest_and_internal_pages_stay_out(self):
        import re
        navigation = json.loads((self.source / 'docs/navigation.json').read_text(encoding='utf-8'))
        expected = [entry['title'] for section in navigation['sections'] for entry in section['pages'] if entry.get('nav')]
        for route in ('index.html', 'docs/index.html', 'docs/quickstart/index.html', 'skills/telegram-bot-api/index.html'):
            with self.subTest(route):
                page = (self.site / route).read_text(encoding='utf-8')
                sidebar = re.search(r'<nav id="site-navigation".*?</nav>', page, re.S).group(0)
                self.assertEqual(re.findall(r'<a href="[^"]+"[^>]*>([^<]+)</a>', sidebar), expected)
                self.assertEqual(re.findall(r'nav-label">([^<]+)<', sidebar), ['Обучение', 'Как сделать', 'Справочник', 'Объяснения'])
        self.assertLessEqual(len(expected), navigation['max_sidebar_pages'])
        self.assertTrue((self.site / 'docs/internal/README/index.html').is_file())
        search = json.loads((self.site / 'search-index.json').read_text(encoding='utf-8'))
        self.assertFalse([entry['path'] for entry in search if entry['path'].startswith('docs/internal/')])
        self.assertNotIn('Source: docs/internal/', (self.site / 'llms-full.txt').read_text(encoding='utf-8'))
        quickstart = (self.site / 'docs/quickstart/index.html').read_text(encoding='utf-8')
        self.assertRegex(quickstart, r'class="breadcrumbs">.*?/ Обучение</p>')

    def test_quality_board_shows_repository_numbers_and_says_when_ci_is_missing(self):
        page = (self.site / 'docs/quality-board/index.html').read_text(encoding='utf-8')
        self.assertIn('<h2 id="numbers">Числа</h2>', page)
        self.assertIn('нет данных: сайт собран без CI', page)
        self.assertIn('Выбор скиллов', page)
        self.assertRegex(page, r'Методы Bot API [0-9.]+ с рецептом</td><td>\d+ из \d+')

    def test_check_rebuild_keeps_existing_output(self):
        before = (self.site / 'index.html').read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_docs_site.py'), '--source', str(self.source), '--output', str(self.site), '--check'], capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.site / 'index.html').read_bytes(), before)

    def test_existing_destination_is_not_overwritten(self):
        destination = self.base / 'existing'
        destination.mkdir()
        marker = destination / 'user.txt'
        marker.write_bytes(b'preserve the existing output')
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_docs_site.py'), '--source', str(self.source), '--output', str(destination)], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Output already exists', result.stderr)
        self.assertEqual(marker.read_bytes(), b'preserve the existing output')
        self.assertEqual(list(destination.iterdir()), [marker])

    def test_tampering_fails_verification_and_check_without_repair(self):
        site = self.base / 'modified'
        shutil.copytree(self.site, site)
        file = site / 'index.html'
        file.write_bytes(file.read_bytes() + b'\n<!-- owned modification -->')
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        result = verify(site)
        self.assertFalse(result['passed'])
        self.assertIn('Changed artifact: index.html', result['errors'])
        check = subprocess.run([sys.executable, str(ROOT / 'scripts/build_docs_site.py'), '--source', str(self.source), '--output', str(site), '--check'], capture_output=True, text=True, timeout=90)
        self.assertNotEqual(check.returncode, 0)
        self.assertIn('existing output preserved', check.stderr)
        self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), digest)

    def test_unaccepted_version_is_rejected_before_writing(self):
        source = self.base / 'unaccepted'
        source.mkdir()
        for name in ['components.json', 'catalog/api-reference-index.json', 'catalog/api-reference.json', 'catalog/recipe-gallery.json']:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({'library_version': '0.0.0-unaccepted'}), encoding='utf-8')
        python = source / 'packages/python/pyproject.toml'
        python.parent.mkdir(parents=True)
        python.write_text('[project]\nversion="0.0.0-unaccepted"\n', encoding='utf-8')
        typescript = source / 'packages/typescript/package.json'
        typescript.parent.mkdir(parents=True)
        typescript.write_text('{"version":"0.0.0-unaccepted"}', encoding='utf-8')
        (source / 'docs').mkdir()
        (source / 'docs/acceptance-history.json').write_text(json.dumps({'reports': [{'version': '0.24.0', 'passed': True}]}), encoding='utf-8')
        destination = self.base / 'refused-site'
        with self.assertRaisesRegex(ValueError, 'accepted version'):
            Builder(source, destination, 'https://example.test/', 'preview')
        self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
