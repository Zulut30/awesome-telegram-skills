"""The weekly Bot API watch compares index content, not the page hash, and describes what changed."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / '.agents/skills/telegram-bot-api/scripts/update_api_index.py'
DIFF = ROOT / 'scripts/diff_api_index.py'


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry(name: str, fields: list[str]) -> str:
    rows = ''.join(f'<tr><td>{field}</td><td>String</td><td>x</td></tr>' for field in fields)
    return (f'<h4><a class="anchor" name="{name.lower()}" href="#{name.lower()}"></a>{name}</h4><p>Text.</p>'
            f'<table><thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead><tbody>{rows}</tbody></table>')


def page(version: str = '10.3', extra: str = '', user=('id', 'is_bot', 'first_name')) -> str:
    return ('<html><body><h3>Recent changes</h3><p>Bot API ' + version + '</p>'
            + entry('getMe', []) + entry('sendMessage', ['chat_id', 'text']) + entry('User', list(user))
            + entry('InlineKeyboardButton', ['text', 'style']) + extra + '</body></html>')


class ApiWatchTests(unittest.TestCase):
    def setUp(self):
        self.updater, self.differ = load(UPDATER), load(DIFF)

    def test_rebuilt_page_with_the_same_api_is_not_a_change(self):
        old = self.updater.parse_index(page())
        rebuilt = self.updater.parse_index(page().replace('<p>Text.</p>', '<p>Text, reworded.</p>'))
        self.assertNotEqual(old['source_sha256'], rebuilt['source_sha256'], 'the hash changes on every rebuild')
        self.assertFalse(self.differ.diff(old, rebuilt)['changed'])
        reordered = self.updater.parse_index(page(user=('first_name', 'id', 'is_bot')))
        self.assertFalse(self.differ.diff(old, reordered)['changed'], 'table order is not an API change')

    def test_new_version_methods_types_and_fields_are_reported(self):
        old = self.updater.parse_index(page())
        new = self.updater.parse_index(page('10.4', entry('sendTestFeature', ['chat_id']) + entry('TestFeature', ['name']),
                                            user=('id', 'first_name', 'has_test_badge')))
        result = self.differ.diff(old, new)
        self.assertTrue(result['changed'])
        self.assertEqual(result['version'], {'old': '10.3', 'new': '10.4'})
        self.assertEqual((result['added_methods'], result['added_types']), (['sendTestFeature'], ['TestFeature']))
        self.assertEqual(result['changed_fields'], {'User': {'added': ['has_test_badge'], 'removed': ['is_bot']}})
        body = self.differ.markdown(result, 'https://core.telegram.org/bots/api')
        for text in ('10.3 → 10.4', '`sendTestFeature`', '`TestFeature`', 'добавлены `has_test_badge`', 'удалены `is_bot`'):
            self.assertIn(text, body)
        self.assertIn(result['digest'], self.differ.title(result))
        removed = self.differ.diff(new, old)
        self.assertEqual((removed['removed_methods'], removed['removed_types']), (['sendTestFeature'], ['TestFeature']))
        self.assertNotEqual(removed['digest'], result['digest'], 'each distinct change gets its own issue')

    def test_command_line_writes_issue_body_and_github_outputs_only_for_a_change(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for name, html in (('old', page()), ('same', page().replace('Text.', 'Other.')), ('new', page('10.4'))):
                (folder / f'{name}.html').write_text(html, encoding='utf-8')
                subprocess.run([sys.executable, str(UPDATER), '--html-file', str(folder / f'{name}.html'),
                                '--output', str(folder / f'{name}.json')], check=True, capture_output=True)
            for name, changed in (('same', 'false'), ('new', 'true')):
                with self.subTest(name):
                    body, output = folder / f'{name}.md', folder / f'{name}.out'
                    done = subprocess.run([sys.executable, str(DIFF), str(folder / 'old.json'), str(folder / f'{name}.json'),
                                           '--markdown', str(body), '--github-output', str(output)],
                                          capture_output=True, text=True, encoding='utf-8', check=True)
                    self.assertEqual(json.loads(done.stdout)['changed'], changed == 'true')
                    self.assertIn(f'changed={changed}\n', output.read_text(encoding='utf-8'))
                    self.assertEqual(body.exists(), changed == 'true')

    def test_committed_index_matches_itself_and_workflow_compares_content(self):
        index = json.loads((ROOT / '.agents/skills/telegram-bot-api/references/api-index.json').read_text(encoding='utf-8'))
        later = {**index, 'source_sha256': '0' * 64, 'retrieved_at': '2099-01-01T00:00:00+00:00'}
        self.assertFalse(self.differ.diff(index, later)['changed'])
        workflow = (ROOT / '.github/workflows/telegram-docs-watch.yml').read_text(encoding='utf-8')
        for text in ("cron: '17 6 * * 1'", 'issues: write', 'update_api_index.py', 'diff_api_index.py',
                     "steps.diff.outputs.changed == 'true'", 'gh issue create'):
            self.assertIn(text, workflow)
        self.assertNotIn('source_sha256', workflow)


if __name__ == '__main__':
    unittest.main()
