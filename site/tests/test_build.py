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
from build_docs_site import Builder, source_files, SITE_URL
from verify_docs_site import verify


class DocumentationOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original = Path(os.environ.get('DOCS_SOURCE', ROOT)).resolve()
        cls.temporary = TemporaryDirectory(prefix='telegram-documentation-operations-')
        cls.base = Path(cls.temporary.name).resolve()
        # A frozen owned input prevents another developer/agent's edits from changing a --check fixture mid-run.
        cls.source = cls.base / 'source'
        for file in source_files(original):
            target = cls.source / file.relative_to(original)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, target)
        cls.site = cls.base / 'site'
        cls.manifest = Builder(cls.source, cls.site, 'https://zulut30.github.io/awesome-telegram-skills/', 'preview', preview=True).build()

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
        # The gate row names exact models: an alias such as haiku moves to a new model with a CLI update.
        self.assertRegex(page, r'Выбор скиллов, после сопоставления с описаниями</td><td>claude-[a-z]+-\d+-\d+: \d')
        self.assertIn('Выбор скиллов сразу, только имя (без порога)', page)
        self.assertRegex(page, r'Методы Bot API [0-9.]+ с рецептом</td><td>\d+ из \d+')

    def test_check_rebuild_keeps_existing_output(self):
        before = (self.site / 'index.html').read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_docs_site.py'), '--source', str(self.source), '--output', str(self.site), '--check', '--preview'], capture_output=True, text=True, timeout=90)
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
        check = subprocess.run([sys.executable, str(ROOT / 'scripts/build_docs_site.py'), '--source', str(self.source), '--output', str(site), '--check', '--preview'], capture_output=True, text=True, timeout=90)
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


class PreviewAndPublicationGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory(prefix='telegram-docs-mode-gates-')
        cls.base = Path(cls.temporary.name).resolve()
        cls.original = Path(os.environ.get('DOCS_SOURCE', ROOT)).resolve()
        cls.original_history = (cls.original / 'docs/acceptance-history.json').read_bytes()
        cls.unaccepted = cls.base / 'unaccepted-source'
        for file in source_files(cls.original):
            target = cls.unaccepted / file.relative_to(cls.original)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, target)
        cls.version = json.loads((cls.unaccepted / 'components.json').read_text(encoding='utf-8'))['library_version']
        history_path = cls.unaccepted / 'docs/acceptance-history.json'
        history = json.loads(history_path.read_text(encoding='utf-8'))
        # Synthetic acceptance exists only inside the owned temporary fixture, never the repository.
        template = dict(next(item for item in history['reports'] if item['passed'] and item['stages']))
        for item in history['reports']:
            if item['version'] == cls.version:
                item['passed'] = False
        history_path.write_text(json.dumps(history), encoding='utf-8')
        cls.accepted = cls.base / 'accepted-source'
        shutil.copytree(cls.unaccepted, cls.accepted)
        accepted_history = json.loads((cls.accepted / 'docs/acceptance-history.json').read_text(encoding='utf-8'))
        accepted_history['reports'] = [item for item in accepted_history['reports'] if item['version'] != cls.version]
        accepted_history['reports'].append(template | {'version': cls.version, 'passed': True})
        (cls.accepted / 'docs/acceptance-history.json').write_text(json.dumps(accepted_history), encoding='utf-8')
        cls.preview_site = cls.base / 'preview-site'
        cls.preview_manifest = Builder(cls.unaccepted, cls.preview_site, SITE_URL, 'preview', preview=True).build()
        cls.production_site = cls.base / 'production-site'
        # The revision name "preview" is intentionally unrelated to the explicit build mode.
        cls.production_manifest = Builder(cls.accepted, cls.production_site, SITE_URL, 'preview').build()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def fingerprints(self, directory):
        return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in directory.rglob('*') if p.is_file()}

    def check(self, source, site, *, preview):
        command = [sys.executable, str(ROOT / 'scripts/build_docs_site.py'), '--source', str(source), '--output', str(site), '--check']
        if preview:
            command.append('--preview')
        return subprocess.run(command, capture_output=True, text=True, timeout=90)

    def test_preview_marks_every_page_and_does_not_forge_repository_acceptance(self):
        self.assertEqual(self.preview_manifest['mode'], 'preview')
        self.assertFalse(self.preview_manifest['accepted_version'])
        for route in self.preview_manifest['pages']:
            with self.subTest(route=route):
                page = (self.preview_site / route).read_text(encoding='utf-8')
                self.assertTrue('data-build-mode="preview"' in page, 'missing preview notice')
                self.assertTrue('content="noindex,nofollow"' in page, 'missing noindex metadata')
                self.assertTrue('режим разработки' in page, 'missing visible development label')
        home = (self.preview_site / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn(f'<strong>Принятая версия {self.version}', home)
        self.assertIn('Предварительная версия разработки', (self.preview_site / 'llms.txt').read_text(encoding='utf-8'))
        self.assertEqual((self.preview_site / 'robots.txt').read_text(), 'User-agent: *\nDisallow: /\n')
        self.assertEqual((self.original / 'docs/acceptance-history.json').read_bytes(), self.original_history)

    def test_production_default_refuses_unaccepted_source_before_any_output(self):
        destination = self.base / 'refused-production'
        before = self.fingerprints(self.unaccepted)
        with self.assertRaisesRegex(ValueError, 'accepted version'):
            Builder(self.unaccepted, destination, SITE_URL, 'preview')
        self.assertFalse(destination.exists())
        self.assertEqual(self.fingerprints(self.unaccepted), before)
        with self.assertRaisesRegex(ValueError, 'boolean'):
            Builder(self.unaccepted, destination, SITE_URL, 'preview', preview='true')

    def test_production_acceptance_does_not_inherit_preview_from_revision_name(self):
        self.assertEqual(self.production_manifest['mode'], 'production')
        self.assertTrue(self.production_manifest['accepted_version'])
        for route in self.production_manifest['pages']:
            with self.subTest(route=route):
                page = (self.production_site / route).read_text(encoding='utf-8')
                self.assertFalse('data-build-mode="preview"' in page, 'production contains preview notice')
                self.assertFalse('name="robots" content="noindex,nofollow"' in page, 'production contains preview metadata')
        self.assertIn('Allow: /', (self.production_site / 'robots.txt').read_text())

    def test_preview_check_matches_explicit_mode_and_preserves_files_on_mismatch(self):
        before = self.fingerprints(self.preview_site)
        matched = self.check(self.unaccepted, self.preview_site, preview=True)
        self.assertEqual(matched.returncode, 0, matched.stderr)
        mismatch = self.check(self.unaccepted, self.preview_site, preview=False)
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn('build mode differs', mismatch.stderr)
        self.assertEqual(self.fingerprints(self.preview_site), before)

    def test_production_check_rejects_preview_mode_without_repair(self):
        before = self.fingerprints(self.production_site)
        matched = self.check(self.accepted, self.production_site, preview=False)
        self.assertEqual(matched.returncode, 0, matched.stderr)
        mismatch = self.check(self.accepted, self.production_site, preview=True)
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn('build mode differs', mismatch.stderr)
        self.assertEqual(self.fingerprints(self.production_site), before)

    def test_preview_keeps_version_and_missing_link_validation(self):
        source = self.base / 'invalid-source'
        source.mkdir()
        for name in ('components.json', 'catalog/api-reference-index.json', 'catalog/api-reference.json', 'catalog/recipe-gallery.json', 'packages/python/pyproject.toml', 'packages/typescript/package.json', 'docs/acceptance-history.json', 'docs/navigation.json'):
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.unaccepted / name, target)
        document = source / 'docs/broken.md'
        document.write_text('# Проверка\n\n[Отсутствующий файл](missing-file.md)\n', encoding='utf-8')
        builder = Builder(source, self.base / 'broken-preview', SITE_URL, 'preview', preview=True)
        with self.assertRaisesRegex(ValueError, 'unavailable document link'):
            builder.markdown_page('docs/broken.md')
        package = source / 'packages/typescript/package.json'
        data = json.loads(package.read_text(encoding='utf-8'));data['version'] = '0.0.0'
        package.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'versions disagree'):
            Builder(source, self.base / 'mismatched-preview', SITE_URL, 'preview', preview=True)
        self.assertFalse((self.base / 'broken-preview').exists())
        self.assertFalse((self.base / 'mismatched-preview').exists())

    def test_pages_workflow_uses_only_accepted_production_build(self):
        import yaml
        workflow = yaml.safe_load((ROOT / '.github/workflows/docs-site.yml').read_text(encoding='utf-8'))
        steps = workflow['jobs']['build']['steps']
        builds = [step for step in steps if 'build_docs_site.py' in step.get('run', '')]
        self.assertEqual(len(builds), 2)
        preview = next(step for step in builds if '--preview' in step['run'])
        production = next(step for step in builds if '--preview' not in step['run'])
        self.assertIn('!inputs.pages-artifact', preview['if'])
        self.assertEqual(production['if'], 'inputs.pages-artifact')
        uploads = [step for step in steps if 'upload-pages-artifact@' in step.get('uses', '')]
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0]['if'], 'inputs.pages-artifact')


if __name__ == '__main__':
    unittest.main()
