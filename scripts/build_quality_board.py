"""Collect the numbers of the public quality board.

    python scripts/build_quality_board.py --output output/quality-board.json            # repository data only
    python scripts/build_quality_board.py --ci --repo OWNER/REPO --output output/quality-board.json

Repository data (deterministic, read by the documentation site at build time): skill selection accuracy and the
value of skills from evaluations/reports, Bot API methods covered by recipes and by library components (through
catalog/capability-map.json), how fresh the source checks are, scenarios checked live in Telegram and the latest
acceptance. With --ci the GitHub API adds the share of green Repository checks runs on main, the latest Full
acceptance result and the support response times; the documentation site workflow does this on every build, so
the board on the site follows CI. A failed API call leaves those numbers empty instead of failing the build.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKED = re.compile(r'^Проверено: (\d{4}-\d{2}-\d{2}),', re.M)
QUARTER_DAYS = 92


def load(root: Path, name: str) -> dict:
    return json.loads((root / name).read_text(encoding='utf-8'))


def collect(root: Path) -> dict:
    selection = load(root, 'evaluations/reports/skill-selection-latest.json')
    value = load(root, 'evaluations/reports/skill-value-latest.json')['runs'][0]['totals']
    methods = [method['name'] for method in load(root, '.agents/skills/telegram-bot-api/references/api-index.json')['methods']]
    index_version = load(root, '.agents/skills/telegram-bot-api/references/api-index.json')['bot_api_version']
    recipes = {recipe['id']: recipe for recipe in load(root, 'catalog/recipe-gallery.json')['recipes']}
    capabilities = [cap for area in load(root, 'catalog/capability-map.json')['areas'] for cap in area['capabilities']]
    with_component = [name for name in methods
                      if any(cap.get('bot_api') and cap.get('components') and re.fullmatch(cap['bot_api'], name) for cap in capabilities)]
    with_recipe = [name for name in methods if f'api.{name}' in recipes]
    executed = [name for name in with_recipe if recipes[f'api.{name}']['verification'] in {'sdk', 'mock', 'live'}]
    dates = sorted(match.group(1) for path in (root / '.agents/skills').glob('*/SKILL.md')
                   if (match := CHECKED.search(path.read_text(encoding='utf-8'))))
    journal = re.findall(r'^### (\d{4}-\d{2}-\d{2}) — ', (root / 'docs/sources.md').read_text(encoding='utf-8'), re.M)
    live_cases = live_passed = 0
    for report in sorted((root / 'docs/live-checks').glob('*/report.json')):
        for scenario in json.loads(report.read_text(encoding='utf-8'))['scenarios'].values():
            live_cases += len(scenario['cases'])
            live_passed += sum(case['status'] == 'passed' for case in scenario['cases'].values())
    device_reports = len(list((root / 'docs/device-checks').glob('*/report.json')))
    # The newest accepted release; its main report carries the date, the -distribution/-first-run parts do not.
    acceptance = [entry for entry in load(root, 'docs/acceptance-history.json')['reports'] if entry['passed'] and entry['stages']]
    latest = max(acceptance, key=lambda entry: (tuple(map(int, entry['version'].split('.'))), entry['checked_date'] is not None))
    return {
        'skill_selection': {'date': selection['date'], 'threshold': selection['threshold'], 'gate_mode': selection['gate_mode'],
                            'runs': [{'model': run['served_model'], 'mode': run['mode'], 'accuracy': run['accuracy'],
                                      'correct': run['correct'], 'cases': run['cases']} for run in selection['runs']]},
        'skill_value': {'tasks': value['tasks'], 'passed_with': value['passed_with'], 'passed_without': value['passed_without'],
                        'criteria': value['criteria'], 'criteria_with': value['with'], 'criteria_without': value['without']},
        'bot_api': {'version': index_version, 'methods': len(methods), 'with_recipe': len(with_recipe),
                    'recipe_executed': len(executed), 'with_component': len(with_component)},
        'sources': {'skills': len(dates), 'oldest_check': dates[0], 'newest_check': dates[-1], 'last_journal_entry': max(journal),
                    'quarter_days': QUARTER_DAYS},
        'live': {'reports': len(list((root / 'docs/live-checks').glob('*/report.json'))), 'cases': live_cases, 'passed': live_passed,
                 'device_reports': device_reports},
        'acceptance': {'version': latest['version'], 'date': latest['checked_date'], 'stages': latest['stages'],
                       'python_tests': latest['python_tests'], 'typescript_tests': latest['typescript_tests']},
        'ci': None,
    }


def api(url: str) -> object:
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'awesome-telegram-skills quality board'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:  # noqa: S310
        return json.loads(response.read())


def summarize_runs(runs: list[dict]) -> dict:
    completed = [run for run in runs if run.get('status') == 'completed' and run.get('conclusion') in {'success', 'failure', 'timed_out'}]
    green = sum(run['conclusion'] == 'success' for run in completed)
    return {'runs': len(completed), 'green': green, 'share': round(green / len(completed), 3) if completed else None,
            'last': {'conclusion': completed[0]['conclusion'], 'date': completed[0]['created_at'][:10]} if completed else None}


def ci(repo: str) -> dict:
    """Each workflow separately: one that is missing on main (404) or unreachable leaves only its own entry empty."""
    base = f'https://api.github.com/repos/{repo}/actions/workflows'
    result: dict = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes')}
    for key, query in (('repository_checks_main', 'repository-checks.yml/runs?branch=main&per_page=30'),
                       ('full_acceptance', 'full-acceptance.yml/runs?per_page=10')):
        try:
            result[key] = summarize_runs(api(f'{base}/{query}')['workflow_runs'])  # type: ignore[index]
        except (OSError, ValueError, KeyError, TypeError) as error:
            sys.stderr.write(f'{key}: unavailable ({type(error).__name__})\n')
            result[key] = None
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ci', action='store_true', help='add CI numbers from the GitHub API')
    parser.add_argument('--repo', default='Zulut30/awesome-telegram-skills')
    args = parser.parse_args()
    board = collect(ROOT)
    if args.ci:
        board['ci'] = ci(args.repo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(board, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(board, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
