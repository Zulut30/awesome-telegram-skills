"""Showcase: only checked real projects with known skills and components, added through the issue form."""

import datetime as dt
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_showcase', ROOT / 'scripts/build_showcase.py')
showcase = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = showcase
spec.loader.exec_module(showcase)
CATALOG = json.loads((ROOT / 'catalog/showcase.json').read_text(encoding='utf-8'))
TODAY = dt.date(2026, 10, 7)
PROJECT = {'name': 'Запись в барбершоп', 'kind': 'bot', 'url': 'https://t.me/example_barber_bot', 'source': None,
           'description': 'Запись на стрижку с напоминанием за час до визита.', 'skills': ['telegram-bot-api'],
           'components': ['recipe-catalog'], 'issue': 12, 'added': '2026-10-06', 'checked_at': '2026-10-06'}


class ShowcaseTests(unittest.TestCase):
    def test_catalog_is_valid_and_the_page_is_current(self):
        self.assertEqual(showcase.problems(CATALOG, ROOT, TODAY), [])
        self.assertEqual((ROOT / 'docs/showcase.md').read_text(encoding='utf-8'), showcase.render(CATALOG))
        self.assertEqual(CATALOG['target'], 10)

    def test_a_checked_project_is_rendered_and_examples_are_not_counted(self):
        catalog = dict(CATALOG, projects=[PROJECT])
        self.assertEqual(showcase.problems(catalog, ROOT, TODAY), [])
        page = showcase.render(catalog)
        self.assertIn('Принято проектов: **1**', page)
        self.assertIn('| [Запись в барбершоп](https://t.me/example_barber_bot) | Бот |', page)
        self.assertIn('`telegram-bot-api`, `recipe-catalog` | 2026-10-06 |', page)
        self.assertIn('не считаются проектами витрины', page)

    def test_each_rule_reports_its_violation(self):
        cases = {
            'kind must be one of': dict(PROJECT, kind='game'),
            'url must be https://t.me/<bot> or another https link': dict(PROJECT, url='http://t.me/bot'),
            'source must be an https link or null': dict(PROJECT, source='ftp://code'),
            'description must be 20-200 characters': dict(PROJECT, description='Пишите на owner@example.com по любым вопросам'),
            'name at least one skill or component': dict(PROJECT, skills=[], components=[]),
            'unknown skill telegram-made-up': dict(PROJECT, skills=['telegram-made-up']),
            'unknown component made-up': dict(PROJECT, components=['made-up']),
            'issue must be the number': dict(PROJECT, issue=0),
            'checked_at is in the future': dict(PROJECT, checked_at='2026-10-08'),
            'added must be an ISO date': dict(PROJECT, added='вчера'),
            'fields must be': {key: value for key, value in PROJECT.items() if key != 'source'},
        }
        for message, project in cases.items():
            with self.subTest(message):
                found = showcase.problems(dict(CATALOG, projects=[project]), ROOT, TODAY)
                self.assertTrue(any(message in problem for problem in found), found)
        self.assertIn('Запись в барбершоп: listed more than once', showcase.problems(dict(CATALOG, projects=[PROJECT, PROJECT]), ROOT, TODAY))

    def test_issue_form_collects_every_catalog_field(self):
        form = (ROOT / '.github/ISSUE_TEMPLATE/showcase.yml').read_text(encoding='utf-8')
        for field in ('name', 'kind', 'url', 'source', 'uses', 'description', 'consent'):
            with self.subTest(field):
                self.assertIn(f'id: {field}\n', form)
        for kind in showcase.KINDS:
            self.assertIn(f'        - {kind}\n', form)
        self.assertIn('template=showcase.yml', showcase.FORM)


if __name__ == '__main__':
    unittest.main()
