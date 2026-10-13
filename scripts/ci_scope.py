"""Decide whether a pull request needs the library jobs of Repository checks.

Library jobs (packages on three systems, browsers, installs, examples) run unless every changed file is skill,
evaluation or docs content that none of them reads. Skill checks, generated files, history, docs site and the
in-process library tests run for every change; pushes to main, manual runs and the nightly Full acceptance run
everything. tests/test_ci_scope.py keeps LIBRARY_INPUTS in step with the code the library jobs run: a new
literal path to docs/ or .agents/skills/ there fails it until the path is listed here.

    python scripts/ci_scope.py --base HEAD^1 --head HEAD   # library=true|false, for $GITHUB_OUTPUT
    python scripts/ci_scope.py docs/polls.md evaluations/skill-selection.json
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
# Changes here alone skip the library jobs.
CONTENT = ('.agents/skills/', 'evaluations/', 'docs/')
# Content the library jobs read (prefixes): a change here runs them too.
LIBRARY_INPUTS = (
    '.agents/skills/telegram-ai-bot/references/streaming.md',  # its example runs as a library test
    '.agents/skills/telegram-bot-api/references/api-index.json',  # Telegram catalog of the packages
    '.agents/skills/telegram-code-patterns/',  # copied into consumers; api-reference and quickstart copies verified
    'docs/api-reference',  # generated from the packages, executed by verify_api_reference.py
    'docs/dialog-restart.md',  # recipe gallery sources, bundled as resources/recipes.json
    'docs/en/quickstart.md',
    'docs/platform-operations.md',
    'docs/quickstart.md',
    'docs/start/',  # integration test runs the existing-bot guide
    'docs/troubleshooting.md',  # integration test runs its snippets
)


def library(paths: list[str]) -> bool:
    """True when any path is not content, or is content a library job reads; an empty change runs everything."""
    if not paths:
        return True
    return any(not path.startswith(CONTENT) or path.startswith(LIBRARY_INPUTS) for path in paths)


def changed(base: str, head: str) -> list[str]:
    done = subprocess.run(['git', 'diff', '--name-only', '--no-renames', base, head], cwd=ROOT, check=True,
                          capture_output=True, text=True, encoding='utf-8')
    return [line for line in done.stdout.splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('paths', nargs='*', help='changed paths; instead of --base/--head')
    parser.add_argument('--base')
    parser.add_argument('--head', default='HEAD')
    args = parser.parse_args()
    if bool(args.paths) == bool(args.base):
        parser.error('pass changed paths or --base')
    paths = args.paths or changed(args.base, args.head)
    needed = library(paths)
    print(f'library={str(needed).lower()}')
    reason = 'library jobs run' if needed else 'content only: library jobs skipped'
    print(f'{len(paths)} changed files; {reason}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
