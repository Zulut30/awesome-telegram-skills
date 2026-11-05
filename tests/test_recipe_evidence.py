"""Evidence attribution and fail-closed source/artifact binding; no real service needed."""
from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import recipe_evidence as evidence


class RecipeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='recipe-evidence-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        for name in evidence.RUNNERS:
            self.put(name, 'bound source\n')
        self.put('scripts/verify_recipe_execution.py', '''
def run(label, python, arguments):
    return subprocess.run([str(python), '-I', '-B', '-X', 'utf8', *map(str, arguments)])
batch = run('all-python-fixtures', args.sdk_python, ['-m', 'telegram_patterns._offline_recipe', '--all-python'])
''')
        for name in ('packages/python/pyproject.toml', 'packages/python/LICENSE', 'packages/typescript/package.json',
                     'packages/typescript/README.md', 'packages/typescript/LICENSE', 'recipes/sample.md'):
            self.put(name, 'source')
        self.catalog = {'library_version': '8.1.0', 'recipes': [
            self.recipe('python-example', 'python', 'experimental', 'sqlite'),
            self.recipe('native.unexecuted', 'typescript', 'reference', 'reference'),
        ]}
        self.wheel = self.root / 'library.whl'
        self.tarball = self.root / 'library.tgz'
        self.tarball.write_bytes(b'synthetic tarball: archive verifier has its own contract suite')
        self.report = self.root / 'distribution-report.json'
        self.report_value = {'passed': True, 'version': '8.1.0', 'stages': [{'stage': 'recipe-execution-consumer', 'exit_code': 0}],
                             'recipe_execution': {'passed': True, 'version': '8.1.0', 'python_recipes': 1,
                                                  'installed_origins': [{'prefix': '/consumer/core'}, {'prefix': '/consumer/sdk'}],
                                                  'recipes': [{'recipe_id': 'python-example', 'library_version': '8.1.0',
                                                               'kind': 'sqlite', 'passed': True, 'checks': ['replay-one-effect'],
                                                               'telegram_requests': False, 'external_network_attempts': 0}]},
                             'native_recipes': {'passed': True, 'checks': ['location', 'popup']}}
        # Archive byte/RECORD/typing/export correctness belongs to verify_distribution_contract's
        # existing suite. Here we keep real files/ZIP/hash operations and replace only that boundary.
        self.contract = patch.object(evidence, 'verify_distributions', return_value={'version': '8.1.0', 'passed': True})
        self.contract.start()
        self.addCleanup(self.contract.stop)
        self.refresh()

    def put(self, name, value):
        target = self.source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding='utf-8', newline='\n')

    @staticmethod
    def recipe(name, language, maturity, kind):
        code = '# synthetic recipe\n'
        return {'id': name, 'language': language, 'maturity': maturity,
                'code': code, 'code_sha256': evidence.digest(code.encode()),
                'scope': 'synthetic scope', 'verification': 'mock' if language == 'python' else 'not_run',
                'source_files': ['recipes/sample.md'], 'check_files': ['scripts/verify_recipe_execution.py'],
                'execution': {'kind': kind}}

    def refresh(self):
        data = (json.dumps(self.catalog) + '\n').encode()
        self.put('catalog/recipe-gallery.json', data.decode())
        with zipfile.ZipFile(self.wheel, 'w') as archive:
            archive.writestr('telegram_patterns/resources/recipes.json', data)
        self.report_value['artifacts'] = [{'name': p.name, 'bytes': p.stat().st_size, 'sha256': evidence.digest(p.read_bytes())}
                                          for p in (self.wheel, self.tarball)]
        self.report.write_text(json.dumps(self.report_value), encoding='utf-8')

    def build(self):
        return evidence.make_registry(self.report, self.wheel, self.tarball, self.source)

    def test_individual_result_does_not_promote_maturity_or_native_catalog(self):
        registry = self.build()
        python, native = registry['recipes']
        self.assertEqual(python['evidence']['status'], 'offline_pass')
        self.assertEqual(python['evidence']['producer_command'], ['/consumer/sdk/bin/python', '-I', '-B', '-X', 'utf8', '-m', 'telegram_patterns._offline_recipe', '--all-python'])
        self.assertIn('not capture argv', python['evidence']['command_provenance'])
        self.assertEqual(python['maturity'], 'experimental')
        self.assertEqual(native['evidence']['status'], 'not_run')
        self.assertIsNone(native['evidence']['producer_command'])
        self.assertFalse(registry['stable_gate']['evidence_complete'])
        self.assertEqual(registry['stable_gate']['status'], 'no_stable_scope')
        self.assertFalse(registry['quality_or_production_approved'])

    def test_new_stable_without_individual_result_stays_an_explicit_gap(self):
        self.catalog['recipes'].append(self.recipe('future.stable', 'typescript', 'stable', 'reference'))
        self.refresh()
        registry = self.build()
        self.assertEqual(registry['stable_gate']['missing_recipe_ids'], ['future.stable'])
        self.assertFalse(registry['stable_gate']['evidence_complete'])

    def test_stable_individual_offline_evidence_still_is_not_quality_approval(self):
        self.catalog['recipes'][0]['maturity'] = 'stable'
        self.refresh()
        registry = self.build()
        self.assertTrue(registry['stable_gate']['evidence_complete'])
        self.assertFalse(registry['stable_gate']['quality_or_production_approved'])

    def test_stale_artifact_and_report_are_refused(self):
        registry = self.build()
        self.tarball.write_bytes(b'substituted artifact')
        with self.assertRaisesRegex(evidence.EvidenceError, 'artifact'):
            evidence.check_registry(registry, self.report, self.wheel, self.tarball, self.source)
        self.report.write_text(self.report.read_text() + ' ', encoding='utf-8')
        with self.assertRaisesRegex(evidence.EvidenceError, 'report changed'):
            evidence.check_registry(registry, self.report, self.wheel, self.tarball, self.source)

    def test_stale_source_refuses_even_when_version_and_docs_date_are_unchanged(self):
        registry = self.build()
        self.put('recipes/sample.md', 'changed behavior, unchanged version/date')
        with self.assertRaisesRegex(evidence.EvidenceError, 'Stale source'):
            evidence.check_registry(registry, self.report, self.wheel, self.tarball, self.source)

    def test_unknown_duplicate_empty_checks_network_and_wrong_version_are_refused(self):
        original = copy.deepcopy(self.report_value)
        mutations = [lambda r: r.update(recipe_id='not-in-catalog'), lambda r: r.update(checks=[]),
                     lambda r: r.update(library_version='8.0.0'), lambda r: r.update(external_network_attempts=True),
                     lambda r: r.update(telegram_requests=True), lambda r: r.update(kind='sdk-request'),
                     lambda r: r.update(passed=False)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.report_value = copy.deepcopy(original)
                mutate(self.report_value['recipe_execution']['recipes'][0])
                self.refresh()
                with self.assertRaises(evidence.EvidenceError):
                    self.build()
        self.report_value = copy.deepcopy(original)
        self.report_value['recipe_execution']['recipes'] *= 2
        self.report_value['recipe_execution']['python_recipes'] = 2
        self.refresh()
        with self.assertRaisesRegex(evidence.EvidenceError, 'Duplicate'):
            self.build()

    def test_forged_native_pass_does_not_survive_registry_check(self):
        registry = self.build()
        registry['recipes'][1]['evidence']['status'] = 'offline_pass'
        with self.assertRaisesRegex(evidence.EvidenceError, 'differs'):
            evidence.check_registry(registry, self.report, self.wheel, self.tarball, self.source)

    def test_caller_file_preserved_and_no_stable_output_written(self):
        target = self.root / 'caller.json'
        target.write_bytes(b'caller bytes')
        with self.assertRaises(FileExistsError):
            evidence.write_new(target, {'replacement': True})
        self.assertEqual(target.read_bytes(), b'caller bytes')
        target = self.root / 'stable.json'
        arguments = ['create', '--report', str(self.report), '--wheel', str(self.wheel), '--tarball', str(self.tarball),
                     '--source', str(self.source), '--registry', str(target), '--require-stable']
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(evidence.main(arguments), 1)
        self.assertFalse(target.exists())

    def test_missing_results_are_not_vacuous_runtime_coverage(self):
        self.report_value['recipe_execution']['recipes'] = []
        self.report_value['recipe_execution']['python_recipes'] = 0
        self.refresh()
        registry = self.build()
        self.assertEqual(registry['summary']['offline_pass'], 0)
        self.assertEqual(registry['summary']['not_run'], 2)

    def test_source_traversal_and_git_mismatch_are_refused(self):
        with self.assertRaises(evidence.EvidenceError):
            evidence.source_file(self.source, '../outside')
        completed = [type('Result', (), {'returncode': 0, 'stdout': b'a' * 40 + b'\n'})(),
                     type('Result', (), {'returncode': 0, 'stdout': b'b blob 6\nwrong!\n'})()]
        with (
            patch.object(evidence.subprocess, 'run', side_effect=completed),
            self.assertRaisesRegex(evidence.EvidenceError, 'Source bytes differ'),
        ):
            evidence.verify_git_source(self.source, self.root, 'abcdef1', ['recipes/sample.md'])


if __name__ == '__main__':
    unittest.main()
