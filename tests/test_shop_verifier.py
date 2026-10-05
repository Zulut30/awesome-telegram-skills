"""Run shop verifier refusal cases on actual caller files and junctions."""
import subprocess
import sys
import test_service_verifier


class ShopVerifierTests(test_service_verifier.ServiceVerifierTests):
    def invoke(self,wheel,output):
        tarball=wheel.with_suffix('.tgz');tarball.write_bytes(b'never install this refused fixture')
        return subprocess.run([sys.executable,str(test_service_verifier.ROOT/'scripts/verify_shop_example.py'),'--wheel',str(wheel),'--tarball',str(tarball),'--output',str(output)],cwd=test_service_verifier.ROOT,capture_output=True,text=True,timeout=30)
