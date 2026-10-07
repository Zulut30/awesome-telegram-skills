"""Shared docs/ pages and their skill copies stay identical; an edited source without a sync fails."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/sync_skill_references.py'


def run(root: Path, *flags: str) -> tuple[int, dict]:
    done = subprocess.run([sys.executable, str(SCRIPT), '--root', str(root), *flags], capture_output=True,
                          text=True, encoding='utf-8', timeout=60)
    return done.returncode, json.loads(done.stdout)


class SkillReferenceSyncTests(unittest.TestCase):
    def test_repository_copies_match_their_sources(self):
        code, report = run(ROOT, '--check')
        self.assertEqual((code, report['drift'], report['problems']), (0, [], []))
        self.assertGreaterEqual(report['copies'], 35)

    def test_edit_without_sync_fails_and_sync_repairs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'docs').mkdir()
            (root / 'catalog').mkdir()
            (root / '.agents/skills/telegram-a/references').mkdir(parents=True)
            (root / 'docs/page.md').write_bytes(b'# Page\r\n\r\nText.\r\n')
            copy = root / '.agents/skills/telegram-a/references/page.md'
            (root / 'catalog/skill-references.json').write_text(json.dumps(
                {'copies': {'docs/page.md': ['.agents/skills/telegram-a/references/page.md']}}), encoding='utf-8')
            self.assertEqual(run(root, '--check')[0], 1, 'a missing copy is drift')
            self.assertEqual(run(root)[0], 0)
            self.assertEqual(copy.read_bytes(), b'# Page\r\n\r\nText.\r\n', 'bytes, line endings included')
            (root / 'docs/page.md').write_bytes(b'# Page\n\nEdited.\n')
            code, report = run(root, '--check')
            self.assertEqual((code, report['drift']), (1, ['.agents/skills/telegram-a/references/page.md']))
            self.assertEqual(run(root)[0], 0)
            self.assertEqual(run(root, '--check')[0], 0)
            (root / '.agents/skills/telegram-a/references/other.md').write_text('# Other\n', encoding='utf-8')
            (root / 'docs/other.md').write_text('# Other\n', encoding='utf-8')
            code, report = run(root, '--check')
            self.assertEqual(code, 1)
            self.assertIn('not in catalog/skill-references.json', report['problems'][0])

    def test_example_readme_drives_its_docs_mirror_and_skill_copies(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for part in ('docs', 'catalog', 'examples/bot', '.agents/skills/telegram-a/references'):
                (root / part).mkdir(parents=True)
            (root / 'examples/bot/README.md').write_text('# Bot\n\nEdited at the README.\n', encoding='utf-8')
            (root / 'docs/bot.md').write_text('# Bot\n\nOld.\n', encoding='utf-8')
            (root / 'catalog/skill-references.json').write_text(json.dumps(
                {'mirrors': {'examples/bot/README.md': 'docs/bot.md'},
                 'copies': {'docs/bot.md': ['.agents/skills/telegram-a/references/bot.md']}}), encoding='utf-8')
            code, report = run(root, '--check')
            self.assertEqual((code, sorted(report['drift'])), (1, ['.agents/skills/telegram-a/references/bot.md', 'docs/bot.md']))
            self.assertEqual(run(root)[0], 0)
            for page in ('docs/bot.md', '.agents/skills/telegram-a/references/bot.md'):
                self.assertEqual((root / page).read_text(encoding='utf-8'), '# Bot\n\nEdited at the README.\n', page)
            (root / 'catalog/skill-references.json').write_text(json.dumps(
                {'mirrors': {'examples/bot/README.md': 'docs/missing.md'}, 'copies': {}}), encoding='utf-8')
            code, report = run(root, '--check')
            self.assertEqual(code, 1)
            self.assertIn('a mirror needs', report['problems'][0])


if __name__ == '__main__':
    unittest.main()
