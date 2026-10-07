import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_capability_map as capability_map  # noqa: E402

SOURCES = ('catalog/capability-map.json', 'catalog/telegram-capabilities.json', 'components.json', 'catalog/recipe-gallery.json')


class CapabilityMapTests(unittest.TestCase):
    def copy(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix='capability map '))
        self.addCleanup(shutil.rmtree, root)
        for name in SOURCES:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, root / name)
        for skill in (ROOT / '.agents/skills').iterdir():
            if (skill / 'SKILL.md').is_file():
                (root / '.agents/skills' / skill.name).mkdir(parents=True)
                (root / '.agents/skills' / skill.name / 'SKILL.md').write_text('---\n---\n', encoding='utf-8')
        return root

    def edit(self, root: Path, name: str, change) -> None:
        data = json.loads((root / name).read_text(encoding='utf-8'))
        change(data)
        (root / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def test_page_is_current_and_every_method_is_mapped(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_capability_map.py'), '--check'],
                                capture_output=True, text=True, encoding='utf-8', check=True)
        summary = json.loads(result.stdout)
        telegram = json.loads((ROOT / 'catalog/telegram-capabilities.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['bot_api_methods'], len(telegram['bot_api']['methods']))
        self.assertEqual(summary['mini_app_methods'], len(telegram['mini_app']['methods']))
        page = (ROOT / 'docs/capability-map.md').read_text(encoding='utf-8')
        self.assertIn('| Эфемерные сообщения в группах | `telegram-groups` | `ephemeral-messages` | `demo-ephemeral` | SDK-запрос, Dispatcher | live |', page)
        self.assertIn(f'Без live-проверки: {summary["capabilities"]} из {summary["capabilities"]}', page)

    def test_new_telegram_method_or_unknown_id_fails(self):
        root = self.copy()
        self.edit(root, 'catalog/telegram-capabilities.json', lambda data: data['bot_api']['methods'].append({'name': 'sendHologram'}))
        with self.assertRaisesRegex(ValueError, 'sendHologram has no capability'):
            capability_map.build(root)
        root = self.copy()
        self.edit(root, 'catalog/capability-map.json', lambda data: data['areas'][0]['capabilities'][0]['recipes'].append('demo-missing'))
        with self.assertRaisesRegex(ValueError, 'unknown recipe demo-missing'):
            capability_map.build(root)

    def test_overlapping_patterns_fail(self):
        root = self.copy()

        def overlap(data):
            data['areas'][0]['capabilities'][1]['bot_api'] = '^(sendRichMessage|sendMessage)$'
        self.edit(root, 'catalog/capability-map.json', overlap)
        with self.assertRaisesRegex(ValueError, 'Bot API sendMessage: in text and rich-messages'):
            capability_map.build(root)

    def test_gaps_follow_the_catalogs(self):
        root = self.copy()

        def drop(data):
            data['areas'][0]['capabilities'][1]['components'] = []
            data['areas'][0]['capabilities'][1]['recipes'] = []
        self.edit(root, 'catalog/capability-map.json', drop)
        page, summary = capability_map.build(root)
        self.assertIn('| Rich-сообщения: блоки, таблицы, кнопки | `telegram-bot-api` | — | — | SDK-запрос | компонент, сценарий, live |', page)
        before = json.loads(subprocess.run([sys.executable, str(ROOT / 'scripts/build_capability_map.py'), '--check'],
                                           capture_output=True, text=True, encoding='utf-8', check=True).stdout)
        self.assertEqual(summary['with_component'], before['with_component'] - 1)


if __name__ == '__main__':
    unittest.main()
