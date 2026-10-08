"""Compare an agent's answers with and without a skill against per-task criteria.

For every task a solver model answers twice with the same read-only tools: once in an empty
folder and once in a folder holding a copy of the skill, which it reads itself. A judge model
sees one answer at a time, without knowing which run produced it, and marks each criterion.
Only `claude` (Claude Code CLI) is supported; it uses the caller's own login. The report records the
models that actually answered, because an alias such as `haiku` moves to a new model with a CLI update.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from eval_skill_selection import answering_model  # noqa: E402

PASS_SHARE = 0.75
TOOLS = 'Read,Glob,Grep'
ANSWER_RULES = ('У тебя нет доступа к проекту пользователя и уточнять нельзя: прими разумные допущения '
                'и дай решение текстом — подход, ключевой код и проверки. Не ссылайся на прочитанные файлы. '
                'Не более 500 слов.')


def claude(prompt: str, *, model: str, cwd: Path, tools: str, turns: int) -> dict:
    done = subprocess.run(
        ['claude', '-p', prompt, '--model', model, '--max-turns', str(turns), '--tools', tools,
         '--output-format', 'json', '--no-session-persistence'],
        cwd=cwd, capture_output=True, text=True, encoding='utf-8', timeout=600, stdin=subprocess.DEVNULL)
    if done.returncode:
        raise RuntimeError(f'claude exited {done.returncode}: {(done.stderr or done.stdout).strip()[-300:]}')
    return json.loads(done.stdout)


def solve(task: dict, *, skill_root: Path | None, model: str) -> dict:
    with tempfile.TemporaryDirectory(prefix='skill-value-') as folder:
        if skill_root is None:
            prompt = f'Задача: {task["task"]}\n\n{ANSWER_RULES}'
        else:
            shutil.copytree(skill_root, Path(folder) / task['skill'])
            prompt = (f'В текущем каталоге лежит скилл {task["skill"]}: {task["skill"]}/SKILL.md и его references. '
                      'Прочитай SKILL.md и только нужные references, затем выполни задачу.\n\n'
                      f'Задача: {task["task"]}\n\n{ANSWER_RULES}')
        for turns in (16, 30):
            data = claude(prompt, model=model, cwd=Path(folder), tools=TOOLS, turns=turns)
            if data.get('subtype') != 'error_max_turns':
                break
    return {'answer': str(data.get('result', '')).strip(), 'turns': data.get('num_turns'),
            'served_model': answering_model(data.get('modelUsage') or {}, model)}


def judge(task: dict, answer: str, *, model: str) -> tuple[list[dict], str | None]:
    criteria = '\n'.join(f'{number}. {text}' for number, text in enumerate(task['criteria'], 1))
    prompt = ('Оцени ответ ассистента на задачу разработчика Telegram-бота. Для каждого критерия реши, выполнен ли он: '
              'true, только если ответ явно содержит это утверждение, решение или код; общая фраза и намек не засчитываются; '
              'ответ, который утверждает противоположное, критерий не выполняет. Длина и стиль не важны.\n\n'
              f'<task>\n{task["task"]}\n</task>\n\n<criteria>\n{criteria}\n</criteria>\n\n<answer>\n{answer}\n</answer>\n\n'
              'Верни только JSON без пояснений вокруг: '
              '{"verdicts": [{"met": true, "why": "до 15 слов"}]} — ровно по одному элементу на критерий, в их порядке.')
    with tempfile.TemporaryDirectory(prefix='skill-value-judge-') as folder:
        for _ in range(3):
            data = claude(prompt, model=model, cwd=Path(folder), tools='', turns=1)
            text = str(data.get('result', ''))
            match = re.search(r'\{.*\}', text, re.S)
            try:
                verdicts = json.loads(match.group(0))['verdicts'] if match else None
            except (json.JSONDecodeError, KeyError, TypeError):
                verdicts = None
            if isinstance(verdicts, list) and len(verdicts) == len(task['criteria']) and \
                    all(isinstance(item, dict) and isinstance(item.get('met'), bool) for item in verdicts):
                return ([{'met': item['met'], 'why': str(item.get('why', ''))[:200]} for item in verdicts],
                        answering_model(data.get('modelUsage') or {}, model))
    raise RuntimeError(f'judge returned no valid verdicts for {task["id"]}')


def needed(criteria: int) -> int:
    return math.ceil(criteria * PASS_SHARE)


def summarize(results: list[dict]) -> dict:
    skills = {}
    for item in results:
        entry = skills.setdefault(item['skill'], {'tasks': 0, 'criteria': 0, 'without': 0, 'with': 0,
                                                  'passed_without': 0, 'passed_with': 0})
        size = len(item['criteria'])
        entry['tasks'] += 1
        entry['criteria'] += size
        for condition in ('without', 'with'):
            met = sum(verdict['met'] for verdict in item[condition]['verdicts'])
            entry[condition] += met
            entry['passed_' + condition] += met >= needed(size)
    for entry in skills.values():
        entry['uplift'] = round((entry['with'] - entry['without']) / entry['criteria'], 3)
    totals = {key: sum(entry[key] for entry in skills.values())
              for key in ('tasks', 'criteria', 'without', 'with', 'passed_without', 'passed_with')}
    totals['uplift'] = round((totals['with'] - totals['without']) / totals['criteria'], 3)
    return {'skills': dict(sorted(skills.items())), 'totals': totals}


def served_models(results: list[dict]) -> dict:
    """Which models answered as solver and as judge; results stored before the models were recorded add nothing."""
    entries = [item[condition] for item in results for condition in ('without', 'with')]
    return {role: sorted({entry[key] for entry in entries if entry.get(key)})
            for role, key in (('solver', 'served_model'), ('judge', 'judge_model'))}


def compact(run: dict) -> dict:
    """A run without answer texts: verdicts stay, so every number can be traced to a criterion."""
    results = [{**item, **{condition: {key: value for key, value in item[condition].items() if key != 'answer'}
                           for condition in ('without', 'with')}} for item in run['results']]
    return {**run, 'results': results}


def merge(report: dict | None, run: dict, *, cases_file: Path) -> dict:
    """Put a run into the shared report: it replaces the same solver's results for the evaluated tasks only."""
    order = [task['id'] for task in json.loads(cases_file.read_text(encoding='utf-8'))['tasks']]
    location = cases_file.resolve()
    shown = location.relative_to(ROOT).as_posix() if location.is_relative_to(ROOT) else location.as_posix()
    report = report or {'cases': shown, 'pass_share': PASS_SHARE, 'runs': []}
    run = compact(run)
    previous = next((item for item in report['runs'] if item['solver'] == run['solver']), None)
    if previous is not None:
        if previous['judge'] != run['judge']:
            raise ValueError(f'judge differs from the stored {run["solver"]} run: {previous["judge"]}')
        fresh = {item['id'] for item in run['results']}
        results = [item for item in previous['results'] if item['id'] not in fresh] + run['results']
        results.sort(key=lambda item: order.index(item['id']) if item['id'] in order else len(order))
        run = {**run, 'cli': sorted({*previous['cli'], *run['cli']}), 'served_models': served_models(results),
               'skills_sha256': {**previous['skills_sha256'], **run['skills_sha256']},
               **summarize(results), 'results': results}
    runs = [item for item in report['runs'] if item['solver'] != run['solver']] + [run]
    return {**report, 'runs': sorted(runs, key=lambda item: item['solver'])}


def table(report: dict) -> str:
    """Markdown table: criteria met per skill without and with the skill, one column pair per solver."""
    runs = report['runs']
    rows = ['| Скилл | Задач | ' + ' | '.join(f'{run["solver"]}: без → со | прирост' for run in runs) + ' |',
            '| --- | --- |' + ' --- | --- |' * len(runs)]
    names = sorted({name for run in runs for name in run['skills']})
    for name in [*names, None]:
        entries = [run['totals'] if name is None else run['skills'][name] for run in runs]
        cells = [f'{entry["without"]}/{entry["criteria"]} → {entry["with"]}/{entry["criteria"]} | {entry["uplift"]:+.0%}'
                 for entry in entries]
        rows.append(f'| {"**Всего**" if name is None else name} | {entries[0]["tasks"]} | ' + ' | '.join(cells) + ' |')
    return '\n'.join(rows) + '\n'


def skill_fingerprint(name: str) -> str:
    """Which version of the skill folder a result was measured on."""
    digest = hashlib.sha256()
    for path in sorted((ROOT / '.agents/skills' / name).rglob('*')):
        if path.is_file():
            digest.update(path.relative_to(ROOT).as_posix().encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()


def evaluate(cases_file: Path, *, model: str, judge_model: str, workers: int, only: set[str]) -> dict:
    tasks = json.loads(cases_file.read_text(encoding='utf-8'))['tasks']
    if only:
        tasks = [task for task in tasks if task['skill'] in only]
    if not tasks:
        raise ValueError('no tasks selected')

    def run(task: dict) -> dict:
        record = {'id': task['id'], 'skill': task['skill'], 'criteria': task['criteria']}
        for condition, root in (('without', None), ('with', ROOT / '.agents/skills' / task['skill'])):
            solved = solve(task, skill_root=root, model=model)
            verdicts, judged_by = judge(task, solved['answer'], model=judge_model)
            record[condition] = {'turns': solved['turns'], 'served_model': solved['served_model'], 'judge_model': judged_by,
                                 'verdicts': verdicts, 'answer': solved['answer']}
        return record

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run, tasks))
    version = subprocess.run(['claude', '--version'], capture_output=True, text=True).stdout.strip()
    return {'solver': model, 'judge': judge_model, 'cli': [version], 'served_models': served_models(results),
            'skills_sha256': {name: skill_fingerprint(name) for name in sorted({task['skill'] for task in tasks})},
            **summarize(results), 'results': results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=ROOT / 'evaluations/skill-value.json')
    parser.add_argument('--model', default='haiku', help='solver model; a small model is the strict case')
    parser.add_argument('--judge', default='sonnet', help='judge model')
    parser.add_argument('--skill', action='append', default=[], help='evaluate only this skill (repeatable)')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--output', type=Path, help='write the full JSON report, answers included')
    parser.add_argument('--report', type=Path, help='merge the run, without answer texts, into this shared report')
    parser.add_argument('--table', type=Path, help='print the Markdown table of a shared report and exit')
    args = parser.parse_args()
    if args.table:
        print(table(json.loads(args.table.read_text(encoding='utf-8'))), end='')
        return 0
    if shutil.which('claude') is None:
        parser.error('Claude Code CLI (claude) is not on PATH')
    report = evaluate(args.cases, model=args.model, judge_model=args.judge, workers=args.workers, only=set(args.skill))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.report:
        stored = json.loads(args.report.read_text(encoding='utf-8')) if args.report.exists() else None
        merged = merge(stored, report, cases_file=args.cases)
        args.report.write_text(json.dumps(merged, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'solver': report['solver'], 'judge': report['judge'], **report['totals']}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
