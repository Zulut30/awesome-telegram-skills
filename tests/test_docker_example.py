"""Keep the optional service-bot container safe without requiring Docker for the test suite."""
from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest import mock

try:
    import yaml
except ImportError:  # CI installs PyYAML; a bare local run skips only the Compose parse
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/service-bot'


class DockerExampleTests(unittest.TestCase):
    def test_dockerfile_runs_unprivileged_with_database_on_volume(self):
        dockerfile = (EXAMPLE / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('USER bot', dockerfile)
        self.assertIn('VOLUME /data', dockerfile)
        self.assertIn('"--database", "/data/service.sqlite"', dockerfile)
        self.assertIn('--mount=type=secret,id=ca,required=false', dockerfile)
        self.assertNotIn('BOT_TOKEN', dockerfile)

    @unittest.skipIf(yaml is None, 'PyYAML is not installed')
    def test_compose_reads_token_from_ignored_env_file(self):
        compose = yaml.safe_load((EXAMPLE / 'compose.yaml').read_text(encoding='utf-8'))
        service = compose['services']['service-bot']
        self.assertEqual(service['build']['context'], '../..')
        self.assertEqual(service['env_file'], [{'path': '.env', 'required': True}])
        self.assertEqual(service['volumes'], ['service-data:/data'])
        self.assertNotIn('environment', service)
        self.assertNotIn('ports', service)
        ignored = (ROOT / '.dockerignore').read_text(encoding='utf-8').split()
        self.assertIn('**/.env', ignored)
        self.assertIn('.git', ignored)
        example = (EXAMPLE / '.env.example').read_text(encoding='utf-8')
        self.assertIn('BOT_TOKEN=123456789:REPLACE_WITH_YOUR_TEST_BOT_TOKEN', example)

    def test_documentation_calls_docker_optional(self):
        readme = (EXAMPLE / 'README.md').read_bytes()
        self.assertIn('## Docker (необязательно)'.encode(), readme)
        for copy in ('docs/service-bot.md', '.agents/skills/telegram-code-patterns/references/service-bot.md'):
            self.assertEqual((ROOT / copy).read_bytes(), readme, copy)

    def test_verifier_refuses_existing_env_before_docker(self):
        spec = importlib.util.spec_from_file_location('verify_docker_example', ROOT / 'scripts/verify_docker_example.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='docker-env-') as folder:
            env_file = Path(folder) / '.env'
            env_file.write_text('BOT_TOKEN=1:real-looking\n', encoding='utf-8')
            with mock.patch.object(module, 'EXAMPLE', Path(folder)), mock.patch('sys.argv', ['verify']), \
                    mock.patch.object(module.subprocess, 'run') as run, mock.patch('sys.stderr'), \
                    self.assertRaises(SystemExit) as exit_info:
                module.main()
            self.assertEqual(exit_info.exception.code, 2)
            run.assert_not_called()
            self.assertEqual(env_file.read_text(encoding='utf-8'), 'BOT_TOKEN=1:real-looking\n')


if __name__ == '__main__':
    unittest.main()
