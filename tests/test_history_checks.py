"""Commit messages say what, why and how it was checked; CHANGELOG sections match the version tags."""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'scripts/{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


commits = load('check_commit_messages')
changelog = load('check_changelog')
GOOD = '''dialog: keep the operation id after a restart

После перезапуска бот выдавал новый ID операции, и повторное нажатие создавало вторую заявку.

Проверено: python -m unittest discover -s tests (163 OK)

Co-Authored-By: Someone <someone@example.invalid>
'''


class CommitMessageTests(unittest.TestCase):
    def test_template_example_and_contributing_example_pass(self):
        self.assertEqual(commits.problems(GOOD), [])
        contributing = (ROOT / 'CONTRIBUTING.md').read_text(encoding='utf-8')
        example = contributing.split('```text\n', 1)[1].split('```', 1)[0]
        self.assertEqual(commits.problems(example), [])
        self.assertTrue((ROOT / '.gitmessage').is_file())

    def test_each_rule_reports_its_violation(self):
        cases = {
            'subject is 80 characters, at most 72': GOOD.replace('dialog: keep the operation id after a restart', 'x' * 80),
            'subject ends with a period': GOOD.replace('after a restart', 'after a restart.'),
            'fixup, squash or WIP commit: squash it before review': GOOD.replace('dialog:', 'fixup! dialog:'),
            'the second line must be empty': GOOD.replace('restart\n\n', 'restart\nbody\n', 1),
            'the body must say what changed and why (at least one sentence)': 'area: change\n\nПроверено: tests\n',
            'the body needs a "Проверено:" (or "Verified:") line naming the checks and their results':
                GOOD.replace('Проверено: python -m unittest discover -s tests (163 OK)\n', ''),
            'line 3 is 120 characters, at most 100': GOOD.replace('После', 'я' * 120 + '\nПосле', 1),
        }
        for message, text in cases.items():
            with self.subTest(message):
                self.assertIn(message, commits.problems(text))
        self.assertEqual(commits.problems(GOOD.replace('Проверено:', 'Verified:')), [])


class ChangelogTests(unittest.TestCase):
    TEXT = '## Не выпущено\n\n- next\n\n## 1.3.0 — note\n\n- c\n\n## 1.2.0\n\n- b\n\n## 1.1.0\n\n- a\n'

    def test_current_changelog_structure_and_package_version(self):
        text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
        versions, found = changelog.sections(text)
        self.assertEqual(found, [])
        self.assertIn('0.24.0', versions)
        self.assertEqual(changelog.problems(text, [], '0.24.0'), [])

    def test_tags_and_sections_must_match(self):
        self.assertEqual(changelog.problems(self.TEXT, ['v1.2.0', 'v1.3.0'], '1.3.0'), [])
        self.assertIn('tag v1.4.0 has no CHANGELOG section', changelog.problems(self.TEXT, ['v1.2.0', 'v1.3.0', 'v1.4.0'], '1.3.0'))
        self.assertIn('1.2.0: section without a v1.2.0 tag', changelog.problems(self.TEXT, ['v1.1.0', 'v1.3.0'], '1.3.0'))
        self.assertIn('v1.4.0: add a "## 1.4.0" section before releasing', changelog.problems(self.TEXT, [], '1.3.0', 'v1.4.0'))
        self.assertIn('package version 1.2.5 has no section and is not newer than 1.3.0', changelog.problems(self.TEXT, [], '1.2.5'))
        self.assertEqual(changelog.problems(self.TEXT, [], '1.4.0'), [])  # an unreleased next version

    def test_structure_rules(self):
        self.assertIn('the first section must be "## Не выпущено"', changelog.sections(self.TEXT.replace('## Не выпущено', '## Next'))[1])
        self.assertIn('1.2.0: more than one section', changelog.sections(self.TEXT + '\n## 1.2.0\n')[1])
        self.assertIn('version sections must go from newest to oldest', changelog.sections(self.TEXT + '\n## 1.5.0\n')[1])
        self.assertTrue(any('is not a version section' in problem for problem in changelog.sections(self.TEXT + '\n## Unreleased — 1.0\n')[1]))

    def test_release_workflow_refuses_a_tag_without_a_section(self):
        release = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
        self.assertIn('python scripts/check_changelog.py --tag "$tag"', release)
        checks = (ROOT / '.github/workflows/repository-checks.yml').read_text(encoding='utf-8')
        history = checks.split('\n  history:\n', 1)[1].split('\n  python-style:\n', 1)[0]
        self.assertIn('fetch-depth: 0', history)
        self.assertIn('python scripts/check_commit_messages.py --range "$BASE..$HEAD"', history)


if __name__ == '__main__':
    unittest.main()
