"""Quarterly sources review: ages from every skill, parsers of the live sources and the quarterly workflow."""

import datetime as dt
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sources_review', ROOT / 'scripts/sources_review.py')
review = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = review
spec.loader.exec_module(review)


class SourcesReviewTests(unittest.TestCase):
    def test_every_skill_has_a_date_and_none_is_stale_today(self):
        rows = review.skill_ages(ROOT / '.agents/skills', dt.date(2026, 10, 7))
        self.assertEqual(len(rows), len(list((ROOT / '.agents/skills').glob('*/SKILL.md'))))
        self.assertTrue(all(row['checked'] for row in rows))
        self.assertFalse([row['skill'] for row in rows if row['stale']])
        later = review.skill_ages(ROOT / '.agents/skills', dt.date(2027, 1, 15))
        self.assertTrue(all(row['stale'] for row in later))

    def test_missing_or_old_dates_are_stale(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, line in (('telegram-a', 'Проверено: 2026-01-01, API\n'), ('telegram-b', 'Без даты\n')):
                (root / name).mkdir()
                (root / name / 'SKILL.md').write_text(f'# {name}\n\n## Источники\n\n{line}', encoding='utf-8')
            rows = {row['skill']: row for row in review.skill_ages(root, dt.date(2026, 10, 7))}
        self.assertEqual((rows['telegram-a']['age_days'], rows['telegram-a']['stale']), (279, True))
        self.assertEqual((rows['telegram-b']['checked'], rows['telegram-b']['stale']), (None, True))

    def test_live_source_parsers(self):
        changelog = '<p><strong>Bot API 10.3</strong></p> <p><strong>Bot API 10.2</strong></p> <p><strong>Bot API 9.6</strong></p>'
        self.assertEqual(review.latest_bot_api(changelog), '10.3')
        self.assertIsNone(review.latest_bot_api('<p>maintenance</p>'))
        self.assertEqual(review.pinned_aiogram('aiogram==3.31.0\npython-telegram-bot==22.5\n'), '3.31.0')
        self.assertTrue(review.crypto_pay_envelope(b'{"ok":false,"error":{"code":401,"name":"UNAUTHORIZED"}}'))
        self.assertFalse(review.crypto_pay_envelope(b'<html>blocked</html>'))
        self.assertFalse(review.crypto_pay_envelope(b'{"ok":true,"result":{}}'))

    def test_checklist_and_quarterly_workflow(self):
        report = {'date': '2026-10-07', 'skills': [{'skill': 'telegram-a', 'checked': '2026-01-01', 'age_days': 279, 'stale': True}],
                  'probes': {'bot_api': {'saved_index': '10.3', 'latest_in_changelog': '10.4', 'current': False},
                             'aiogram': {'pinned': '3.31.0', 'latest_on_pypi': '3.31.0', 'current': True},
                             'crypto_pay': {'hosts': {'pay.crypt.bot': {'status': 401, 'documented_envelope': True}}, 'reachable': True}}}
        text = review.markdown(report)
        self.assertIn('- Bot API: сохраненный индекс 10.3, в changelog 10.4 — нужна сверка.', text)
        self.assertIn('- [ ] `telegram-a` — проверено 2026-01-01', text)
        workflow = (ROOT / '.github/workflows/sources-review.yml').read_text(encoding='utf-8')
        self.assertIn("cron: '17 6 1 1,4,7,10 *'", workflow)
        self.assertIn('python scripts/sources_review.py', workflow)
        self.assertIn('gh issue create', workflow)
        self.assertIn('2026-10-07 — пункт 99, ежеквартальная сверка', (ROOT / 'docs/sources.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
