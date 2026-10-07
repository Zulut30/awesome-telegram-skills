"""Общий список переменных окружения скриптов проверки: прокси и CA проходят, секреты — нет."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('_environment', ROOT / 'scripts/_environment.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class MinimalEnvironmentTests(unittest.TestCase):
    def test_tools_get_proxies_and_trust_but_never_secrets(self):
        source = {'PATH': '/bin', 'HOME': '/home/u', 'TMPDIR': '/tmp', 'https_proxy': 'http://proxy:8080',
                  'NO_PROXY': 'localhost', 'SSL_CERT_FILE': '/ca.pem', 'NODE_EXTRA_CA_CERTS': '/ca.pem',
                  'PLAYWRIGHT_BROWSERS_PATH': '/opt/pw', 'SystemRoot': 'C:\\Windows',
                  'BOT_TOKEN': '100:SECRET', 'PAYMENT_SECRET': 'x', 'PYTHONPATH': '/evil', 'NODE_OPTIONS': '--require x'}
        environment = module.minimal_environment(source=source)
        for name in ('PATH', 'HOME', 'TMPDIR', 'https_proxy', 'NO_PROXY', 'SSL_CERT_FILE', 'NODE_EXTRA_CA_CERTS',
                     'PLAYWRIGHT_BROWSERS_PATH', 'SystemRoot'):
            self.assertIn(name, environment)
        for name in ('BOT_TOKEN', 'PAYMENT_SECRET', 'PYTHONPATH', 'NODE_OPTIONS'):
            self.assertNotIn(name, environment)
        self.assertEqual(module.minimal_environment(['custom_flag'], source={'CUSTOM_FLAG': '1'}), {'CUSTOM_FLAG': '1'})


if __name__ == '__main__':
    unittest.main()
