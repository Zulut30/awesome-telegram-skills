"""Add or refresh the «Термины:» line in skill references and the pages copied into skills.

A docs/ page mirrored from an example README is edited at the README; sync_skill_references.py
then copies it on.

SKILL.md files are excluded: they explain a term where it first appears. Generated API
reference pages get the line from build_api_reference.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _glossary import with_terms_line  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GENERATED = {'api-reference.md', 'api-reference-core.md', 'api-reference-bot.md', 'api-reference-typescript.md'}


def targets() -> list[Path]:
    manifest = json.loads((ROOT / 'catalog/skill-references.json').read_text(encoding='utf-8'))
    origin = {page: readme for readme, page in manifest.get('mirrors', {}).items()}
    copied = {ROOT / path for paths in manifest['copies'].values() for path in paths}
    own = [path for path in sorted((ROOT / '.agents/skills').glob('*/references/*.md')) if path not in copied]
    sources = [ROOT / origin.get(source, source) for source in manifest['copies']]
    return [path for path in own + sources if path.name not in GENERATED]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    stale = []
    for path in targets():
        text = path.read_text(encoding='utf-8')
        updated = with_terms_line(text)
        if updated != text:
            stale.append(path.relative_to(ROOT).as_posix())
            if not args.check:
                path.write_text(updated, encoding='utf-8')
    print(json.dumps({'passed': not (args.check and stale), 'files': stale}, ensure_ascii=False))
    return 1 if args.check and stale else 0


if __name__ == '__main__':
    sys.exit(main())
