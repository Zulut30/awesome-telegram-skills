"""Exercise real timed-out child output and report preservation in an owned temp root."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts import verify_pattern_packages as verifier


class PackageVerificationTests(unittest.TestCase):
    def test_actual_timeout_keeps_both_streams_and_failed_stage_report(self):
        with tempfile.TemporaryDirectory(prefix='package verifier timeout ') as temporary:
            root=Path(temporary)
            def write(name,text):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
            write('packages/python/pyproject.toml','[project]\nname="awesome-telegram-patterns"\nversion="0.0.1"\n')
            write('packages/typescript/package.json',json.dumps({'name':'@awesome-telegram/patterns','version':'0.0.1'}))
            write('components.json',json.dumps({'library_version':'0.0.1','components':[]}))
            write('examples/mini-app/package.json',json.dumps({'dependencies':{'@awesome-telegram/patterns':'0.0.1'}}))
            consumer=root/'consumer';consumer.mkdir()
            original_run=verifier.run_command
            def real_timeout(command,**kwargs):
                self.assertEqual(kwargs['timeout'],180)
                self.assertEqual(kwargs['cwd'],root)
                return original_run([sys.executable,'-u','-c',
                    "import sys,time;print('stdout preserved',flush=True);print('stderr preserved',file=sys.stderr,flush=True);time.sleep(10)"],
                    **(kwargs|{'timeout':0.5}))
            with patch.object(verifier,'ROOT',root),patch.object(sys,'argv',['verify-pattern-packages']),                    patch.object(verifier.shutil,'which',return_value=sys.executable),                    patch.object(verifier.tempfile,'mkdtemp',return_value=str(consumer)),                    patch.object(verifier,'run_command',side_effect=real_timeout):
                with self.assertRaisesRegex(RuntimeError,'partial output saved'):verifier.main()
            output=root/'output/pattern-library-0.0.1'
            log=(output/'workspace-build.log').read_text(encoding='utf-8')
            self.assertIn('stdout preserved',log);self.assertIn('stderr preserved',log);self.assertIn('TIMEOUT',log)
            report=json.loads((output/'distribution-report.json').read_text(encoding='utf-8'))
            self.assertFalse(report['passed']);self.assertEqual(report['stages'][0]['exit_code'],124)
            self.assertTrue(report['stages'][0]['timed_out']);self.assertEqual(report['stages'][0]['timeout_seconds'],0.5)

    def test_named_existing_report_directory_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(prefix='package verifier existing ') as temporary:
            output=Path(temporary)/'report';output.mkdir()
            marker=output/'distribution-report.json';marker.write_bytes(b'original evidence')
            with patch.object(sys,'argv',['verify-pattern-packages','--output',str(output)]):
                with self.assertRaises(FileExistsError): verifier.main()
            self.assertEqual(marker.read_bytes(),b'original evidence')


if __name__=='__main__':unittest.main()
