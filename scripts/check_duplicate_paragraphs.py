"""Find paragraphs longer than two sentences repeated across SKILL.md files.

A skill may link its own copy of a shared reference, but SKILL.md text should not
restate another skill's paragraphs: such copies drift apart and waste context.
Paragraphs are compared after normalizing whitespace and links; near-copies count.
"""
from __future__ import annotations

import argparse
from difflib import SequenceMatcher
from itertools import combinations
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SENTENCE_END = re.compile(r'[.!?…](?:\s|$)')
THRESHOLD = 0.8


def paragraphs(text: str) -> list[str]:
    body = text.split('\n---', 2)[-1] if text.startswith('---') else text
    result = []
    for block in re.split(r'\n\s*\n', body.replace('\r\n', '\n')):
        block = block.strip()
        if not block or block.startswith(('#', '|', '```', '- ', '1. ')):
            continue
        plain = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', ' '.join(block.split()))
        if len(SENTENCE_END.findall(plain)) > 2:
            result.append(plain)
    return result


def duplicates(root: Path, threshold: float = THRESHOLD) -> list[dict]:
    found = []
    items = [(path.parent.name, paragraph) for path in sorted((root / '.agents/skills').glob('*/SKILL.md'))
             for paragraph in paragraphs(path.read_text(encoding='utf-8'))]
    for (skill_a, text_a), (skill_b, text_b) in combinations(items, 2):
        if skill_a == skill_b:
            continue
        matcher = SequenceMatcher(None, text_a, text_b, autojunk=False)
        if matcher.real_quick_ratio() < threshold or matcher.quick_ratio() < threshold:
            continue
        ratio = matcher.ratio()
        if ratio >= threshold:
            found.append({'skills': [skill_a, skill_b], 'similarity': round(ratio, 2), 'paragraph': text_a[:160]})
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--threshold', type=float, default=THRESHOLD)
    args = parser.parse_args()
    found = duplicates(ROOT, args.threshold)
    print(json.dumps({'passed': not found, 'duplicates': found}, ensure_ascii=False, indent=2))
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
