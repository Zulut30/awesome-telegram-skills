"""Usability rounds: anonymous sessions, per-task measures and a strict round-to-round comparison (fixtures only)."""

import datetime as dt
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('usability_study', ROOT / 'scripts/usability_study.py')
study = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = study
spec.loader.exec_module(study)
TODAY = dt.date(2026, 10, 7)
LEVELS = ['new-to-bots', 'aiogram', 'mini-app-frontend', 'ai-agent', 'aiogram', 'new-to-bots']


def round_file(number, minutes, errors, outcomes=('completed',) * 6):
    data = study.template(number)
    data.update(started='2026-10-01', finished='2026-10-03', library_version='0.24.0', facilitator='team')
    if number > 1:
        data['changes_since_previous'] = ['quickstart: explain the virtual environment step (commit abc1234)']
    for index in range(6):
        for task in study.TASKS:
            data['sessions'].append({'participant': f'P{index + 1}', 'level': LEVELS[index], 'task': task, 'minutes': minutes[index],
                                     'errors': errors[index], 'outcome': outcomes[index], 'ease': 5,
                                     'problems': [{'severity': 'major', 'page': 'docs/quickstart.md', 'note': 'Не понял шаг с venv'}]})
    return data


class UsabilityStudyTests(unittest.TestCase):
    def test_summary_per_task(self):
        result = study.validate(round_file(1, [10, 12, 14, 16, 18, 30], [1, 2, 0, 3, 1, 5]), today=TODAY)
        self.assertEqual(result['participants'], 6)
        self.assertEqual(result['tasks']['quickstart'], {'sessions': 6, 'median_minutes': 15.0, 'completion_rate': 1.0,
                                                         'errors_per_session': 2.0, 'median_ease': 5.0, 'blockers': 0})

    def test_comparison_needs_every_task_better(self):
        first = study.validate(round_file(1, [10, 12, 14, 16, 18, 30], [1, 2, 0, 3, 1, 5]), today=TODAY)
        better = study.validate(round_file(2, [8, 9, 10, 11, 12, 20], [0, 1, 0, 1, 0, 2]), today=TODAY)
        self.assertTrue(study.compare(first, better)['improved'])
        worse_completion = study.validate(round_file(2, [8, 9, 10, 11, 12, 20], [0, 1, 0, 1, 0, 2],
                                                     ('completed',) * 5 + ('failed',)), today=TODAY)
        self.assertFalse(study.compare(first, worse_completion)['improved'])
        slower = study.validate(round_file(2, [10, 12, 14, 16, 18, 30], [0, 1, 0, 1, 0, 2]), today=TODAY)
        self.assertFalse(study.compare(first, slower)['improved'])

    def test_each_rule_rejects_its_violation(self):
        def broken(mutate):
            data = round_file(2, [8, 9, 10, 11, 12, 20], [0, 1, 0, 1, 0, 2])
            mutate(data)
            return data
        cases = {
            '5 to 8 different participants': lambda d: d.update(sessions=[s for s in d['sessions'] if s['participant'] in {'P1', 'P2'}]),
            'lists the fixes': lambda d: d.update(changes_since_previous=[]),
            'anonymous id': lambda d: d['sessions'][0].update(participant='Анна'),
            'level must be one of': lambda d: d['sessions'][0].update(level='senior'),
            'minutes must be between': lambda d: d['sessions'][0].update(minutes=0),
            'Single Ease Question': lambda d: d['sessions'][0].update(ease=9),
            'need a severity': lambda d: d['sessions'][0]['problems'][0].update(page='somewhere'),
            'remove names, usernames': lambda d: d['sessions'][0]['problems'][0].update(note='Спросил у @example_user'),
            'started <= finished <= today': lambda d: d.update(finished='2026-10-09'),
            'library_version': lambda d: d.update(library_version=''),
        }
        for message, mutate in cases.items():
            with self.subTest(message), self.assertRaisesRegex(study.StudyError, message):
                study.validate(broken(mutate), today=TODAY)

    def test_empty_template_is_not_a_result(self):
        with self.assertRaises(study.StudyError):
            study.validate(study.template(1), today=TODAY)
        self.assertIn('scripts/usability_study.py compare', (ROOT / 'docs/usability-study.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
