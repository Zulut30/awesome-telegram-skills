"""The repository is a Claude Code plugin marketplace whose plugin is the canonical skills tree."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ClaudeMarketplaceTests(unittest.TestCase):
    def test_marketplace_points_at_canonical_skills_without_copies(self):
        manifest = json.loads((ROOT / '.claude-plugin/marketplace.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['name'], 'awesome-telegram-skills')
        self.assertTrue(manifest['owner']['name'])
        (plugin,) = manifest['plugins']
        self.assertEqual(plugin['name'], 'telegram-skills')
        self.assertNotRegex(plugin['name'], r'^(claude|anthropic|anthropics|cc-plugin)-')
        self.assertEqual(plugin['source'], './.agents')
        self.assertNotIn('..', plugin['source'])
        root = (ROOT / plugin['source']).resolve()
        self.assertFalse((root / '.claude-plugin').exists(), 'no manifest: Claude Code scans the default skills/ layout')
        skills = sorted(path.parent.name for path in (root / 'skills').glob('*/SKILL.md'))
        self.assertEqual(len(skills), 41)
        self.assertRegex(plugin['description'], rf'^{len(skills)} skills')
        for name in skills:
            frontmatter = (root / 'skills' / name / 'SKILL.md').read_text(encoding='utf-8').split('---')[1]
            self.assertIn(f'name: {name}\n', frontmatter)

    def test_documented_install_command_matches_manifest(self):
        manifest = json.loads((ROOT / '.claude-plugin/marketplace.json').read_text(encoding='utf-8'))
        command = (f"claude plugin marketplace add Zulut30/awesome-telegram-skills && "
                   f"claude plugin install {manifest['plugins'][0]['name']}@{manifest['name']}")
        gemini = 'gemini skills install https://github.com/Zulut30/awesome-telegram-skills.git --path .agents/skills'
        self.assertTrue((ROOT / '.agents/skills').is_dir())
        for page in ('README.md', 'README.en.md', 'docs/start/ai-agent.md'):
            text = (ROOT / page).read_text(encoding='utf-8')
            self.assertIn(command, text, page)
            self.assertIn(gemini, text, page)


if __name__ == '__main__':
    unittest.main()
