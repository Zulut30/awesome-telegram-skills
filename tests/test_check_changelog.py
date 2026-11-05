"""Canonical release history, numeric RC ordering and tag equality."""

import unittest

from scripts.check_changelog import problems, sections


class ReleaseChangelogTests(unittest.TestCase):
    def test_rc_order_is_numeric_and_final_is_newer_than_its_candidates(self):
        text = '## Не выпущено\n\n## 1.0.0\n\n## 1.0.0-rc.10\n\n## 1.0.0-rc.2\n\n## 0.24.0\n'
        self.assertEqual(sections(text), (['1.0.0', '1.0.0-rc.10', '1.0.0-rc.2', '0.24.0'], []))
        self.assertEqual(problems(text, ['v1.0.0', 'v1.0.0-rc.10', 'v1.0.0-rc.2'], '1.0.0'), [])
        wrong = '## Не выпущено\n\n## 1.0.0-rc.2\n\n## 1.0.0-rc.10\n'
        self.assertIn('version sections must go from newest to oldest', sections(wrong)[1])

    def test_python_manifest_form_matches_canonical_changelog_without_becoming_final(self):
        text = '## Не выпущено\n\n## 1.0.0-rc.1 — candidate\n\n## 0.24.0\n'
        self.assertEqual(problems(text, ['v1.0.0-rc.1'], '1.0.0rc1', 'v1.0.0-rc.1'), [])
        self.assertIn('v1.0.0: add a "## 1.0.0" section before releasing',
                      problems(text, [], '1.0.0rc1', 'v1.0.0'))
        self.assertIn('v1.0.0rc1: not a canonical release tag', problems(text, [], '1.0.0rc1', 'v1.0.0rc1'))

    def test_noncanonical_sections_are_not_accepted_as_numeric_release(self):
        for version in ['1.0.0rc1', '1.0.0-rc.01', '01.0.0', '1.0.0-beta.1', '1.0.0 ']:
            with self.subTest(version=version):
                versions, found = sections('## Не выпущено\n\n## ' + version + '\n')
                self.assertEqual(versions, [])
                self.assertTrue(any('not a version section' in error for error in found))


if __name__ == '__main__':
    unittest.main()
