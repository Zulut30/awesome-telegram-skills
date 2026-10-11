"""Generated artifacts must not influence validation of current source files."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from scripts.validate_skills import validate


class SkillSourceValidationTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows junction traversal regression')
    def test_directory_junction_does_not_expand_the_validation_scope(self):
        with tempfile.TemporaryDirectory(prefix='skill junction validation ') as temporary:
            base=Path(temporary);root=base/'repo';(root/'.agents/skills').mkdir(parents=True)
            outside=base/'outside';outside.mkdir()
            (outside/'broken.md').write_text('[bad](missing.md)',encoding='utf-8')
            link=root/'linked'
            done=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True)
            self.assertEqual(done.returncode,0)
            count,errors=validate(root)
            self.assertEqual(count,0)
            self.assertEqual(errors,['No skill folders found'])
            # Exercise traversal independently: empty skills validation returns early.
            from scripts.validate_skills import source_files
            self.assertEqual(list(source_files(root)),[])

    def test_generated_failures_are_ignored_but_source_failures_are_reported(self):
        with tempfile.TemporaryDirectory(prefix='skill validation ') as temporary:
            root=Path(temporary)
            skill=root/'.agents/skills/test-skill';(skill/'agents').mkdir(parents=True)
            (skill/'SKILL.md').write_text('---\nname: test-skill\ndescription: Проверка самостоятельного навыка.\n---\nИнструкции.\n',encoding='utf-8')
            (skill/'agents/openai.yaml').write_text('interface:\n  display_name: Test\n  short_description: "Проверить структуру одного навыка"\n  default_prompt: "$test-skill Проверь структуру"\n',encoding='utf-8')
            for name in ['output/archive','node_modules/dependency','packages/python/build','dist','temporary.egg-info']:
                folder=root/name;folder.mkdir(parents=True)
                (folder/'broken.md').write_text('[bad](missing.md)',encoding='utf-8')
                (folder/'broken.py').write_text('def invalid syntax',encoding='utf-8')
            self.assertEqual(validate(root),(1,[]))
            (root/'README.md').write_text('[bad](missing.md)',encoding='utf-8')
            (root/'source.py').write_text('def invalid syntax',encoding='utf-8')
            count,errors=validate(root)
            self.assertEqual(count,1);self.assertEqual(len(errors),2)
            self.assertTrue(any('README.md' in error for error in errors))
            self.assertTrue(any('source.py' in error for error in errors))
