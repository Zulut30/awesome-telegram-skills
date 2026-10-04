"""Exercise documentation generator with isolated trees and export drift."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts import build_api_reference as generator


class ApiReferenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='api reference ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        source = generator.ROOT
        for relative in ['components.json', 'catalog/api-reference.json', 'packages/typescript/src/index.ts',
                         *['packages/python/src/telegram_patterns/' + name + '.py'
                           for name in ['__init__', 'aiogram', 'testing']]]:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)
        shutil.copytree(source / 'examples/api-reference', self.root / 'examples/api-reference')
        for relative in ['docs', '.agents/skills/telegram-code-patterns/references']:
            (self.root / relative).mkdir(parents=True)
        self.spec = self.root / 'catalog/api-reference.json'
        self.addCleanup(patch.stopall)
        patch.object(generator, 'ROOT', self.root).start()
        patch.object(generator, 'SPEC', self.spec).start()

    def generate(self, check=False):
        with patch.object(sys, 'argv', ['build_api_reference.py'] + (['--check'] if check else [])):
            return generator.main()

    def test_real_write_check_portability_and_stale_output_detection_preserve_owned_files(self):
        marker = self.root / 'docs/owned.md'
        marker.write_bytes(b'consumer notes\n')
        self.assertEqual(self.generate(), 0)
        self.assertEqual(self.generate(check=True), 0)
        for name in ['api-reference.md', 'api-reference-core.md', 'api-reference-bot.md', 'api-reference-typescript.md']:
            self.assertEqual((self.root / 'docs' / name).read_bytes(),
                             (self.root / '.agents/skills/telegram-code-patterns/references' / name).read_bytes())
        stale = self.root / 'docs/api-reference.md'
        stale.write_bytes(b'owned stale reference\n')
        with self.assertRaisesRegex(ValueError, 'output drift'): self.generate(check=True)
        self.assertEqual(stale.read_bytes(), b'owned stale reference\n')
        self.assertEqual(marker.read_bytes(), b'consumer notes\n')

    def test_new_export_and_missing_binding_cannot_silently_receive_documentation(self):
        source = self.root / 'packages/typescript/src/index.ts'
        original = source.read_text(encoding='utf-8')
        source.write_text(original + '\nexport { UndocumentedAPI } from "./future.js";\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Public export documentation drift'): generator.build()
        source.write_text(original, encoding='utf-8')
        example = self.root / 'examples/api-reference/python/core_identity.py'
        example.write_text(example.read_text(encoding='utf-8').replace('InvalidInitData,', ''), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'documented import'): generator.build()

    def test_limits_duplicates_and_outside_example_rejected_before_generation(self):
        original = json.loads(self.spec.read_text(encoding='utf-8'))
        for problem in ['limits', 'duplicate', 'outside']:
            with self.subTest(problem=problem):
                spec = json.loads(json.dumps(original))
                if problem == 'limits': spec['groups'][0]['limits'] = ' '
                if problem == 'duplicate': spec['groups'].append(spec['groups'][0])
                if problem == 'outside':
                    (self.root / 'owned.py').write_text('preserve = True\n', encoding='utf-8')
                    spec['groups'][0]['example'] = 'owned.py'
                self.spec.write_text(json.dumps(spec), encoding='utf-8')
                with self.assertRaises(ValueError): generator.build()
                self.assertFalse((self.root / 'docs/api-reference.md').exists())


if __name__ == '__main__': unittest.main()
