"""Лицензия MIT объявлена согласованно: файл, пакеты, примеры и каждый скилл."""
import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LicenseTests(unittest.TestCase):
    def test_license_file_copies_and_manifests_agree(self):
        text = (ROOT / 'LICENSE').read_bytes()
        self.assertTrue(text.startswith(b'MIT License'))
        for copy in ('packages/python/LICENSE', 'packages/typescript/LICENSE'):
            self.assertEqual((ROOT / copy).read_bytes(), text, copy)
        python = tomllib.loads((ROOT / 'packages/python/pyproject.toml').read_text(encoding='utf-8'))
        self.assertEqual((python['project']['license'], python['project']['license-files']), ('MIT', ['LICENSE']))
        for example in ('group-bot', 'service-bot', 'shop'):
            data = tomllib.loads((ROOT / f'examples/{example}/pyproject.toml').read_text(encoding='utf-8'))
            self.assertEqual(data['project']['license'], 'MIT', example)
        for manifest in ('package.json', 'packages/typescript/package.json', 'examples/mini-app/package.json',
                         'examples/shop/frontend/package.json'):
            self.assertEqual(json.loads((ROOT / manifest).read_text(encoding='utf-8'))['license'], 'MIT', manifest)
        self.assertIn('LICENSE', json.loads((ROOT / 'packages/typescript/package.json').read_text(encoding='utf-8'))['files'])

    def test_every_skill_declares_the_license(self):
        skills = sorted((ROOT / '.agents/skills').glob('*/SKILL.md'))
        self.assertEqual(len(skills), 41)
        for skill in skills:
            front = skill.read_text(encoding='utf-8').split('---', 2)[1]
            self.assertRegex(front, re.compile(r'^license: MIT\r?$', re.M), skill.parent.name)


if __name__ == '__main__':
    unittest.main()
