"""Measure how often an agent picks the right reference after reading a skill's SKILL.md.

Each case sends SKILL.md, one user request and a fixed question to a real agent CLI with
tools disabled, then compares the first `*.md` name in the answer with the expected set.
Only `claude` (Claude Code CLI) is supported; it uses the caller's own login. The report records
the model that actually answered, because an alias such as `haiku` moves to a new model with a CLI update.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from eval_skill_selection import ask, cli_version  # noqa: E402

ANSWER = re.compile(r'[a-z0-9][a-z0-9-]*\.md')


def evaluate(skill_file: Path, cases_file: Path, *, model: str, workers: int) -> dict:
    skill = skill_file.read_text(encoding='utf-8')
    cases = json.loads(cases_file.read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='routing-eval-') as folder:  # no project files or CLAUDE.md
        def run(case: dict) -> dict:
            prompt = (f'Ниже полный SKILL.md скилла {cases["skill"]}.\n\n<skill>\n{skill}\n</skill>\n\n'
                      f'Запрос пользователя: {case["query"]}\n\n{cases["question"]}')
            answer, served = ask(prompt, model=model, cwd=Path(folder))
            found = ANSWER.findall(answer)
            chosen = found[0] if found else None
            return {'query': case['query'], 'expected': case['expected'], 'chosen': chosen,
                    'correct': chosen in case['expected'], 'served_model': served, 'answer': answer.strip()[:200]}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run, cases['cases']))
    correct = sum(item['correct'] for item in results)
    served = Counter(item['served_model'] for item in results)
    return {'skill': cases['skill'], 'skill_file': skill_file.as_posix(), 'model': model,
            'served_model': served.most_common(1)[0][0], 'served_models': sorted(str(name) for name in served),
            'cli': cli_version(), 'cases': len(results), 'correct': correct, 'accuracy': round(correct / len(results), 3),
            'results': results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill', type=Path, required=True, help='SKILL.md to show the agent')
    parser.add_argument('--cases', type=Path, required=True, help='JSON with skill, question and cases')
    parser.add_argument('--model', default='claude-haiku-5-5', help='claude --model value; prefer an exact model ID to an alias')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--output', type=Path, help='Write the JSON report here')
    args = parser.parse_args()
    if shutil.which('claude') is None:
        parser.error('Claude Code CLI (claude) is not on PATH')
    report = evaluate(args.skill, args.cases, model=args.model, workers=args.workers)
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('skill', 'model', 'served_model', 'cases', 'correct', 'accuracy')}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
