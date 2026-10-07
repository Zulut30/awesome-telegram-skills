"""Measure how often an agent picks the right skill from the name and description list alone.

The agent sees what it sees at startup, every `name: description` pair, plus one request,
and names one skill; tools are disabled. Cases may come from a working tree or a git ref,
so a description change can be compared with its baseline.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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


def ask(prompt: str, *, model: str, cwd: Path) -> str:
    done = subprocess.run(
        ['claude', '-p', prompt, '--model', model, '--max-turns', '1', '--tools', '', '--output-format', 'json',
         '--no-session-persistence'],
        cwd=cwd, capture_output=True, text=True, encoding='utf-8', timeout=300, stdin=subprocess.DEVNULL)
    if done.returncode:
        raise RuntimeError(f'claude exited {done.returncode}: {done.stderr.strip()[-300:]}')
    return str(json.loads(done.stdout).get('result', ''))


def evaluate(cases_file: Path, *, ref: str | None, model: str, workers: int) -> dict:
    skills = descriptions(ref)
    listing = catalog(skills)
    cases = json.loads(cases_file.read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='selection-eval-') as folder:
        def run(case: dict) -> dict:
            prompt = (f'Доступные скиллы:\n{listing}\n\nЗапрос пользователя: {case["query"]}\n\n'
                      'Какой один скилл ты загрузишь первым? Ответь только его именем.')
            answer = ask(prompt, model=model, cwd=Path(folder))
            found = NAME.findall(answer)
            chosen = found[0] if found else None
            return {'query': case['query'], 'expected': case['expected'], 'not': case.get('not', []), 'chosen': chosen,
                    'correct': chosen in case['expected'], 'answer': answer.strip()[:160]}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run, cases['cases']))
    correct = sum(item['correct'] for item in results)
    return {'descriptions': ref or 'working tree', 'descriptions_sha256': digest(skills), 'model': model,
            'cases': len(results), 'correct': correct,
            'accuracy': round(correct / len(results), 3), 'results': results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--ref', help='git ref whose descriptions to use instead of the working tree')
    parser.add_argument('--model', default='haiku')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if shutil.which('claude') is None:
        parser.error('Claude Code CLI (claude) is not on PATH')
    report = evaluate(args.cases, ref=args.ref, model=args.model, workers=args.workers)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('descriptions', 'model', 'cases', 'correct', 'accuracy')}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
