"""Measure how often an agent picks the right skill from the name and description list alone.

The agent sees what it sees at startup, every `name: description` pair, plus one request,
and names one skill; tools are disabled. Cases may come from a working tree or a git ref,
so a description change can be compared with its baseline.

Two modes: `instant` asks for the name only (the strict case: no room to compare descriptions),
`reasoned` lets the agent match the request against the descriptions in one or two sentences and
takes the name from the last line, as an agent does before it calls a skill. Every run records the
model that actually answered: an alias such as `haiku` moves to a new model with a CLI update.
`--report` merges the run, without answer texts, into the shared report.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FRONTMATTER = re.compile(r'\A---\n(.*?)\n---', re.S)
NAME = re.compile(r'telegram-[a-z0-9-]+')
THRESHOLD = 0.95
GATE_MODE = 'reasoned'
QUESTIONS = {
    'instant': 'Какой один скилл ты загрузишь первым? Ответь только его именем.',
    'reasoned': ('Какой один скилл ты загрузишь первым? Коротко, в одном-двух предложениях, сопоставь запрос '
                 'с описаниями, затем последней строкой напиши только имя скилла.'),
}


def descriptions(ref: str | None) -> dict[str, str]:
    """name -> description from .agents/skills in the working tree or at a git ref."""
    import yaml
    result = {}
    if ref is None:
        files = {path.parent.name: path.read_text(encoding='utf-8') for path in (ROOT / '.agents/skills').glob('*/SKILL.md')}
    else:
        listing = subprocess.run(['git', 'ls-tree', '--name-only', f'{ref}:.agents/skills'], cwd=ROOT,
                                 capture_output=True, text=True, check=True).stdout.split()
        files = {name: subprocess.run(['git', 'show', f'{ref}:.agents/skills/{name}/SKILL.md'], cwd=ROOT,
                                      capture_output=True, text=True, encoding='utf-8', check=True).stdout for name in listing}
    for name, text in sorted(files.items()):
        data = yaml.safe_load(FRONTMATTER.match(text.replace('\r\n', '\n')).group(1))
        result[name] = data['description']
    return result


def catalog(skills: dict[str, str]) -> str:
    return '\n'.join(f'- {name}: {text}' for name, text in skills.items())


def digest(skills: dict[str, str]) -> str:
    """Fingerprint of the description list; a report is stale once it differs."""
    return hashlib.sha256(catalog(skills).encode('utf-8')).hexdigest()


def answering_model(usage: dict, requested: str) -> str | None:
    """The model that answered, from the CLI's modelUsage. The CLI also bills a small helper model for its own
    side request, so among the models whose ID contains the requested alias or ID take the one with the largest prompt."""
    def prompt_tokens(name: str) -> int:
        item = usage[name]
        return sum(int(item.get(key) or 0) for key in ('inputTokens', 'cacheCreationInputTokens', 'cacheReadInputTokens'))
    names = [name for name in usage if requested in name] or list(usage)
    return max(names, key=prompt_tokens) if names else None


def ask(prompt: str, *, model: str, cwd: Path) -> tuple[str, str | None]:
    done = subprocess.run(
        ['claude', '-p', prompt, '--model', model, '--max-turns', '1', '--tools', '', '--output-format', 'json',
         '--no-session-persistence'],
        cwd=cwd, capture_output=True, text=True, encoding='utf-8', timeout=300, stdin=subprocess.DEVNULL)
    if done.returncode:
        raise RuntimeError(f'claude exited {done.returncode}: {done.stderr.strip()[-300:]}')
    data = json.loads(done.stdout)
    return str(data.get('result', '')), answering_model(data.get('modelUsage') or {}, model)


def choose(answer: str, mode: str) -> str | None:
    """instant: the first skill name in the answer; reasoned: the last name on the last line, as the prompt asks."""
    if mode == 'instant':
        found = NAME.findall(answer)
    else:
        lines = answer.strip().splitlines()
        found = NAME.findall(lines[-1]) if lines else []
        found = found[-1:]
    return found[0] if found else None


def cli_version() -> str:
    return subprocess.run(['claude', '--version'], capture_output=True, text=True).stdout.strip()


def evaluate(cases_file: Path, *, ref: str | None, model: str, workers: int, mode: str = 'instant') -> dict:
    skills = descriptions(ref)
    listing = catalog(skills)
    cases = json.loads(cases_file.read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='selection-eval-') as folder:
        def run(case: dict) -> dict:
            prompt = f'Доступные скиллы:\n{listing}\n\nЗапрос пользователя: {case["query"]}\n\n{QUESTIONS[mode]}'
            answer, served = ask(prompt, model=model, cwd=Path(folder))
            chosen = choose(answer, mode)
            return {'query': case['query'], 'expected': case['expected'], 'not': case.get('not', []), 'chosen': chosen,
                    'correct': chosen in case['expected'], 'kind': case.get('kind', 'positive'), 'served_model': served,
                    'answer': answer.strip()[-300:]}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run, cases['cases']))
    correct = sum(item['correct'] for item in results)
    served = Counter(item['served_model'] for item in results)
    return {'descriptions': ref or 'working tree', 'descriptions_sha256': digest(skills), 'model': model, 'mode': mode,
            'served_model': served.most_common(1)[0][0], 'served_models': sorted(str(name) for name in served),
            'cli': cli_version(), 'cases': len(results), 'correct': correct,
            'accuracy': round(correct / len(results), 3), 'results': results}


def summary(run: dict) -> dict:
    """A run for the shared report: numbers per kind and the misses, without answer texts."""
    by_kind: dict[str, dict[str, int]] = {}
    for item in run['results']:
        entry = by_kind.setdefault(item['kind'], {'cases': 0, 'correct': 0})
        entry['cases'] += 1
        entry['correct'] += item['correct']
    misses = [{'query': item['query'], 'expected': item['expected'], 'chosen': item['chosen']}
              for item in run['results'] if not item['correct']]
    return {key: run[key] for key in ('model', 'mode', 'served_model', 'served_models', 'cli', 'cases', 'correct', 'accuracy')} | \
        {'by_kind': dict(sorted(by_kind.items(), key=lambda pair: pair[0] != 'positive')), 'misses': misses}


def merge(report: dict | None, run: dict, *, cases_file: Path, today: dt.date) -> dict:
    """Put a run into the shared report: it replaces the run of the same model and mode. Runs measured on other
    descriptions are dropped, because the report must describe one list of descriptions, and so are runs without
    a recorded answering model: an alias alone does not say which model was measured."""
    location = cases_file.resolve()
    shown = location.relative_to(ROOT).as_posix() if location.is_relative_to(ROOT) else location.as_posix()
    keep = report if report and report.get('descriptions_sha256') == run['descriptions_sha256'] else None
    runs = [item for item in (keep or {}).get('runs', [])
            if item.get('served_model') and (item['model'], item.get('mode')) != (run['model'], run['mode'])]
    runs.append(summary(run))
    runs.sort(key=lambda item: (item['mode'] != GATE_MODE, item['served_model'] or item['model']))
    return {'date': today.isoformat(), 'agent': 'Claude Code CLI, claude -p with tools disabled',
            'cases': shown, 'threshold': THRESHOLD, 'gate_mode': GATE_MODE,
            'descriptions_sha256': run['descriptions_sha256'], 'runs': runs}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--ref', help='git ref whose descriptions to use instead of the working tree')
    parser.add_argument('--model', default='claude-haiku-5-5', help='claude --model value; prefer an exact model ID to an alias')
    parser.add_argument('--mode', choices=sorted(QUESTIONS), default=GATE_MODE)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--output', type=Path, help='write the full JSON run, answers included')
    parser.add_argument('--report', type=Path, help='merge the run, without answer texts, into this shared report')
    args = parser.parse_args()
    if shutil.which('claude') is None:
        parser.error('Claude Code CLI (claude) is not on PATH')
    if args.report and args.ref:
        parser.error('--report describes the working tree; compare a --ref with --output instead')
    report = evaluate(args.cases, ref=args.ref, model=args.model, workers=args.workers, mode=args.mode)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.report:
        stored = json.loads(args.report.read_text(encoding='utf-8')) if args.report.exists() else None
        merged = merge(stored, report, cases_file=args.cases, today=dt.date.today())
        args.report.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('descriptions', 'model', 'mode', 'served_model', 'cases', 'correct', 'accuracy')}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
