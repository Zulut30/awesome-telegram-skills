"""Documentation structure: four sections with goals, a short sidebar and internal material kept apart."""

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_docs_map', ROOT / 'scripts/build_docs_map.py')
docs_map = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = docs_map
spec.loader.exec_module(docs_map)
MANIFEST = json.loads((ROOT / 'docs/navigation.json').read_text(encoding='utf-8'))


class DocsStructureTests(unittest.TestCase):
    def test_repository_structure_has_no_problems_and_the_map_is_current(self):
        self.assertEqual(docs_map.problems(MANIFEST, ROOT), [])
        self.assertEqual((ROOT / 'docs/README.md').read_text(encoding='utf-8'), docs_map.render(MANIFEST))
        entries = [entry for section in MANIFEST['sections'] for entry in section['pages']]
        self.assertLessEqual(sum(1 for entry in entries if entry.get('nav')), 25)

    def test_internal_material_lives_only_in_docs_internal(self):
        internal = {path.name for path in (ROOT / 'docs/internal').iterdir()}
        for name in ('excellence-plan-100.md', 'library-roadmap-100.md', 'skill-quality-audit.md', 'verification.md'):
            with self.subTest(name):
                self.assertIn(name, internal)
                self.assertFalse((ROOT / 'docs' / name).exists())
        index = (ROOT / 'docs/internal/README.md').read_text(encoding='utf-8')
        for name in internal - {'README.md'}:
            with self.subTest(listed=name):
                self.assertIn(f']({name})', index)

    def test_each_rule_reports_its_violation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'docs/internal').mkdir(parents=True)
            for entry in (entry for section in MANIFEST['sections'] for entry in section['pages']):
                target = root / entry['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('# page\n', encoding='utf-8')
            self.assertEqual(docs_map.problems(MANIFEST, root), [])
            (root / 'docs/orphan.md').write_text('# orphan\n', encoding='utf-8')
            self.assertIn('docs/orphan.md: user page without a section and goal (or move it to docs/internal)',
                          docs_map.problems(MANIFEST, root))
            (root / 'docs/orphan.md').unlink()
            (root / 'docs/internal/plan.md').write_text('# plan\n', encoding='utf-8')
            self.assertEqual(docs_map.problems(MANIFEST, root), [])
            changed = json.loads(json.dumps(MANIFEST))
            pages = changed['sections'][1]['pages']
            for entry in pages:
                entry['nav'] = True
            pages.append({'title': 'План', 'goal': 'Посмотреть внутренний план работ проекта.', 'path': 'docs/internal/plan.md'})
            pages.append(dict(pages[0]))
            changed['sections'][0]['pages'][2]['goal'] = 'Коротко'
            found = docs_map.problems(changed, root)
            self.assertIn('docs/internal/plan.md: internal material must not be listed', found)
            self.assertIn(f"{pages[0]['path']}: listed more than once", found)
            self.assertIn(f"{changed['sections'][0]['pages'][2]['path']}: needs a title and a one-sentence goal", found)
            self.assertTrue(any(problem.endswith('sidebar pages, at most 25') for problem in found))
            shutil.rmtree(root / 'docs/internal')


if __name__ == '__main__':
    unittest.main()
