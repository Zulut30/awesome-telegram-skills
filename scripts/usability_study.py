"""Record usability sessions and compare rounds: did the fixes make the quickstart and the agent task easier?

    python scripts/usability_study.py new --round 1                 # docs/internal/usability/round-1.json, no sessions
    python scripts/usability_study.py check docs/internal/usability/round-1.json
    python scripts/usability_study.py compare docs/internal/usability/round-1.json docs/internal/usability/round-2.json

Protocol and tasks: docs/usability-study.md. Participants are anonymous (P1, P2, ...); records hold the level,
time, errors, outcome, the Single Ease Question score (1-7) and problems with the page they happened on. A round
counts only with 5 to 8 participants. The comparison passes when, for every task, the median time and the errors
per session go down and the completion rate does not drop.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'docs/internal/usability'
TASKS = {'quickstart': 'Пройти первый запуск до ответа offline-бота',
         'agent-task': 'С ИИ-агентом и скиллами добавить клавиатуру в два столбца в готового бота на aiogram'}
LEVELS = ('new-to-bots', 'aiogram', 'mini-app-frontend', 'ai-agent')
OUTCOMES = ('completed', 'with-help', 'failed')
SEVERITIES = ('blocker', 'major', 'minor')
PRIVATE = re.compile(r'\d{6,}:[A-Za-z0-9_-]{30,}|[\w.+-]+@[\w-]+\.[\w.]+|\+\d[\d ()-]{8,}|@[A-Za-z][\w]{4,}')


class StudyError(ValueError):
    """The round file is malformed or incomplete."""


def template(number: int) -> dict:
    return {'schema_version': 1, 'round': number, 'started': '', 'finished': '', 'library_version': '', 'facilitator': '',
            'changes_since_previous': [], 'sessions': []}


def validate(study: object, *, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    if not isinstance(study, dict) or study.get('schema_version') != 1 or not isinstance(study.get('round'), int):
        raise StudyError('a round file needs schema_version 1 and a round number')
    try:
        started, finished = dt.date.fromisoformat(study['started']), dt.date.fromisoformat(study['finished'])
    except (KeyError, TypeError, ValueError):
        raise StudyError('started and finished must be dates YYYY-MM-DD') from None
    if not started <= finished <= today:
        raise StudyError('dates must satisfy started <= finished <= today')
    if not re.fullmatch(r'\d+\.\d+\.\d+', str(study.get('library_version', ''))):
        raise StudyError('library_version must be the version the participants used')
    sessions = study.get('sessions')
    if not isinstance(sessions, list) or not 5 <= len({session.get('participant') for session in sessions}) <= 8:
        raise StudyError('a round needs 5 to 8 different participants')
    if study['round'] > 1 and not study.get('changes_since_previous'):
        raise StudyError('a repeated round lists the fixes made since the previous round')
    for index, session in enumerate(sessions, start=1):
        where = f'sessions[{index}]'
        if not re.fullmatch(r'P[1-9]\d?', str(session.get('participant'))):
            raise StudyError(f'{where}.participant must be an anonymous id like P3')
        if session.get('level') not in LEVELS:
            raise StudyError(f'{where}.level must be one of {", ".join(LEVELS)}')
        if session.get('task') not in TASKS:
            raise StudyError(f'{where}.task must be one of {", ".join(TASKS)}')
        if session.get('outcome') not in OUTCOMES:
            raise StudyError(f'{where}.outcome must be one of {", ".join(OUTCOMES)}')
        minutes, errors, ease = session.get('minutes'), session.get('errors'), session.get('ease')
        if not isinstance(minutes, (int, float)) or not 0 < minutes <= 180:
            raise StudyError(f'{where}.minutes must be between 0 and 180')
        if not isinstance(errors, int) or errors < 0:
            raise StudyError(f'{where}.errors must be a count')
        if ease not in range(1, 8):
            raise StudyError(f'{where}.ease must be the Single Ease Question score 1-7')
        for problem in session.get('problems', []):
            if problem.get('severity') not in SEVERITIES or not str(problem.get('page', '')).startswith(('docs/', 'README', 'packages/', '.agents/')):
                raise StudyError(f'{where}.problems need a severity ({", ".join(SEVERITIES)}) and the page it happened on')
            if PRIVATE.search(json.dumps(problem, ensure_ascii=False)):
                raise StudyError(f'{where}.problems: remove names, usernames, e-mail, phone numbers and tokens')
    for task in TASKS:
        if sum(1 for session in sessions if session['task'] == task) < 5:
            raise StudyError(f'task {task}: at least 5 sessions per round')
    return summary(study)


def summary(study: dict) -> dict:
    result = {'round': study['round'], 'participants': len({session['participant'] for session in study['sessions']}), 'tasks': {}}
    for task in TASKS:
        rows = [session for session in study['sessions'] if session['task'] == task]
        result['tasks'][task] = {
            'sessions': len(rows),
            'median_minutes': statistics.median(row['minutes'] for row in rows),
            'completion_rate': round(sum(row['outcome'] == 'completed' for row in rows) / len(rows), 3),
            'errors_per_session': round(sum(row['errors'] for row in rows) / len(rows), 2),
            'median_ease': statistics.median(row['ease'] for row in rows),
            'blockers': sum(problem['severity'] == 'blocker' for row in rows for problem in row.get('problems', [])),
        }
    return result


def compare(before: dict, after: dict) -> dict:
    tasks, better = {}, True
    for task in TASKS:
        old, new = before['tasks'][task], after['tasks'][task]
        improved = (new['median_minutes'] < old['median_minutes'] and new['errors_per_session'] < old['errors_per_session']
                    and new['completion_rate'] >= old['completion_rate'])
        better = better and improved
        tasks[task] = {'before': old, 'after': new, 'improved': improved}
    return {'improved': better, 'rounds': [before['round'], after['round']], 'tasks': tasks}


def load(path: Path) -> dict:
    try:
        return validate(json.loads(path.read_text(encoding='utf-8')))
    except ValueError as error:
        raise StudyError(f'{path}: {error}') from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    new = commands.add_parser('new')
    new.add_argument('--round', type=int, required=True)
    check = commands.add_parser('check')
    check.add_argument('file', type=Path)
    versus = commands.add_parser('compare')
    versus.add_argument('before', type=Path)
    versus.add_argument('after', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'new':
            target = FOLDER / f'round-{args.round}.json'
            if target.exists():
                raise StudyError(f'{target.relative_to(ROOT)} already exists')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(template(args.round), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            result: dict = {'created': str(target.relative_to(ROOT))}
        elif args.command == 'check':
            result = load(args.file)
        else:
            result = compare(load(args.before), load(args.after))
            if not result['improved']:
                print(json.dumps(result, ensure_ascii=False))
                return 1
    except StudyError as error:
        sys.stderr.write(f'{error}\n')
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
