import base64
import csv
import io
import json
import hashlib
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
import warnings
import zipfile

from scripts.verify_distribution_contract import DistributionViolation, _read_archive, verify_distributions


class DistributionContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='distribution-contract-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.wheel = self.root / 'fixture.whl'
        self.tarball = self.root / 'fixture.tgz'
        self.prefix = 'awesome_telegram_patterns-0.9.0.dist-info/'
        self.py_source = {'telegram_patterns/__init__.py':b"__version__ = '0.9.0'\n__all__=[]\n", 'telegram_patterns/py.typed':b'',
                          'telegram_patterns/resources/recipes.json':b'{"library_version":"0.9.0"}\n'}
        self.license = b'MIT License\nfixture\n'
        self.ts_manifest = {'name':'@awesome-telegram/patterns','version':'0.9.0','type':'module','license':'MIT','sideEffects':['**/*.css'],
            'exports':{'.':{'types':'./dist/index.d.ts','import':'./dist/index.js'},'./styles.css':'./src/styles.css'}}
        self.ts_files = {'package/package.json':json.dumps(self.ts_manifest).encode(),'package/README.md':b'fixture\n','package/LICENSE':self.license,
                        'package/src/styles.css':b'.fixture{color:red}\n','package/dist/index.js':b'export const fixture=1;\n',
                        'package/dist/index.d.ts':b'export declare const fixture: number;\n'}
        self.write('packages/python/pyproject.toml', b'[project]\nname="awesome-telegram-patterns"\nversion="0.9.0"\nrequires-python=">=3.11"\nlicense="MIT"\nlicense-files=["LICENSE"]\ndependencies=[]\n[project.scripts]\ntelegram-patterns="telegram_patterns.cli:main"\n')
        self.write('packages/python/LICENSE',self.license)
        for name, value in self.py_source.items(): self.write('packages/python/src/'+name,value)
        for name, value in self.ts_files.items(): self.write('packages/typescript/'+name.removeprefix('package/'),value)
        self.write('packages/typescript/src/index.ts',b'export const fixture=1;\n')
        self.zip()
        self.tar()

    def write(self, relative, value):
        target=self.root/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(value)

    def zip(self, mutate=None):
        values={**self.py_source,
          self.prefix+'METADATA':b'Name: awesome-telegram-patterns\nVersion: 0.9.0\nRequires-Python: >=3.11\nLicense-Expression: MIT\nLicense-File: LICENSE\nRequires-Dist: aiogram<4,>=3.31; extra == "aiogram"\nRequires-Dist: tzdata<2027,>=2026.5; extra == "calendar"\nRequires-Dist: cryptography<52,>=46; extra == "signature"\nRequires-Dist: python-telegram-bot<23,>=22.8; extra == "ptb"\n\n',
          self.prefix+'WHEEL':b'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
          self.prefix+'entry_points.txt':b'[console_scripts]\ntelegram-patterns = telegram_patterns.cli:main\n',
          self.prefix+'top_level.txt':b'telegram_patterns\n',self.prefix+'licenses/LICENSE':self.license}
        if mutate: mutate(values)
        output=io.StringIO();writer=csv.writer(output,lineterminator='\n')
        for name,value in values.items():
            writer.writerow([name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(value).digest()).rstrip(b'=').decode(),str(len(value))])
        writer.writerow([self.prefix+'RECORD','',''])
        values[self.prefix+'RECORD']=output.getvalue().encode()
        with zipfile.ZipFile(self.wheel,'w') as archive:
            for name,value in values.items(): archive.writestr(name,value)

    def tar(self, mutate=None):
        values=dict(self.ts_files)
        if mutate: mutate(values)
        with tarfile.open(self.tarball,'w:gz') as archive:
            for name,value in values.items():
                item=tarfile.TarInfo(name);item.size=len(value);archive.addfile(item,io.BytesIO(value))

    def verify(self): return verify_distributions(self.root,self.wheel,self.tarball)

    def test_valid_archives_and_cli_in_real_temporary_tree_do_not_extract_or_replace_files(self):
        marker=self.root/'owned.txt';marker.write_text('preserve',encoding='utf-8')
        before={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        report=self.verify();self.assertTrue(report['wheel']['record_verified']);self.assertFalse(report['extracts_files'])
        result=subprocess.run([sys.executable,'scripts/verify_distribution_contract.py','--root',str(self.root),
            '--wheel',str(self.wheel),'--tarball',str(self.tarball)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(result.stdout)['passed'])
        after={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_missing_python_resource_or_typing_marker_is_rejected_even_with_valid_record(self):
        for name in ('telegram_patterns/resources/recipes.json','telegram_patterns/py.typed'):
            with self.subTest(name=name):
                self.zip(lambda values:values.pop(name))
                with self.assertRaises(DistributionViolation): self.verify()

    def test_recomputed_record_cannot_hide_tampered_source_or_an_extra_secret_file(self):
        self.zip(lambda values:values.update({'telegram_patterns/__init__.py':b'changed'}))
        with self.assertRaisesRegex(DistributionViolation,'bytes mismatch'): self.verify()
        self.zip(lambda values:values.update({'.env':b'private fixture token'}))
        with self.assertRaisesRegex(DistributionViolation,'undeclared'): self.verify()

    def test_missing_or_changed_license_is_rejected(self):
        self.zip(lambda values: values.pop(self.prefix+'licenses/LICENSE'))
        with self.assertRaisesRegex(DistributionViolation,'missing or undeclared'): self.verify()
        self.zip(lambda values: values.update({self.prefix+'licenses/LICENSE':b'Other\n'}))
        with self.assertRaisesRegex(DistributionViolation,'license'): self.verify()
        self.zip()
        self.tar(lambda values: values.update({'package/package.json':json.dumps({**self.ts_manifest,'license':'GPL-3.0'}).encode()}))
        self.write('packages/typescript/package.json',json.dumps({**self.ts_manifest,'license':'GPL-3.0'}).encode())
        with self.assertRaisesRegex(DistributionViolation,'license'): self.verify()

    def test_record_digest_tampering_is_detected(self):
        with zipfile.ZipFile(self.wheel) as archive: values={item.filename:archive.read(item) for item in archive.infolist()}
        record=self.prefix+'RECORD';values[record]=values[record].replace(b'sha256=',b'sha512=',1)
        with zipfile.ZipFile(self.wheel,'w') as archive:
            for name,value in values.items(): archive.writestr(name,value)
        with self.assertRaisesRegex(DistributionViolation,'RECORD digest'): self.verify()

    def test_css_declaration_missing_and_stale_dist_module_are_rejected(self):
        for change in (lambda values:values.pop('package/src/styles.css'),lambda values:values.pop('package/dist/index.d.ts'),
                       lambda values:values.update({'package/dist/removed.js':b'old module'})):
            self.tar(change)
            with self.assertRaisesRegex(DistributionViolation,'undeclared'): self.verify()
        self.tar(lambda values:values.update({'package/src/styles.css':b'wrong CSS'}))
        with self.assertRaisesRegex(DistributionViolation,'bytes differ'): self.verify()

    def test_traversal_duplicates_links_and_special_members_are_rejected(self):
        for name in ('../outside.txt','/absolute.txt','package/../outside.txt','package\\secret','C:/secret','package//secret'):
            with self.subTest(name=name):
                self.tar(lambda values:values.update({name:b'fixture'}))
                with self.assertRaisesRegex(DistributionViolation,'unsafe'): _read_archive(self.tarball,wheel=False)
        with tarfile.open(self.tarball,'w:gz') as archive:
            item=tarfile.TarInfo('package/link');item.type=tarfile.SYMTYPE;item.linkname='../outside';archive.addfile(item)
        with self.assertRaisesRegex(DistributionViolation,'link'): _read_archive(self.tarball,wheel=False)
        with zipfile.ZipFile(self.wheel,'w') as archive:
            item=zipfile.ZipInfo('telegram_patterns/link');item.external_attr=(stat.S_IFLNK|0o777)<<16;archive.writestr(item,b'../outside')
        with self.assertRaisesRegex(DistributionViolation,'non-regular'): _read_archive(self.wheel,wheel=True)
        with tarfile.open(self.tarball,'w:gz') as archive:
            for _ in range(2):
                item=tarfile.TarInfo('package/duplicate');item.size=1;archive.addfile(item,io.BytesIO(b'x'))
        with self.assertRaisesRegex(DistributionViolation,'Duplicate'): _read_archive(self.tarball,wheel=False)
        with zipfile.ZipFile(self.wheel,'w') as archive, warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            archive.writestr('telegram_patterns/duplicate',b'x')
            archive.writestr('telegram_patterns/duplicate',b'x')
        with self.assertRaisesRegex(DistributionViolation,'Duplicate'): _read_archive(self.wheel,wheel=True)

    def test_bad_version_and_dependency_boundary_are_rejected(self):
        self.zip(lambda values:values.update({self.prefix+'METADATA':values[self.prefix+'METADATA'].replace(b'0.9.0',b'9.9.9')}))
        with self.assertRaisesRegex(DistributionViolation,'identity mismatch'): self.verify()
        self.zip(lambda values:values.update({self.prefix+'METADATA':values[self.prefix+'METADATA'].replace(b'\n\n',b'\nRequires-Dist: unexpected\n\n')}))
        with self.assertRaisesRegex(DistributionViolation,'dependency boundary'): self.verify()

    def test_module_version_must_match_pyproject(self):
        self.write('packages/python/src/telegram_patterns/__init__.py', b"__version__ = '9.9.9'\n__all__=[]\n")
        with self.assertRaisesRegex(DistributionViolation, r'__version__ differs'): self.verify()
        self.write('packages/python/src/telegram_patterns/__init__.py', b'__all__=[]\n')
        with self.assertRaisesRegex(DistributionViolation, r'__version__ differs'): self.verify()


if __name__=='__main__': unittest.main()
