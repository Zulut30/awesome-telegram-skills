from __future__ import annotations
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import FrozenInstanceError, replace
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from telegram_patterns import StarterComponent, StarterConflict, StarterPlan, create_starter, starter_components
from telegram_patterns.cli import main
import importlib
registry = importlib.import_module('telegram_patterns.starter_components')


class StarterComponentTests(unittest.TestCase):
    def supplied(self, root: Path, ts_version='0.10.0'):
        source = root / 'local library'; source.mkdir()
        (source / 'pyproject.toml').write_text('[project]\nname="awesome-telegram-patterns"\nversion="0.10.0"\n', encoding='utf-8')
        tarball = root / 'local tarball.tgz'
        data = json.dumps({'name':'@awesome-telegram/patterns','version':ts_version}).encode()
        with tarfile.open(tarball,'w:gz') as archive:
            member=tarfile.TarInfo('package/package.json');member.size=len(data)
            archive.addfile(member,io.BytesIO(data))
        return source,tarball

    def test_registry_is_immutable_independent_and_distinguishes_templates(self):
        groups = starter_components()
        self.assertEqual(len(groups),15)
        self.assertIsInstance(groups[0],StarterComponent)
        self.assertEqual(len({item.id for item in groups}),15)
        with self.assertRaises(FrozenInstanceError): groups[0].intent='changed'
        self.assertTrue(all('bot' in item.templates for item in starter_components('bot')))
        self.assertNotIn('api-client',[item.id for item in starter_components('bot')])
        self.assertIn('api-client',[item.id for item in starter_components('bot-mini-app')])
        with self.assertRaises(StarterConflict): starter_components('unknown')
        # Preserve the five positional DTO arguments introduced before 0.10.
        self.assertEqual(StarterPlan(Path('x'),'bot','0.9.2',(),False).components,())

    def test_dry_plan_matches_files_selection_and_dependency_closure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source,tarball=self.supplied(root);target=root/'new app'
            choices=['api-client','text-form','paginated-menu','selection-draft','mini-app-native-api','api-client']
            plan=create_starter(target,library=source,typescript=tarball,template='bot-mini-app',components=choices,dry_run=True)
            self.assertFalse(target.exists())
            self.assertEqual(plan.requested_components.count('api-client'),1)
            self.assertIn('responsive-shell',plan.components)
            self.assertIn('callback-router',plan.components)
            real=create_starter(target,library=source,typescript=tarball,template='bot-mini-app',components=choices)
            files=tuple(sorted(path.relative_to(target).as_posix() for path in target.rglob('*') if path.is_file()))
            self.assertEqual(plan.files,files);self.assertEqual(real.components,plan.components)
            self.assertIn('starter_form.py',files);self.assertIn('mini-app/src/starter-client.ts',files)
            app=(target/'app.py').read_text(encoding='utf-8')
            self.assertIn('SimpleEventIsolation()',app)
            self.assertIn('configure_starter_form(dispatcher)',app)
            self.assertNotIn('__COMPONENT_',app)
            self.assertNotIn('__COMPONENT_', (target/'mini-app/src/main.ts').read_text(encoding='utf-8'))
            configuration=json.loads((target/'.telegram-patterns.json').read_text(encoding='utf-8'))
            self.assertEqual(configuration['components'],list(plan.components))
            (target/'user-owned.py').write_bytes(b'owned')
            before={path.relative_to(target).as_posix():path.read_bytes() for path in target.rglob('*') if path.is_file()}
            with self.assertRaises(FileExistsError): create_starter(target,library=source,components=choices,template='bot-mini-app',typescript=tarball)
            self.assertEqual(before,{path.relative_to(target).as_posix():path.read_bytes() for path in target.rglob('*') if path.is_file()})

    def test_incompatible_selection_and_artifacts_do_not_create_target(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source,tarball=self.supplied(root,ts_version='0.9.2');target=root/'new'
            cases=[({'components':'text-form'},'selection-type'),({'components':[42]},'selection-type'),
                   ({'components':['UNKNOWN_SECRET_CANARY']},'unknown-component'),
                   ({'components':['api-client']},'component-template'),
                   ({'template':'bot-mini-app'},'missing-typescript'),
                   ({'template':'bot-mini-app','typescript':tarball},'artifact-version'),
                   ({'typescript':tarball},'unexpected-typescript')]
            for kwargs,reason in cases:
                with self.subTest(reason=reason),self.assertRaises(StarterConflict) as caught:
                    create_starter(target,library=source,**kwargs)
                self.assertEqual(caught.exception.reason,reason)
                self.assertFalse(target.exists());self.assertNotIn('CANARY',str(caught.exception))
            (source/'pyproject.toml').write_text('[project]\nname="awesome-telegram-patterns"\nversion="0.5.0"\n',encoding='utf-8')
            with self.assertRaises(StarterConflict) as caught:
                create_starter(target,library=source,components=['text-form'])
            self.assertEqual(caught.exception.reason,'component-version');self.assertFalse(target.exists())

    def test_blueprint_file_command_and_prefix_collisions_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source,_=self.supplied(root);target=root/'new'
            original=next(item for item in registry._COMPONENTS if item.id=='native-keyboards')
            for replacement in (replace(original,commands=('start',)),replace(original,files=('app.py',)),
                                replace(original,callback_prefixes=('act:overlap',)),
                                replace(original,files=('mini-app/src/main.ts',)),replace(original,files=('App.py',)),
                                replace(original,files=('app.py/child.py',)),replace(original,files=('../outside.py',))):
                items=tuple(replacement if item.id==original.id else item for item in registry._COMPONENTS)
                with patch.object(registry,'_COMPONENTS',items),patch.dict(registry._BY_ID,{original.id:replacement}):
                    with self.assertRaises(StarterConflict) as caught:
                        create_starter(target,library=source,components=['native-keyboards'])
                    self.assertEqual(caught.exception.reason,'entrypoint-conflict');self.assertFalse(target.exists())

    def test_cli_lists_without_artifacts_and_reports_safe_conflict(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['init','--list-components']),0)
        listed=json.loads(output.getvalue())
        self.assertFalse(listed['network']);self.assertEqual(len(listed['components']),15)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source,_=self.supplied(root);target=root/'new'
            with redirect_stderr(io.StringIO()) as error:
                self.assertEqual(main(['init',str(target),'--library',str(source),'--component','CANARY_SECRET','--json']),2)
            payload=json.loads(error.getvalue())
            self.assertEqual(payload['reason'],'unknown-component');self.assertNotIn('CANARY',error.getvalue())
            self.assertFalse(target.exists())
        with redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(['init','--list-components','--dry-run','--json']),2)
        self.assertEqual(json.loads(error.getvalue())['reason'],'listing-input')

    def test_each_python_feature_and_full_composition_execute_real_dispatcher(self):
        choices=['native-keyboards','paginated-menu','text-form','update-events']
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source,_=self.supplied(root)
            for selection in ([item] for item in choices):
                target=root/selection[0]
                create_starter(target,library=source,components=selection)
                done=subprocess.run([sys.executable,'offline_components.py'],cwd=target,capture_output=True,text=True,encoding='utf-8',timeout=60)
                self.assertEqual(done.returncode,0,done.stderr)
                proof=json.loads(done.stdout);self.assertTrue(proof['passed']);self.assertFalse(proof['network'])
            target=root/'all';create_starter(target,library=source,components=choices)
            done=subprocess.run([sys.executable,'offline_components.py'],cwd=target,capture_output=True,text=True,encoding='utf-8',timeout=60)
            self.assertEqual(done.returncode,0,done.stderr)
            proof=json.loads(done.stdout);self.assertEqual(len(proof['commands']),7);self.assertTrue(proof['session_closed'])


if __name__ == '__main__': unittest.main()
