"""Copy shared docs/ pages into the skills that carry them; --check fails on any drift.

catalog/skill-references.json lists each docs/ source and its skill copies. A copy is
written byte for byte, so a skill folder stays standalone after it is copied elsewhere.
"mirrors" names example READMEs that are the source of a docs/ page: the page and its
skill copies follow the README. A skill reference named like a docs/ page but missing
from the list is an error too: hand-made copies drift unnoticed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'catalog/skill-references.json'


def plan(root: Path) -> tuple[dict[Path, Path], list[str]]:
    manifest = json.loads((root / MANIFEST).read_text(encoding='utf-8'))
    origin = {page: readme for readme, page in manifest.get('mirrors', {}).items()}
    targets, problems = {}, []
    for readme, page in manifest.get('mirrors', {}).items():
        if not (root / readme).is_file() or not page.startswith('docs/') or page not in manifest['copies']:
            problems.append(f'{readme}: a mirror needs the README and a docs/ page listed in copies')
            continue
        targets[root / page] = root / readme
    for source, destinations in manifest['copies'].items():
        if not (root / source).is_file():
            problems.append(f'missing source {source}')
            continue
        for destination in destinations:
            if Path(destination).name != Path(source).name or not destination.startswith('.agents/skills/'):
                problems.append(f'{destination}: a copy keeps the source name inside a skill')
            targets[root / destination] = root / origin.get(source, source)
    for reference in sorted((root / '.agents/skills').glob('*/references/*.md')):
        if (root / 'docs' / reference.name).is_file() and reference not in targets:
            problems.append(f'{reference.relative_to(root).as_posix()}: copy of docs/{reference.name} is not in {MANIFEST}')
    return targets, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='report drift without writing')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    targets, problems = plan(args.root)
    drift = [destination for destination, source in targets.items()
             if not destination.is_file() or destination.read_bytes() != source.read_bytes()]
    if not args.check:
        for destination in drift:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(targets[destination].read_bytes())
    report = {'passed': not problems and (not args.check or not drift), 'copies': len(targets),
              'drift' if args.check else 'written': [path.relative_to(args.root).as_posix() for path in drift],
              'problems': problems}
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
