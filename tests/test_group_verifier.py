"""Group verifier refuses owned output and junctions before build/install."""
import subprocess
import sys
import test_service_verifier


class GroupVerifierTests(test_service_verifier.ServiceVerifierTests):
    def invoke(self,wheel,output):
        return subprocess.run([sys.executable,str(test_service_verifier.ROOT/'scripts/verify_group_bot.py'),'--wheel',str(wheel),'--output',str(output)],cwd=test_service_verifier.ROOT,capture_output=True,text=True,timeout=30)
