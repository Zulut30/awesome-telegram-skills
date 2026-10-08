"""The single parameterized verifier of copied skill recipes: table, refusals and callers (no SDK needed)."""

import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / '.agents/skills/telegram-code-patterns'
spec = importlib.util.spec_from_file_location('verify_copied_recipe', ROOT / 'scripts/verify_copied_recipe.py')
verifier = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = verifier  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(verifier)
COMPOSITIONS = {name: recipe for name, recipe in verifier.RECIPES.items() if isinstance(recipe, verifier.Composition)}


class CopiedRecipeTests(unittest.TestCase):
    def test_one_script_replaces_the_per_recipe_verifiers(self):
        self.assertEqual(sorted(path.name for path in (ROOT / 'scripts').glob('verify_*_recipe.py')), ['verify_copied_recipe.py'])
        self.assertEqual(set(verifier.RECIPES), {'developer', 'dialog', 'dialog-restart', 'inline-search', 'keyboard', 'media',
                                                 'message', 'platform', 'poll', 'profile'})

    def test_every_composition_has_its_guide_offline_scenario_and_reviewed_source(self):
        for name, recipe in COMPOSITIONS.items():
            with self.subTest(name):
                guide = SKILL / 'references' / recipe.guide
                self.assertEqual(len(verifier.blocks_of(guide)), 1)
                self.assertTrue(recipe.offline.is_file(), recipe.offline)
                # composition() checks the block count and, for reviewed recipes, byte equality with examples/python.
                source = recipe.composition(guide)
                if recipe.reviewed:
                    self.assertEqual(source, (ROOT / 'examples/python' / f'{recipe.module}.py').read_text(encoding='utf-8'))

    def test_missing_duplicate_and_tampered_blocks_are_refused_before_execution(self):
        for name, recipe in COMPOSITIONS.items():
            text = (SKILL / 'references' / recipe.guide).read_text(encoding='utf-8')
            source = verifier.blocks_of(SKILL / 'references' / recipe.guide)[0]
            broken = {'missing': text.replace('```python\n' + source + '```', 'No composition'),
                      'duplicate': text + '\n```python\n' + source + '```\n'}
            if recipe.reviewed:
                broken['tampered'] = text.replace(source, 'raise RuntimeError("must not run")\n' + source)
            for case, document in broken.items():
                with self.subTest(recipe=name, case=case), tempfile.TemporaryDirectory() as folder:
                    copied = Path(folder) / recipe.guide
                    copied.write_text(document, encoding='utf-8')
                    with self.assertRaises(ValueError):
                        recipe.composition(copied)
                    self.assertEqual(copied.read_text(encoding='utf-8'), document)

    def test_package_verifier_runs_every_recipe_through_the_one_script(self):
        text = (ROOT / 'scripts/verify_pattern_packages.py').read_text(encoding='utf-8')
        self.assertIn("ROOT / 'scripts/verify_copied_recipe.py'), name, str(copied_skill)", text)
        called = set()
        for group in re.findall(r"for name in \(([^)]*)\):\n\s+portable_recipe\(name, sdk\)", text):
            called.update(re.findall(r"'([a-z-]+)'", group))
        called.update(re.findall(r"portable_recipe\('([a-z-]+)', core\)", text))
        self.assertEqual(called, set(verifier.RECIPES))


if __name__ == '__main__':
    unittest.main()
