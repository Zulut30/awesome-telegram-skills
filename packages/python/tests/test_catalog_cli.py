from __future__ import annotations
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from telegram_patterns import RecipeCatalog, create_starter
from telegram_patterns.cli import doctor, main

ROOT = Path(__file__).resolve().parents[3]


class RecipeTests(unittest.TestCase):
    def test_navigation_intersections_versions_unknown_context_and_immutable_links(self):
        catalog = RecipeCatalog()
        recipe = catalog.search('две кнопки', task='keyboards', context='private', sdk='aiogram', sdk_version='3.31.0')[0]
        self.assertEqual(recipe.id, 'two-columns')
        self.assertTrue(recipe.source_files and recipe.check_files)
        self.assertIsInstance(recipe.contexts, tuple)
        self.assertIn('native.BackButton.show', {r.id for r in catalog.search('назад', sdk='telegram-webapp')})
        lost = catalog.search('потерянный ответ', context='backend', task='recovery')[0]
        self.assertEqual((lost.id, lost.sdk, lost.api_version), ('demo-recovery', 'python-core', 'none'))
        self.assertEqual(catalog.search('потерянный ответ', context='private'), ())
        self.assertEqual(catalog.search(sdk='aiogram', sdk_version='0.0.0'), ())
        self.assertEqual(catalog.get('api.getUpdates').contexts, ('unspecified',))
        self.assertNotIn(catalog.get('api.getUpdates'), catalog.search(context='group', limit=1000))
        self.assertIn('private', catalog.get('api.createForumTopic').contexts)
        for field in ('task', 'context', 'sdk', 'sdk_version', 'api_version'):
            for invalid in (True, '', 'x' * 81):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValueError): catalog.search(**{field: invalid})

    def test_legacy_navigation_defaults_and_link_injection_rejected(self):
        data={'schema_version':1,'library_version':'fixture','recipes':[{
            'id':'legacy','title':'Fixture','summary':'fixture','category':'keyboards','language':'python','keywords':[],
            'code':'pass','verification':'sdk','scope':'fixture','sources':['https://core.telegram.org/bots/api']}]}
        legacy=RecipeCatalog(data).get('legacy')
        self.assertEqual((legacy.tasks,legacy.contexts,legacy.source_files), ((),('unspecified',),()))
        for field, value in [('contexts',[]),('tasks',['Invented label']),('sdk',None),('sdk_version','<script>'),
                             ('source_files',['../secret.env']),('check_files',['https://invalid.test']),
                             ('source_files',['C:/secret']),('source_files',['scripts//check.py'])]:
            bad=json.loads(json.dumps(data));bad['recipes'][0][field]=value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError): RecipeCatalog(bad)

    def test_maturity_does_not_promote_evidence_to_stable(self):
        catalog = RecipeCatalog()
        self.assertEqual(len(catalog.search(maturity='experimental', limit=1000)), 30)
        self.assertEqual(len(catalog.search(maturity='reference', limit=1000)), 284)
        self.assertEqual(catalog.search(maturity='stable'), ())
        self.assertEqual(catalog.get('api.sendPhoto').maturity, 'reference')
        self.assertEqual(catalog.get('two-columns').maturity, 'experimental')
        self.assertEqual(catalog.search(verification='sdk', maturity='experimental')[0].id, 'two-columns')
        self.assertEqual(catalog.search(verification='mock', maturity='reference'), ())
        self.assertRaises(ValueError, catalog.search, maturity='production')

    def test_legacy_and_explicit_maturity_are_independent_of_verification(self):
        data={'schema_version':1,'library_version':'fixture','recipes':[{
            'id':'fixture','title':'Fixture','summary':'fixture','category':'keyboards','language':'python','keywords':[],
            'code':'pass','verification':'live','scope':'fixture','sources':['https://core.telegram.org/bots/api']}]}
        self.assertEqual(RecipeCatalog(data).get('fixture').maturity, 'experimental')
        data['recipes'][0]['verification']='not_run'
        self.assertEqual(RecipeCatalog(data).get('fixture').maturity, 'reference')
        data['recipes'][0].update(verification='browser', maturity='experimental')
        self.assertEqual(RecipeCatalog(data).search(verification='browser')[0].maturity, 'experimental')
        for invalid in ('production', None, [], True):
            data['recipes'][0]['maturity']=invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError): RecipeCatalog(data)

    def test_packaged_catalog_search_ranking_filters_and_scopes(self):
        catalog = RecipeCatalog()
        self.assertEqual(len(catalog.recipes), 314)
        self.assertEqual(catalog.search('ДВЕ кнопки')[0].id, 'two-columns')
        self.assertEqual(catalog.search('три кнопки')[0].id, 'three-columns')
        self.assertEqual(catalog.search()[0].id, 'two-columns')
        self.assertEqual(len(catalog.search(category='keyboards', limit=1000)), 11)
        self.assertEqual(len(catalog.search(language='typescript', limit=1000)), 99)
        self.assertEqual(len(catalog.search(verification='mock')), 19)
        self.assertEqual(catalog.search(verification='live'), ())
        self.assertEqual(catalog.search('токен_НЕТ_РЕЦЕПТА'), ())
        self.assertEqual(catalog.get('api.sendPhoto').verification, 'sdk')
        self.assertEqual(catalog.get('native.showPopup').verification, 'not_run')
        self.assertNotIn('network', catalog.get('api.sendPhoto').preview or {})

    def test_preview_copy_and_record_immutability(self):
        recipe = RecipeCatalog().get('two-columns')
        preview = recipe.preview; preview['inline_keyboard'][0][0]['text'] = 'modified'
        self.assertEqual(recipe.preview['inline_keyboard'][0][0]['text'], 'Каталог')
        with self.assertRaises(AttributeError): recipe.title = 'modified'

    def test_invalid_schema_duplicates_urls_and_query(self):
        resource = {'schema_version':1,'library_version':'0.5.0','recipes':[{
            'id':'fixture','title':'Fixture','summary':'fixture','category':'keyboards','language':'python','keywords':[],
            'code':'pass','verification':'sdk','scope':'fixture','sources':['https://core.telegram.org/bots/api']} ]}
        for mutation in ('duplicate', 'url', 'verification', 'schema'):
            data=json.loads(json.dumps(resource))
            if mutation=='duplicate':data['recipes']*=2
            elif mutation=='url':data['recipes'][0]['sources']=['javascript:alert(1)']
            elif mutation=='verification':data['recipes'][0]['verification']='all_works'
            else:data['schema_version']=2
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): RecipeCatalog(data)
        for query, limit in (('x'*513,20),('',True),('',0),('',1001)):
            with self.assertRaises(ValueError): RecipeCatalog().search(query, limit=limit)
        with self.assertRaises(KeyError): RecipeCatalog().get('missing')


class StarterTests(unittest.TestCase):
    def source(self, root):
        source=root/'local library'; source.mkdir()
        (source/'pyproject.toml').write_text('[project]\nname="awesome-telegram-patterns"\nversion="0.5.0"\n',encoding='utf-8')
        return source

    def test_mini_app_local_path_preserves_spaces_unicode_and_literal_percent(self):
        with tempfile.TemporaryDirectory(prefix='telegram-starter-') as folder:
            root = Path(folder).resolve(); source = self.source(root)  # canonical: macOS temp dirs cross /var -> /private/var
            supplied = root / 'local artifacts %20 Пример'; supplied.mkdir()
            tarball = supplied / 'patterns.tgz'
            metadata = json.dumps({'name': '@awesome-telegram/patterns', 'version': '0.5.0'}).encode()
            with tarfile.open(tarball, 'w:gz') as archive:
                member = tarfile.TarInfo('package/package.json'); member.size = len(metadata)
                archive.addfile(member, io.BytesIO(metadata))
            target = root / 'first project'
            plan = create_starter(target, library=source, template='bot-mini-app', typescript=tarball, dry_run=True)
            self.assertFalse(plan.created); self.assertFalse(target.exists())
            create_starter(target, library=source, template='bot-mini-app', typescript=tarball)
            package = json.loads((target / 'mini-app/package.json').read_text(encoding='utf-8'))
            self.assertEqual(package['dependencies']['@awesome-telegram/patterns'], 'file:' + tarball.as_posix())
            import tomllib
            python = tomllib.loads((target / 'pyproject.toml').read_text(encoding='utf-8'))
            self.assertEqual(python['project']['dependencies'], ['awesome-telegram-patterns[aiogram] @ ' + source.as_uri()])
            config = json.loads((target / '.telegram-patterns.json').read_text(encoding='utf-8'))
            self.assertEqual(config['typescript_uri'], tarball.as_uri())

    def test_dry_run_new_project_and_exclusive_creation(self):
        with tempfile.TemporaryDirectory(prefix='telegram-starter-') as folder:
            root=Path(folder).resolve(); source=self.source(root); target=root/'my bot'
            plan=create_starter(target,library=source,dry_run=True)
            self.assertFalse(plan.created);self.assertFalse(target.exists())
            plan=create_starter(target,library=source)
            self.assertTrue(plan.created);self.assertEqual(len(plan.files),7)
            import tomllib
            manifest=tomllib.loads((target/'pyproject.toml').read_text(encoding='utf-8'))
            self.assertIn(source.as_uri(),manifest['project']['dependencies'][0])
            self.assertNotIn('SECRET',(target/'.env.example').read_text(encoding='utf-8'))
            self.assertIn('.env',(target/'.gitignore').read_text())
            before={path.name:path.read_bytes() for path in target.iterdir()}
            self.assertRaises(FileExistsError,create_starter,target,library=source)
            self.assertEqual(before,{path.name:path.read_bytes() for path in target.iterdir()})
            empty=root/'existing-empty';empty.mkdir();self.assertRaises(FileExistsError,create_starter,empty,library=source)

    def test_missing_parent_bad_source_and_missing_typescript_do_not_create(self):
        with tempfile.TemporaryDirectory(prefix='telegram-starter-') as folder:
            root=Path(folder);source=self.source(root);target=root/'bot'
            self.assertRaises(ValueError,create_starter,root/'missing/child',library=source)
            self.assertRaises(ValueError,create_starter,target,library=source,template='bot-mini-app')
            (source/'pyproject.toml').write_text('[project]\nname="other-package"\nversion="0.5.0"\n')
            self.assertRaises(ValueError,create_starter,target,library=source)
            self.assertFalse(target.exists())

    def test_target_link_is_rejected_and_content_preserved(self):
        with tempfile.TemporaryDirectory(prefix='telegram-starter-') as folder:
            root=Path(folder);source=self.source(root);real=root/'real';real.mkdir();target=root/'linked'
            (real/'keep.txt').write_text('owned')
            try: target.symlink_to(real,target_is_directory=True)
            except OSError as error:self.skipTest('Directory links unavailable: '+type(error).__name__)
            self.assertRaises(FileExistsError,create_starter,target,library=source)
            self.assertEqual((real/'keep.txt').read_text(),'owned')

    def test_generated_bot_same_dispatcher_runs_without_network(self):
        with tempfile.TemporaryDirectory(prefix='telegram-generated-') as folder:
            root=Path(folder);target=root/'bot'
            create_starter(target,library=ROOT/'packages/python')
            env=dict(os.environ);env.pop('BOT_TOKEN',None);env['PYTHONUTF8']='1'
            result=subprocess.run([sys.executable,str(target/'offline.py')],cwd=target,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            evidence=json.loads(result.stdout)
            self.assertTrue(evidence['passed']);self.assertFalse(evidence['network']);self.assertTrue(evidence['session_closed'])


class CLITests(unittest.TestCase):
    def test_maturity_filter_and_show_are_visible_to_consumer(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['recipes','--maturity','reference','--verification','mock']),0)
        self.assertEqual(json.loads(output.getvalue())['recipes'],[])
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['recipes','две кнопки','--maturity','experimental']),0)
        self.assertEqual(json.loads(output.getvalue())['recipes'][0]['maturity'],'experimental')
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['recipes','--show','api.sendPhoto']),0)
        self.assertIn('reference / sdk',output.getvalue())

    def test_search_show_and_controlled_invalid_artifact(self):
        with redirect_stdout(io.StringIO()) as output:self.assertEqual(main(['recipes','две кнопки']),0)
        self.assertEqual(json.loads(output.getvalue())['recipes'][0]['id'],'two-columns')
        with redirect_stdout(io.StringIO()) as output:self.assertEqual(main(['recipes','--show','two-columns']),0)
        self.assertIn('inline_keyboard',output.getvalue())
        with tempfile.TemporaryDirectory(prefix='telegram-cli-') as folder:
            root=Path(folder);artifact=root/'bad.whl';artifact.write_bytes(b'INVALID_FIXTURE')
            with redirect_stderr(io.StringIO()) as output:self.assertEqual(main(['init',str(root/'target'),'--library',str(artifact)]),2)
            self.assertNotIn('INVALID_FIXTURE',output.getvalue());self.assertFalse((root/'target').exists())

    def test_errors_are_readable_by_default_and_json_on_request(self):
        import shutil
        from importlib.resources import files
        library=ROOT/'packages/python'  # library source directory, independent of how the package is installed
        with tempfile.TemporaryDirectory(prefix='telegram-cli-errors-') as folder:
            root=Path(folder);artifact=root/'bad.whl';artifact.write_bytes(b'INVALID_FIXTURE')
            def run(*arguments):
                with redirect_stderr(io.StringIO()) as output:status=main(list(arguments))
                return status,output.getvalue()
            status,text=run('init',str(root/'a'),'--library',str(artifact))
            self.assertEqual(status,2);self.assertNotIn('INVALID_FIXTURE',text)
            self.assertIn('Ошибка: Переданный wheel или tarball поврежден',text);self.assertIn('добавьте --json',text)
            with self.assertRaises(json.JSONDecodeError): json.loads(text)
            status,text=run('init',str(root/'a'),'--library',str(artifact),'--json')
            payload=json.loads(text);self.assertEqual((status,payload['problem'],payload['error']),(2,'artifact','BadZipFile'))
            self.assertTrue(text.isascii())
            (root/'exists').mkdir()
            status,text=run('init',str(root/'exists'),'--library',str(library))
            self.assertIn('Ошибка: Каталог проекта уже существует.',text)
            status,text=run('init','--component','x')
            self.assertIn('Ошибка: Нужны новый target и --library',text);self.assertIn('Что сделать: Исправьте аргументы',text)
            # A wheel missing a bundled template is an installation problem, not an unknown outcome.
            package=root/'package';shutil.copytree(Path(str(files('telegram_patterns'))),package)
            (package/'resources/starter/README.md.txt').unlink()
            with patch('telegram_patterns.cli.files',return_value=package),patch('telegram_patterns.starter.files',return_value=package):
                status,text=run('init',str(root/'b'),'--library',str(library),'--json')
                payload=json.loads(text)
                self.assertEqual((payload['problem'],payload['failure']['outcome']),('installation','read-failed'))
                status,text=run('init',str(root/'b'),'--library',str(library))
            self.assertIn('Пакет установлен не полностью',text);self.assertNotIn('частично',text)
            self.assertFalse((root/'b').exists())
        legacy=io.TextIOWrapper(io.BytesIO(),encoding='ascii')
        with redirect_stderr(legacy):self.assertEqual(main(['init','--component','x']),2)
        legacy.flush();self.assertIn(b'\\u041e',legacy.buffer.getvalue())

    def test_doctor_local_read_only_and_token_never_printed(self):
        with tempfile.TemporaryDirectory(prefix='telegram-doctor-') as folder:
            root=Path(folder);(root/'pyproject.toml').write_text('[project]\nname="fixture"\n')
            (root/'.env').write_text('BOT_TOKEN=SECRET_FROM_FILE')
            before={p.name:p.read_bytes() for p in root.iterdir()}
            with patch.dict(os.environ,{'BOT_TOKEN':'100:SECRET_FROM_ENV'}): report=doctor(root,require_token=True)
            self.assertTrue(report['passed']);self.assertFalse(report['network']);self.assertNotIn('SECRET',json.dumps(report))
            with patch.dict(os.environ,{'BOT_TOKEN':''}): report=doctor(root,require_token=True)
            self.assertFalse(report['passed'])
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})

    def test_doctor_invalid_project_data_is_controlled(self):
        with tempfile.TemporaryDirectory(prefix='telegram-doctor-') as folder:
            root=Path(folder);(root/'pyproject.toml').write_text('SECRET_INVALID_TOML')
            report=doctor(root)
            self.assertFalse(report['passed']);self.assertNotIn('SECRET',json.dumps(report))


class GalleryGeneratorTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('gallery_builder',ROOT/'scripts/build_recipe_gallery.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_real_generation_in_temp_directory_check_and_drift(self):
        builder=self.module()
        with tempfile.TemporaryDirectory(prefix='telegram-gallery-') as folder:
            output=Path(folder)/'site'
            with patch('sys.argv',['builder','--output-dir',str(output)]),redirect_stdout(io.StringIO()):builder.main()
            self.assertTrue((output/'index.html').is_file());self.assertTrue((output/'gallery.js').is_file())
            self.assertEqual(len(json.loads((output/'recipes.json').read_text(encoding='utf-8'))['recipes']),314)
            with patch('sys.argv',['builder','--output-dir',str(output),'--check']),redirect_stdout(io.StringIO()):builder.main()
            (output/'index.html').write_text('drift')
            with patch('sys.argv',['builder','--output-dir',str(output),'--check']),self.assertRaisesRegex(ValueError,'drift'):builder.main()
            self.assertEqual((output/'index.html').read_text(),'drift')

    def test_script_closing_tag_is_escaped_without_corrupting_json(self):
        payload={'schema_version':1,'recipes':[{'title':'</script><img src=x onerror=alert(1)>'}]}
        html=self.module().render_html(payload)
        self.assertNotIn('</script><img',html)
        embedded=html.split('<script id="recipe-data" type="application/json">')[1].split('</script>')[0]
        self.assertEqual(json.loads(embedded),payload)
