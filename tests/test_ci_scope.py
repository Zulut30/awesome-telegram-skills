"""Library jobs are skipped only for content they never read: ci_scope.py decides from the changed paths, and the
code those jobs run names no skill, evaluation or docs path that LIBRARY_INPUTS misses."""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKS = (ROOT / '.github/workflows/repository-checks.yml').read_text(encoding='utf-8')
spec = importlib.util.spec_from_file_location('ci_scope', ROOT / 'scripts/ci_scope.py')
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)
GATE = "if: needs.changes.outputs.library == 'true'"
# Library code itself: npm scripts of the workspaces and every package, example and tool test live here.
LIBRARY_TREES = ('packages', 'examples', 'tools')
CODE = {'.py', '.mjs', '.js', '.ts', '.json', '.toml', '.txt', '.html'}
LITERAL = re.compile(r'(?:docs|\.agents/skills|evaluations)/[\w.*/-]*')
# A path built from a directory literal and a variable: ROOT / 'docs' / name.
JOINED = re.compile(r"""['"](docs|\.agents/skills|\.agents|evaluations)['"]\s*/\s*(?!['"])""")
# Joined paths whose targets are listed by their prefix: the generator writes docs/api-reference*.md only.
JOINED_COVERED = {('scripts/build_api_reference.py', 'docs/'): 'docs/api-reference'}


def job_blocks(text):
    body = text.split('\njobs:\n', 1)[1]
    return dict(re.findall(r'^  ([a-z][a-z0-9-]*):\n((?:(?:    .*)?\n)*)', body, re.M))


def library_code():
    """Files the gated jobs run: their scripts and tests, what those import or call, and the library trees."""
    pending = []
    for block in job_blocks(CHECKS).values():
        if GATE in block:
            pending += re.findall(r'(?:scripts|tests)/[\w.-]+\.(?:py|mjs|ts)', block)
    seen = set()
    while pending:
        name = pending.pop()
        path = ROOT / name
        if name in seen or not path.is_file():
            continue
        seen.add(name)
        text = path.read_text(encoding='utf-8')
        pending += re.findall(r'(?:scripts|tests)/[\w.-]+\.(?:py|mjs|ts)', text)
        pending += [f'scripts/{module}.py' for module in re.findall(r'^\s*(?:from|import) (\w+)', text, re.M)]
    files = {ROOT / name for name in seen}
    for tree in LIBRARY_TREES:
        files |= {path for path in (ROOT / tree).rglob('*') if path.suffix in CODE and 'node_modules' not in path.parts
                  and 'dist' not in path.parts}
    return files


class CiScopeTests(unittest.TestCase):
    def test_content_alone_skips_and_everything_else_runs(self):
        self.assertFalse(scope.library(['.agents/skills/telegram-buttons/SKILL.md', 'evaluations/skill-selection.json',
                                        'docs/polls.md', '.agents/skills/telegram-bot-api/references/polls.md']))
        for paths in (
            [],  # nothing to compare: run everything
            ['packages/python/src/telegram_patterns/__init__.py'],
            ['.agents/skills/telegram-buttons/SKILL.md', 'README.md'],
            ['.agents/skills/telegram-code-patterns/SKILL.md'],
            ['.agents/skills/telegram-bot-api/references/api-index.json'],
            ['docs/quickstart.md'], ['docs/en/quickstart.md'], ['docs/api-reference-bot.md'],
            ['docs/start/existing-aiogram-bot.md'], ['docs/troubleshooting.md'],
            ['.github/workflows/repository-checks.yml'], ['scripts/ci_scope.py'], ['requirements/sdk.txt'],
        ):
            with self.subTest(paths=paths):
                self.assertTrue(scope.library(paths))

    def test_workflow_gates_library_jobs_and_required_accepts_only_their_content_skip(self):
        blocks = job_blocks(CHECKS)
        gated = {name for name, block in blocks.items() if GATE in block}
        # Skills, generated files, history, docs site and in-process library tests check every change.
        self.assertEqual(set(blocks) - gated, {'changes', 'skills', 'generated-files', 'history', 'python-unit',
                                               'docs-site', 'required'})
        for name in gated:
            with self.subTest(job=name):
                self.assertIn('    needs: changes\n', blocks[name])
        self.assertIn("echo 'library=true' >> \"$GITHUB_OUTPUT\"", blocks['changes'], 'pushes and manual runs check all')
        self.assertIn('python3 scripts/ci_scope.py --base HEAD^1 --head HEAD', blocks['changes'])
        self.assertIn('fetch-depth: 2', blocks['changes'])
        self.assertIn("contains(needs.*.result, 'skipped') && needs.changes.outputs.library != 'false'", blocks['required'])

    def test_library_jobs_read_no_content_outside_library_inputs(self):
        files = library_code()
        self.assertIn(ROOT / 'scripts/verify_pattern_packages.py', files)
        self.assertIn(ROOT / 'scripts/build_recipe_gallery.py', files, 'scripts the verifiers call are followed')
        # A literal counts when some repository file is at it or under it: a stale mention reads nothing.
        tracked = [path.relative_to(ROOT).as_posix() for tree in ('docs', '.agents/skills', 'evaluations')
                   for path in (ROOT / tree).rglob('*') if path.is_file()]
        missed = set()
        for path in files:
            name = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding='utf-8', errors='replace')
            found = set(LITERAL.findall(text))
            found |= {JOINED_COVERED.get((name, f'{root}/'), f'{root}/') for root in JOINED.findall(text)}
            for literal in found:
                # A directory literal without its slash names the same tree as the listed prefix.
                covered = literal.startswith(scope.LIBRARY_INPUTS) or (literal + '/').startswith(scope.LIBRARY_INPUTS)
                exists = any(file.startswith(literal.rstrip('*')) for file in tracked)
                if literal.startswith(scope.CONTENT) and not covered and exists:
                    missed.add(f'{name}: {literal}')
        self.assertEqual(sorted(missed), [], 'a library job reads this content: add its prefix to LIBRARY_INPUTS')


if __name__ == '__main__':
    unittest.main()
