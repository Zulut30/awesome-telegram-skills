"""Check that commit messages say what changed, why, and how it was verified.

    python scripts/check_commit_messages.py                    # commits in origin/main..HEAD
    python scripts/check_commit_messages.py --range BASE..HEAD # a pull request or a push
    python scripts/check_commit_messages.py --message-file .git/COMMIT_EDITMSG

Format (template: .gitmessage, rules: CONTRIBUTING.md):

    area: what the change does, imperative, at most 72 characters

    What changed and why, in one or more paragraphs.

    Проверено: commands and their results (or "Verified: ...")

    Co-Authored-By: ... (optional trailers)

Merge commits, commits by bots (Dependabot) and commits already contained in BASELINE, the last commit before the
rule existed, are not checked.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'ce1508bc8d75a31eb5f581d6240b4cac0eccf271'
TRAILER = re.compile(r'^[A-Z][\w-]*(-[\w]+)*: \S')
VERIFIED = re.compile(r'^(Проверено|Verified):\s*\S', re.I)
BOTS = re.compile(r'\[bot\]@users\.noreply\.github\.com$|^dependabot', re.I)


def problems(message: str) -> list[str]:
    lines = message.rstrip('\n').split('\n')
    lines = [line for line in lines if not line.startswith('#')]  # comments of the template
    subject = lines[0] if lines else ''
    found = []
    if not subject.strip():
        return ['empty subject line']
    if len(subject) > 72:
        found.append(f'subject is {len(subject)} characters, at most 72')
    if subject.endswith('.'):
        found.append('subject ends with a period')
    if re.match(r'(fixup!|squash!|wip\b)', subject, re.I):
        found.append('fixup, squash or WIP commit: squash it before review')
    if len(lines) < 2 or lines[1].strip():
        found.append('the second line must be empty')
    body = [line for line in lines[2:] if not TRAILER.match(line) or VERIFIED.match(line)]
    prose = ' '.join(line.strip() for line in body if line.strip() and not VERIFIED.match(line))
    if len(prose) < 40:
        found.append('the body must say what changed and why (at least one sentence)')
    if not any(VERIFIED.match(line) for line in body):
        found.append('the body needs a "Проверено:" (or "Verified:") line naming the checks and their results')
    for number, line in enumerate(lines[2:], start=3):
        if len(line) > 100 and '://' not in line and not TRAILER.match(line):
            found.append(f'line {number} is {len(line)} characters, at most 100')
    return found


def git(*arguments: str) -> str:
    return subprocess.run(['git', *arguments], cwd=ROOT, capture_output=True, text=True, check=True, encoding='utf-8').stdout


def checked_commits(revision_range: str) -> list[str]:
    commits = git('rev-list', '--no-merges', revision_range).split()
    has_baseline = subprocess.run(['git', 'cat-file', '-e', BASELINE + '^{commit}'], cwd=ROOT, capture_output=True).returncode == 0
    result = []
    for commit in commits:
        if has_baseline and subprocess.run(['git', 'merge-base', '--is-ancestor', commit, BASELINE], cwd=ROOT).returncode == 0:
            continue
        if BOTS.search(git('show', '-s', '--format=%ae', commit).strip()):
            continue
        result.append(commit)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--range', default='origin/main..HEAD', help='git revision range, e.g. BASE..HEAD')
    parser.add_argument('--message-file', type=Path, help='check one message, e.g. from a commit-msg hook')
    args = parser.parse_args()
    if args.message_file:
        found = problems(args.message_file.read_text(encoding='utf-8'))
        if found:
            sys.stderr.write('\n'.join(found) + '\n')
            return 1
        return 0
    failures = {}
    commits = checked_commits(args.range)
    for commit in commits:
        found = problems(git('show', '-s', '--format=%B', commit))
        if found:
            failures[commit[:10] + ' ' + git('show', '-s', '--format=%s', commit).strip()] = found
    for commit, found in failures.items():
        sys.stderr.write(f'{commit}\n' + ''.join(f'  - {problem}\n' for problem in found))
    if failures:
        sys.stderr.write('Template: .gitmessage (git config commit.template .gitmessage); rules: CONTRIBUTING.md\n')
        return 1
    print(json.dumps({'passed': True, 'range': args.range, 'checked': len(commits)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
