"""Verify actual timeout cleanup with a real descendant in an owned temporary tree."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from scripts.verification_process import run_command, save_consumer_diagnostics


class VerificationProcessTests(unittest.TestCase):
    def test_nested_diagnostics_survive_without_installations_or_project_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);consumer=root/'consumer';consumer.mkdir()
            for relative, content in [('gallery/browser/report.json',b'{"passed":false}'),
                                      ('gallery/browser/phone.png',b'actual image bytes'),
                                      ('reference/failed.log',b'failure details'),
                                      ('sdk/private.log',b'not diagnostics'),
                                      ('project/.env',b'not diagnostics'),
                                      ('project/node_modules/report.json',b'not diagnostics')]:
                path=consumer/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
            destination=root/'saved';save_consumer_diagnostics(consumer,destination)
            self.assertEqual({p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()},
                             {'gallery/browser/report.json','gallery/browser/phone.png','reference/failed.log'})
            self.assertEqual((destination/'reference/failed.log').read_bytes(),b'failure details')

    def test_timeout_keeps_streams_and_stops_descendant(self):
        with tempfile.TemporaryDirectory(prefix='verification process ') as temporary:
            root=Path(temporary)
            child="""from pathlib import Path
import time
Path('ready').write_text('ready')
while not Path('probe').exists(): time.sleep(.02)
Path('survived').write_text('child still running')
"""
            parent="""import subprocess,sys,time
from pathlib import Path
subprocess.Popen([sys.executable,'-c',sys.argv[1]])
while not Path('ready').exists(): time.sleep(.02)
print('parent stdout',flush=True)
print('parent stderr',file=sys.stderr,flush=True)
time.sleep(30)
"""
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                run_command([sys.executable,'-u','-c',parent,child],cwd=root,env=dict(os.environ),timeout=2)
            self.assertIn('parent stdout',caught.exception.output)
            self.assertIn('parent stderr',caught.exception.stderr)
            (root/'probe').write_text('can the child still write?')
            time.sleep(.3)
            self.assertFalse((root/'survived').exists())

    def test_nonzero_exit_retains_both_streams(self):
        with tempfile.TemporaryDirectory() as temporary:
            done=run_command([sys.executable,'-c',"import sys;print('out');print('err',file=sys.stderr);sys.exit(7)"],
                             cwd=Path(temporary),env=dict(os.environ),timeout=5)
            self.assertEqual(done.returncode,7)
            self.assertEqual(done.stdout.strip(),'out')
            self.assertEqual(done.stderr.strip(),'err')
