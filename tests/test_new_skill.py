"""The skill scaffold: the validator rejects it until every marker is replaced, then accepts it."""

import datetime as dt
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'scripts/{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scaffold = load('new_skill')
installer = load('install_skills')
try:
    validator = load('validate_skills')
except SystemExit:  # PyYAML missing
    validator = None


class NewSkillTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        shutil.copyfile(ROOT / 'LICENSE', self.root / 'LICENSE')
        shutil.copy(ROOT / 'components.json', self.root / 'components.json')
        shutil.copytree(ROOT / '.agents/skills/telegram-bot-api', self.root / '.agents/skills/telegram-bot-api')

    def create(self):
        return scaffold.create(self.root, 'telegram-example-polls', 'Опросы', 'Опросы и викторины в чатах Telegram',
                               'telegram-bot-api', dt.date(2026, 10, 7))

    def test_scaffold_fails_validation_until_filled_and_then_passes(self):
        if validator is None:
            self.skipTest('PyYAML is not installed')
        files = self.create()
        skill = files[0].read_text(encoding='utf-8')
        version = json.loads((ROOT / 'components.json').read_text(encoding='utf-8'))['library_version']
        self.assertIn(f'version: "{version}"', skill)
        _, errors = validator.validate(self.root)
        self.assertEqual([error.split(': ', 1)[1] for error in errors if 'telegram-example-polls' in error], ['unfinished scaffold'])
        for path in files:
            text = path.read_text(encoding='utf-8')
            text = text.replace('- [TODO: ошибка и как ее избежать.]', '- Повтор отправки после неизвестного ответа сервера.')
            text = re.sub(r'\[TODO: [^\]]*\]', 'Опрос в чате с подсчетом голосов', text)
            path.write_text(text, encoding='utf-8', newline='\n')
        _, errors = validator.validate(self.root)
        self.assertEqual([error for error in errors if 'telegram-example-polls' in error], [])

    def test_bad_arguments_are_refused_without_writing(self):
        cases = {'name must look like': dict(name='Example'), '--not-for must name another existing skill': dict(not_for='telegram-none'),
                 '--short must be 25-64 characters': dict(short='коротко'), 'may not contain quotes': dict(title='Опросы "Pro"')}
        for message, change in cases.items():
            arguments = dict(name='telegram-example-polls', title='Опросы', short='Опросы и викторины в чатах Telegram', not_for='telegram-bot-api')
            arguments.update(change)
            with self.subTest(message), self.assertRaisesRegex(ValueError, message):
                scaffold.create(self.root, arguments['name'], arguments['title'], arguments['short'], arguments['not_for'], dt.date(2026, 10, 7))
            self.assertFalse((self.root / '.agents/skills/telegram-example-polls').exists())
        self.create()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.create()

    def test_guide_lists_every_registration_step(self):
        guide = (ROOT / 'docs/contributing-skills.md').read_text(encoding='utf-8')
        for needle in ('scripts/new_skill.py', 'README.en.md', 'docs/sources.md', 'evaluations/skill-value.json',
                       'evaluations/skill-selection.json', 'tests.test_current_numbers', 'add_terms_lines.py', 'components.json'):
            with self.subTest(needle):
                self.assertIn(needle, guide)
        self.assertIn('docs/contributing-skills.md', scaffold.NEXT_STEPS)

    def test_created_skill_keeps_full_notice_when_installed_alone_and_conflicts_preserve_it(self):
        tool = self.root / 'scripts/new_skill.py'
        tool.parent.mkdir()
        shutil.copyfile(ROOT / 'scripts/new_skill.py', tool)
        command = [sys.executable, str(tool), 'telegram-example-polls', '--title', 'Опросы',
                   '--short', 'Опросы и викторины в чатах Telegram', '--not-for', 'telegram-bot-api']
        created = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(created.returncode, 0, created.stderr)
        files = [self.root / name for name in json.loads(created.stdout)['created']]
        self.assertEqual(len(files), 3)
        source = self.root / '.agents/skills/telegram-example-polls'
        notice = (self.root / 'LICENSE').read_bytes()
        self.assertEqual(files[-1], source / 'LICENSE')
        self.assertEqual((source / 'LICENSE').read_bytes(), notice)
        project = self.root / 'consumer project'
        project.mkdir()
        marker = project / 'owner.txt'
        marker.write_bytes(b'caller-owned')
        installed = installer.install_skills(self.root / '.agents/skills', project, ['telegram-example-polls'])
        self.assertEqual(len(installed), 1)
        self.assertEqual((installed[0] / 'LICENSE').read_bytes(), notice)
        self.assertFalse((installed[0].parent / 'telegram-bot-api').exists())
        before = {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.create()
        with self.assertRaises(installer.InstallError):
            installer.install_skills(self.root / '.agents/skills', project, ['telegram-example-polls'])
        self.assertEqual(before, {p.relative_to(project): p.read_bytes() for p in project.rglob('*') if p.is_file()})
        self.assertEqual(marker.read_bytes(), b'caller-owned')

    def test_missing_or_incomplete_notice_is_refused_before_any_target_write(self):
        canonical = (ROOT / 'LICENSE').read_bytes()
        license_path = self.root / 'LICENSE'
        for data in (None, b'MIT License\n\nCopyright (c) Fixture\n', b'Proprietary notice',
                     canonical.replace(b'Permission is hereby granted', b'Permission is NOT granted'), b'\xff\xfe'):
            with self.subTest(data=data):
                if data is None:
                    license_path.unlink()
                else:
                    license_path.write_bytes(data)
                before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
                with self.assertRaisesRegex(ValueError, 'complete canonical MIT LICENSE'):
                    self.create()
                self.assertFalse((self.root / '.agents/skills/telegram-example-polls').exists())
                self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
                license_path.write_bytes(canonical)
        tool = self.root / 'scripts/new_skill.py'
        tool.parent.mkdir()
        shutil.copyfile(ROOT / 'scripts/new_skill.py', tool)
        license_path.write_bytes(b'MIT License\n\nCopyright (c) Fixture\n')
        refused = subprocess.run([sys.executable, str(tool), 'telegram-example-polls', '--title', 'Опросы',
                                  '--short', 'Опросы и викторины в чатах Telegram', '--not-for', 'telegram-bot-api'],
                                 capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stdout, '')
        self.assertIn('complete canonical MIT LICENSE', refused.stderr)
        self.assertNotIn('Traceback', refused.stderr)
        self.assertFalse((self.root / '.agents/skills/telegram-example-polls').exists())

    def test_linked_notice_is_not_followed(self):
        license_path = self.root / 'LICENSE'
        license_path.unlink()
        try:
            license_path.symlink_to(ROOT / 'LICENSE')
        except (OSError, NotImplementedError):
            self.skipTest('Filesystem does not allow this user to create symlinks')
        with self.assertRaisesRegex(ValueError, 'complete canonical MIT LICENSE'):
            self.create()
        self.assertFalse((self.root / '.agents/skills/telegram-example-polls').exists())


if __name__ == '__main__':
    unittest.main()
