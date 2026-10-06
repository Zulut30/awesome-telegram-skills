from contextlib import redirect_stdout, redirect_stderr
from dataclasses import FrozenInstanceError
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from telegram_patterns import RecipeCatalog, RecipeRunPlan, RecipeRunResult, plan_recipe, run_recipe_offline, UnsupportedCapability, ValidationFailure, InvalidCompletion, TimeoutFailure
from telegram_patterns.cli import main
import telegram_patterns.execution as execution


class ExecutionTests(unittest.TestCase):
    def test_restart_fixture_does_not_inherit_runner_arguments_and_restores_caller(self):
        code = '''import json,sys
from pathlib import Path
from telegram_patterns._offline_recipe import _execute
sys.argv=['caller-worker','--all-python','caller-only-argument']
before=sys.argv[:]
result=_execute('demo-dialog-restart')
assert sys.argv==before
assert result['passed'] and 'three-process-restart' in result['checks']
assert {p.name for p in Path.cwd().iterdir()}=={'owned.txt','aiogram.py'}
assert (Path.cwd()/'owned.txt').read_bytes()==b'preserved'
print(json.dumps(result))
'''
        with tempfile.TemporaryDirectory(prefix='worker argv proof ') as folder:
            root=Path(folder); (root/'owned.txt').write_bytes(b'preserved')
            (root/'aiogram.py').write_text('raise RuntimeError("PRIVATE_CANARY")',encoding='utf-8')
            environment=dict(os.environ,PYTHONPATH=str(root),BOT_TOKEN='100:PRIVATE_CANARY',PAYMENT_SECRET='PRIVATE_CANARY')
            run=subprocess.run([sys.executable,'-I','-B','-c',code],cwd=root,capture_output=True,
                env=environment,text=True,encoding='utf-8',timeout=90)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertNotIn('PRIVATE_CANARY',run.stdout+run.stderr)
            self.assertEqual(json.loads(run.stdout)['external_network_attempts'],0)
            self.assertEqual((root/'owned.txt').read_bytes(),b'preserved')

    def test_calendar_data_missing_or_unverified_blocks_before_worker(self):
        original=execution.importlib.metadata.version
        def missing(name):
            if name=='tzdata': raise execution.importlib.metadata.PackageNotFoundError()
            return original(name)
        for probe,reason in [(missing,'calendar-extra-required'),(lambda name:'2026.4' if name=='tzdata' else original(name),'calendar-data-differs-from-checked-fixture')]:
            with patch.object(execution.importlib.metadata,'version',side_effect=probe):
                plan=plan_recipe('demo-calendar')
                self.assertIn(reason,plan.blocked_reasons)
                with patch.object(execution.subprocess,'run',side_effect=AssertionError('child forbidden')):
                    with self.assertRaises(UnsupportedCapability): run_recipe_offline('demo-calendar')

    def test_catalog_requirements_are_detached_plans_are_frozen_and_never_read_secrets(self):
        with patch.dict(os.environ, {'BOT_TOKEN':'100:PRIVATE_CANARY', 'PAYMENT_SECRET':'PRIVATE_CANARY'}):
            for recipe in RecipeCatalog().recipes:
                plan = plan_recipe(recipe.id)
                self.assertIsInstance(plan, RecipeRunPlan)
                self.assertFalse(plan.offline_environment)
                self.assertFalse(plan.offline_permissions)
                self.assertTrue(plan.live_review and plan.effects)
                self.assertNotIn('PRIVATE_CANARY', repr(plan))
            data = RecipeCatalog().get('two-columns').execution
            self.assertIsNotNone(data)
            data['live_environment'].append('LOCAL_CHANGE')
            self.assertNotIn('LOCAL_CHANGE', plan_recipe('two-columns').live_environment)
            with self.assertRaises(FrozenInstanceError): plan.recipe_id = 'changed'

    def test_missing_sdk_and_native_reference_stop_before_child_or_temporary_files(self):
        with patch.object(execution.importlib.metadata, 'version', side_effect=execution.importlib.metadata.PackageNotFoundError()):
            self.assertIn('aiogram-extra-required',plan_recipe('two-columns').blocked_reasons)
            with patch.object(execution.subprocess,'run',side_effect=AssertionError('child forbidden')), patch.object(execution,'TemporaryDirectory',side_effect=AssertionError('write forbidden')):
                for recipe in ('two-columns','native.requestContact'):
                    with self.assertRaises(UnsupportedCapability):run_recipe_offline(recipe)
        with patch.object(execution.importlib.metadata,'version',return_value='3.32.0'):
            self.assertIn('sdk-differs-from-checked-fixture',plan_recipe('two-columns').blocked_reasons)
        for invalid in (False,0,121,float('nan'),float('inf'),'60'):
            with self.assertRaises(ValidationFailure):run_recipe_offline('demo-recovery',timeout=invalid)
        with self.assertRaises(KeyError):run_recipe_offline('../../PRIVATE_CANARY.py')

    def test_child_errors_invalid_feedback_and_timeout_never_reflect_payload(self):
        for response in (subprocess.CompletedProcess([],1,'PRIVATE_CANARY','PRIVATE_CANARY'),subprocess.CompletedProcess([],0,'{}','')):
            with patch.object(execution.subprocess,'run',return_value=response), self.assertRaises(InvalidCompletion) as error:
                run_recipe_offline('demo-recovery')
            self.assertNotIn('PRIVATE_CANARY',str(error.exception))
        with patch.object(execution.subprocess,'run',side_effect=subprocess.TimeoutExpired('PRIVATE_CANARY',60)), self.assertRaises(TimeoutFailure):run_recipe_offline('demo-recovery')

    def test_isolated_installed_core_and_sdk_runs_ignore_caller_directory_and_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);marker=root/'unexpected.txt'
            (root/'aiogram.py').write_text('raise RuntimeError("PRIVATE_CANARY")')
            (root/'.env').write_text('BOT_TOKEN=100:PRIVATE_CANARY')
            original=Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {'BOT_TOKEN':'100:PRIVATE_CANARY','PYTHONPATH':str(root),'PAYMENT_SECRET':'PRIVATE_CANARY'}):
                    for recipe in ('demo-recovery','two-columns','api.sendPhoto'):
                        result=run_recipe_offline(recipe)
                        self.assertIsInstance(result,RecipeRunResult);self.assertTrue(result.passed);self.assertFalse(result.telegram_requests)
            finally:os.chdir(original)
            self.assertFalse(marker.exists())
            self.assertEqual(len(list(root.iterdir())),2)

    def test_cli_emits_plan_before_result_and_never_runs_without_explicit_offline(self):
        with patch.object(execution.subprocess,'run',side_effect=AssertionError('implicit execution forbidden')), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['run-recipe','demo-recovery']),0)
        self.assertEqual(json.loads(output.getvalue())['stage'],'plan')
        with redirect_stdout(io.StringIO()) as output,redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(main(['run-recipe','demo-recovery','--offline']),0)
        records=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([r['stage'] for r in records],['plan','result']);self.assertFalse(errors.getvalue())
