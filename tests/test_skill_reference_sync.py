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


if __name__ == '__main__':
    unittest.main()
