"""Create the skeleton of a new skill that the validator walks you through.

    python scripts/new_skill.py telegram-example --title "Пример" --short "Короткое описание для каталога" \\
        --not-for telegram-bot-python

Creates .agents/skills/<name>/SKILL.md in the standard outline and agents/openai.yaml. Every place that needs your
text holds a "[TODO: ...]" marker, so `python scripts/validate_skills.py` fails with "unfinished scaffold" until
the skill is written. The remaining steps (catalog row, sources, evaluation tasks, counts) are in
docs/contributing-skills.md; `--next-steps` prints them for the created skill.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r'telegram-[a-z0-9]+(?:-[a-z0-9]+)*')

SKILL = '''---
name: {name}
description: "[TODO: что делает скилл, одним-двумя предложениями]. Используйте, когда [TODO: намерение пользователя]. Не для [TODO: соседняя задача] → {not_for}."
license: MIT
metadata:
  version: "{version}"
---

# {title}

## Когда использовать

[TODO: задачи пользователя, для которых нужен этот скилл.]

## Когда не использовать

[TODO: соседние задачи и скиллы, которые их решают, например {not_for}.]

## Алгоритм

[TODO: шаги, которые агент выполняет в проекте пользователя. Сохраняйте его стек; длинные справки выносите в references/ этого скилла.]

## Проверка

[TODO: как убедиться, что решение работает: команда, тест или offline-проверка без токена.]

## Типичные ошибки

- [TODO: ошибка и как ее избежать.]
- [TODO: ошибка и как ее избежать.]
- [TODO: ошибка и как ее избежать.]

## Источники

- [Telegram Bot API](https://core.telegram.org/bots/api) — [TODO: разделы, на которые опирается скилл; добавьте и другие первичные источники ссылками]

Проверено: {today}, [TODO: что именно сверено с источниками].
'''

INTERFACE = '''interface:
  display_name: "Telegram: {title}"
  short_description: "{short}"
  default_prompt: "Используй ${name}. [TODO: типичная просьба пользователя]"
'''

NEXT_STEPS = '''Дальше (подробно — docs/contributing-skills.md):
1. Замените каждый [TODO: ...] в .agents/skills/{name}/SKILL.md и agents/openai.yaml; длинные справки положите в references/.
2. Каталог: строка в README.md (раздел «Скилл под вашу задачу») и английская строка в README.en.md того же вида.
3. Числа скиллов: python -m unittest tests.test_current_numbers tests.test_readme_status называет каждый файл и место.
4. Источники: python scripts/check_skill_sources.py --table docs/sources.md пересобирает таблицу из разделов «Источники»;
   добавьте запись в журнал под таблицей.
5. Термины: python scripts/add_terms_lines.py, если текст использует термины из глоссария.
6. Оценки (нужен Claude Code CLI): три задачи с критериями в evaluations/skill-value.json и запросы в evaluations/skill-selection.json, затем
   python scripts/eval_skill_selection.py --cases evaluations/skill-selection.json --model claude-haiku-5-5 --mode reasoned --report evaluations/reports/skill-selection-latest.json
   (и так для каждой модели и режима в отчете; модель — точный ID, не алиас)
   python scripts/eval_skill_value.py --skill {name} --report evaluations/reports/skill-value-latest.json
7. Проверка: uv run --with "PyYAML>=6,<7" python scripts/validate_skills.py и python -m unittest discover -s tests.
'''


def create(root: Path, name: str, title: str, short: str, not_for: str, today: dt.date) -> list[Path]:
    if not NAME.fullmatch(name) or len(name) > 64:
        raise ValueError('name must look like telegram-example (lowercase words joined by hyphens)')
    skills = root / '.agents/skills'
    folder = skills / name
    if folder.exists():
        raise ValueError(f'{folder.relative_to(root)} already exists')
    if not (skills / not_for / 'SKILL.md').is_file() or not_for == name:
        raise ValueError(f'--not-for must name another existing skill, not {not_for}')
    if not 25 <= len(short) <= 64:
        raise ValueError('--short must be 25-64 characters')
    if any(character in title + short for character in '"\\<>'):
        raise ValueError('--title and --short may not contain quotes, backslashes or angle brackets')
    version = json.loads((root / 'components.json').read_text(encoding='utf-8'))['library_version']
    (folder / 'agents').mkdir(parents=True)
    files = [folder / 'SKILL.md', folder / 'agents/openai.yaml']
    files[0].write_text(SKILL.format(name=name, title=title, not_for=not_for, version=version, today=today.isoformat()), encoding='utf-8')
    files[1].write_text(INTERFACE.format(name=name, title=title, short=short), encoding='utf-8')
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('name', help='skill name and folder, e.g. telegram-example')
    parser.add_argument('--title', required=True, help='heading of SKILL.md, in Russian')
    parser.add_argument('--short', required=True, help='catalog description, 25-64 characters')
    parser.add_argument('--not-for', required=True, help='an existing skill for the neighbouring task')
    parser.add_argument('--next-steps', action='store_true', help='print the remaining steps after creating')
    args = parser.parse_args()
    try:
        files = create(ROOT, args.name, args.title, args.short, args.not_for, dt.date.today())
    except ValueError as error:
        sys.stderr.write(f'{error}\n')
        return 1
    print(json.dumps({'created': [str(path.relative_to(ROOT)) for path in files]}, ensure_ascii=False))
    if args.next_steps:
        print(NEXT_STEPS.format(name=args.name))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
