"""CI keeps its guarantees: browser stages always run and one aggregate check covers every required job."""

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / '.github/workflows').glob('*.yml'))
CHECKS = (ROOT / '.github/workflows/repository-checks.yml').read_text(encoding='utf-8')


def jobs(text):
    """Top-level job ids of a workflow (two-space indented keys under `jobs:`)."""
    body = text.split('\njobs:\n', 1)[1]
    return re.findall(r'^  ([a-z][a-z0-9-]*):\n', body, re.M)


class CiWorkflowTests(unittest.TestCase):
    def test_no_workflow_skips_browser_checks(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow.name):
                self.assertFalse('--skip-browser' in workflow.read_text(encoding='utf-8'), f'{workflow.name} skips browser checks')

    def test_verifier_refuses_skip_browser_in_ci(self):
        environment = {**os.environ, 'CI': 'true'}
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/verify_pattern_packages.py'), '--skip-browser'],
                              env=environment, capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(done.returncode, 2)
        self.assertIn('--skip-browser is not allowed in CI', done.stderr)

    def test_required_check_needs_every_job(self):
        names = jobs(CHECKS)
        needs = re.search(r'^  required:\n(?:    .*\n)*?    needs: \[([^\]]+)\]', CHECKS, re.M)
        self.assertIsNotNone(needs)
        listed = [name.strip() for name in needs.group(1).split(',')]
        # Every other job must block merging through `required`.
        self.assertEqual(sorted(listed), sorted(set(names) - {'required'}))
        self.assertIn("contains(needs.*.result, 'skipped')", CHECKS)

    def test_browser_job_uses_playwright_chromium(self):
        block = CHECKS.split('\n  browser:\n', 1)[1].split('\n  api-compatibility:\n', 1)[0]
        self.assertIn('npx playwright install --with-deps chromium', block)
        self.assertIn("require('playwright').chromium.executablePath()", block)
        self.assertIn('python scripts/verify_pattern_packages.py', block)
        self.assertIn('node tests/docs-browser.mjs', block)

    def test_fresh_install_runs_on_three_systems_with_the_oldest_python(self):
        block = CHECKS.split('\n  fresh-install:\n', 1)[1].split('\n  examples:\n', 1)[0]
        self.assertIn('os: [ubuntu-latest, windows-latest, macos-latest]', block)
        self.assertIn("python-version: '3.11'", block)
        self.assertNotIn('setup-node', block)
        self.assertIn('python -m build --wheel --outdir dist packages/python', block)
        self.assertIn('python scripts/verify_fresh_install.py --wheel dist/*.whl', block)

    def test_every_generator_with_a_check_mode_runs_in_ci(self):
        block = CHECKS.split('\n  generated-files:\n', 1)[1].split('\n  python-style:\n', 1)[0]
        # The docs site is verified by verify_docs_site.py and the browser job; release builds have no check mode.
        exempt = {'build_docs_site.py'}
        for script in sorted((ROOT / 'scripts').glob('*.py')):
            text = script.read_text(encoding='utf-8')
            generator = script.name.startswith('build_') or script.name in {'sync_skill_references.py', 'add_terms_lines.py'}
            if generator and "'--check'" in text and script.name not in exempt:
                with self.subTest(script.name):
                    self.assertIn(f'python scripts/{script.name} --check', block)

    def test_full_acceptance_runs_nightly_on_tags_and_reports_failures(self):
        text = (ROOT / '.github/workflows/full-acceptance.yml').read_text(encoding='utf-8')
        self.assertRegex(text, r"schedule:\n    - cron: '\d+ \d+ \* \* \*'")
        self.assertIn("tags: ['v*.*.*']", text)
        self.assertIn('python scripts/verify_pattern_packages.py', text)
        self.assertIn('actions/upload-artifact@', text)
        self.assertIn("if: failure() && github.event_name != 'workflow_dispatch'", text)
        self.assertIn('issues: write', text)
        self.assertIn('gh issue create', text)
        self.assertIn('gh issue comment', text)

    def test_dependabot_covers_pins_and_keeps_sha_pinned_actions(self):
        config = (ROOT / '.github/dependabot.yml').read_text(encoding='utf-8')
        for ecosystem in ('github-actions', 'pip', 'npm'):
            self.assertIn(f'package-ecosystem: {ecosystem}', config)
        self.assertIn('directories: [/, /tools/mini-app-quality]', config)
        # Every action is pinned by a full commit SHA with a version comment Dependabot can update.
        for workflow in WORKFLOWS:
            for line in workflow.read_text(encoding='utf-8').splitlines():
                if line.strip().startswith(('- uses:', 'uses:')):
                    with self.subTest(workflow=workflow.name, line=line.strip()):
                        self.assertRegex(line, r'uses: [\w./-]+@[0-9a-f]{40} # v\d+(\.\d+)*$')
        # Tool and SDK versions live in requirements files that Dependabot reads, not inline in workflows.
        for workflow in WORKFLOWS:
            for line in workflow.read_text(encoding='utf-8').splitlines():
                if 'pip install' in line and '==' in line:
                    with self.subTest(workflow=workflow.name, line=line.strip()):
                        self.assertIn('matrix.aiogram', line, 'move the pin to requirements/*.txt')


if __name__ == '__main__':
    unittest.main()
