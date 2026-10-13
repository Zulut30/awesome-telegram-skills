"""The «Разделы:» line: table of contents of a long skill reference.

An agent may preview a reference with a partial read such as `head -100`. A reference longer than LONG lines with
at least two sections lists its second-level headings near the top, so the preview shows everything the file
covers (Anthropic, Skill authoring best practices: "Structure longer reference files with table of contents").
The line follows the title, the availability label and the «Термины:» line.
"""
from __future__ import annotations

import re

LINE_PREFIX = 'Разделы: '
LONG = 100
HEAD = re.compile(r'^# .*\n\n(?:Доступно с .*\n\n)?(?:Термины: .*\n\n)?', re.M)


def sections(text: str) -> list[str]:
    """Second-level headings outside fenced code blocks."""
    found, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith('```'):
            fenced = not fenced
        elif not fenced and line.startswith('## '):
            found.append(line[3:].strip())
    return found


def with_contents_line(text: str) -> str:
    """Put (or refresh, or drop) the «Разделы:» line; the length is counted without it."""
    text = re.sub('^' + re.escape(LINE_PREFIX) + '.*\n\n?', '', text, flags=re.M)
    found = sections(text)
    if len(text.splitlines()) <= LONG or len(found) < 2:
        return text
    head = HEAD.search(text)
    at = head.end() if head else 0
    return text[:at] + LINE_PREFIX + '; '.join(found) + '.\n\n' + text[at:]
