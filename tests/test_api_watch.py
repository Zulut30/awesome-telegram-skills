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
MINI = ROOT / 'scripts/mini_app_index.py'
MINI_DIFF = ROOT / 'scripts/diff_mini_app_index.py'


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



def mini_table(heading: str, rows: list[tuple[str, str, str]], level: str = 'h4') -> str:
    body = ''.join(f'<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>' for a, b, c in rows)
    return (f'<{level}><a class="anchor" name="{heading.lower().replace(" ", "-")}"></a>{heading}</{level}>'
            f'<table><tr><th>Field</th><th>Type</th><th>Description</th></tr>{body}</table>')


def mini_page(extra_module: str = '', extra_event: tuple[str, str] | None = None) -> str:
    events = [('themeChanged', 'Occurs when the theme changes.', ''), ('viewportChanged', 'Occurs on resize.', '')]
    if extra_event:
        events.append((extra_event[0], extra_event[1], ''))
    return ('<html><body>'
            + mini_table('Initializing Mini Apps', [('version', 'String', 'The version.'), ('ready()', 'Function', 'Ready.'),
                                                    ('showPopup(params[, callback])', 'Function', 'Bot API 6.2+ A popup.')], 'h3')
            + mini_table('BackButton', [('show()', 'Function', 'Show.')])
            + mini_table('LocationManager', [('getLocation(callback)', 'Function', 'Location.')])
            + extra_module + mini_table('Events Available for Mini Apps', events, 'h3') + '</body></html>')


class MiniAppWatchTests(unittest.TestCase):
    def setUp(self):
        self.index, self.differ = load(MINI), load(MINI_DIFF)

    def test_new_module_method_and_event_are_reported_with_their_versions(self):
        old = self.index.mini_index(mini_page(), strict=False)
        self.assertEqual({item['path']: item['min_version'] for item in old['methods']},
                         {'ready': '6.0', 'showPopup': '6.2', 'BackButton.show': '6.1', 'LocationManager.getLocation': '8.0'})
        serverless = mini_table('Serverless', [('call(name[, input][, callback])', 'Function', 'Calls an endpoint.')])
        new_page = mini_page(serverless, ('endpointCalled', 'Bot API 10.4+ Occurs after a call.'))
        with self.assertRaisesRegex(ValueError, 'Unmapped Mini App module: Serverless'):
            self.index.mini_index(new_page)  # the catalog build refuses a module it cannot gate
        new = self.index.mini_index(new_page, strict=False)
        result = self.differ.diff(old, new)
        self.assertTrue(result['changed'])
        self.assertEqual(result['added_methods'], {'Serverless.call': None})
        self.assertEqual(result['added_events'], {'endpointCalled': '10.4'})
        body = self.differ.markdown(result, 'https://core.telegram.org/bots/webapps')
        for text in ('`Serverless.call` — версия в документации не указана', '`endpointCalled` — с версии 10.4'):
            self.assertIn(text, body)
        self.assertIn(result['digest'], self.differ.title(result))

    def test_same_api_on_a_rebuilt_page_is_not_a_change_but_a_new_gate_is(self):
        old = self.index.mini_index(mini_page(), strict=False)
        rebuilt = self.index.mini_index(mini_page().replace('Show.', 'Shows the button.'), strict=False, checked_date='2099-01-01')
        self.assertNotEqual(old['source_sha256'], rebuilt['source_sha256'])
        self.assertFalse(self.differ.diff(old, rebuilt)['changed'])
        gated = self.index.mini_index(mini_page().replace('Show.', 'Bot API 7.0+ Show.'), strict=False)
        self.assertEqual(self.differ.diff(old, gated)['changed_methods'], {'BackButton.show': {'old': '6.1', 'new': '7.0'}})

    def test_command_line_and_workflow(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for name, html in (('old', mini_page()), ('new', mini_page(extra_event=('newEvent', 'Occurs.')))):
                (folder / f'{name}.html').write_text(html, encoding='utf-8')
                subprocess.run([sys.executable, str(MINI), '--html-file', str(folder / f'{name}.html'),
                                '--output', str(folder / f'{name}.json')], check=True, capture_output=True)
            done = subprocess.run([sys.executable, str(MINI_DIFF), str(folder / 'old.json'), str(folder / 'new.json'),
                                   '--markdown', str(folder / 'issue.md'), '--github-output', str(folder / 'out')],
                                  capture_output=True, text=True, encoding='utf-8', check=True)
            self.assertEqual(json.loads(done.stdout)['added_events'], {'newEvent': '6.0'})
            self.assertIn('changed=true\n', (folder / 'out').read_text(encoding='utf-8'))
            self.assertIn('`newEvent`', (folder / 'issue.md').read_text(encoding='utf-8'))
        committed = json.loads((ROOT / 'catalog/mini-app-index.json').read_text(encoding='utf-8'))
        self.assertFalse(self.differ.diff(committed, {**committed, 'source_sha256': '0' * 64, 'checked_date': '2099-01-01'})['changed'])
        workflow = (ROOT / '.github/workflows/telegram-docs-watch.yml').read_text(encoding='utf-8')
        for text in ('scripts/mini_app_index.py --output', 'diff_mini_app_index.py catalog/mini-app-index.json'):
            self.assertIn(text, workflow)


if __name__ == '__main__':
    unittest.main()
