"""Exercise verifier preflight against real temporary directories and links."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ServiceVerifierTests(unittest.TestCase):
    def invoke(self,wheel,output):
        return subprocess.run([sys.executable,str(ROOT/'scripts/verify_service_bot.py'),'--wheel',str(wheel),'--output',str(output)],
            cwd=ROOT,capture_output=True,text=True,timeout=30)

    def test_existing_output_preserves_owned_notes_before_build_or_install(self):
        with tempfile.TemporaryDirectory(prefix='service-verifier-existing-') as folder:
            root=Path(folder);wheel=root/'provided.whl';wheel.write_bytes(b'not needed: existing output refuses first')
            output=root/'proof';output.mkdir();marker=output/'owned.txt';marker.write_bytes(b'preserve')
            result=self.invoke(wheel,output)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(marker.read_bytes(),b'preserve')
            self.assertEqual([p.name for p in output.iterdir()],['owned.txt'])

    def test_output_parent_link_refused_without_touching_real_target(self):
        with tempfile.TemporaryDirectory(prefix='service-verifier-links-') as folder:
            root=Path(folder).resolve();target=root/'target';target.mkdir();link=root/'link'
            wheel=root/'provided.whl';wheel.write_bytes(b'never install this fixture')
            marker=target/'owned.txt';marker.write_bytes(b'preserve')
            try:
                if os.name=='nt':
                    made=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True,timeout=10)
                    if made.returncode:self.skipTest('Directory junction unavailable')
                else:link.symlink_to(target,target_is_directory=True)
                result=self.invoke(wheel,link/'proof')
                self.assertNotEqual(result.returncode,0)
                self.assertIn('Output links are not supported',result.stderr)
                self.assertEqual(marker.read_bytes(),b'preserve')
                self.assertEqual([p.name for p in target.iterdir()],['owned.txt'])
            finally:
                if link.exists():
                    assert link.absolute().is_relative_to(root)
                    if os.name=='nt':link.rmdir()
                    else:link.unlink()


if __name__=='__main__':unittest.main()
