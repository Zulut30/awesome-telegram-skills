"""OpenAPI → TypeScript generator: the committed client is current and unsupported contracts are refused."""

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_openapi_types', ROOT / 'scripts/build_openapi_types.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)
CONTRACT = json.loads(generator.SPEC.read_text(encoding='utf-8'))


class OpenApiTypesTests(unittest.TestCase):
    def test_committed_client_matches_the_contract(self):
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/build_openapi_types.py'), '--check'],
                              capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_every_operation_and_schema_reaches_the_client(self):
        text = generator.render(CONTRACT, 'contract')
        for path, item in CONTRACT['paths'].items():
            for method, operation in item.items():
                self.assertIn(f"{operation['operationId']}: {{method: '{method.upper()}', path: '{path}'", text)
        for name in CONTRACT['components']['schemas']:
            self.assertIn(f"  {name}: (value: unknown): {name} =>", text)
        self.assertIn("readonly status: 'awaiting' | 'paid' | 'review';", text)
        self.assertIn('readonly params: {readonly id: string;}', text)

    def test_unsupported_contracts_are_refused(self):
        def schema(name):
            return lambda c: c['components']['schemas'][name]

        cases = {
            'format is not enforced by the client': lambda c: schema('Session')(c)['properties']['token'].update(format='uuid'),
            'open object': lambda c: schema('Policy')(c).pop('additionalProperties'),
            'required without property': lambda c: schema('Policy')(c)['required'].append('missing'),
            'unknown reference': lambda c: schema('Orders')(c)['properties']['orders']['items'].update({'$ref': '#/components/schemas/Nope'}),
            'array without items': lambda c: schema('Orders')(c)['properties']['orders'].pop('items'),
            'non-string enum': lambda c: schema('Currency')(c).update(enum=[1]),
            'duplicate operationId': lambda c: c['paths']['/api/policy']['get'].update(operationId='getCatalog'),
            'undeclared path parameter': lambda c: c['paths']['/api/orders/{id}']['get'].update(parameters=[]),
            'no JSON success response': lambda c: c['paths']['/api/catalog']['get']['responses'].pop('200'),
            'OpenAPI 3.0': lambda c: c.update(openapi='3.0.3'),
        }
        for name, change in cases.items():
            contract = copy.deepcopy(CONTRACT)
            change(contract)
            with self.subTest(name), self.assertRaises(generator.ContractError):
                generator.render(contract, 'contract')


if __name__ == '__main__':
    unittest.main()
