import unittest
from typing import Any

from telegram_patterns import AsyncTransport, ProviderAdapter, safe_error_report


class ExtensionBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_custom_transport_propagates_unknown_write_outcome_without_retry(self):
        class ProjectTransport:
            def __init__(self):
                self.effects = []

            async def send(self, request: str) -> dict[str, Any]:
                self.effects.append(request)
                raise TimeoutError('Fixture lost acknowledgement after effect')

        transport = ProjectTransport()
        contract: AsyncTransport[str, dict[str, Any]] = transport
        with self.assertRaises(TimeoutError) as caught:
            await contract.send('same-operation')
        self.assertEqual(transport.effects, ['same-operation'])
        self.assertEqual(safe_error_report(caught.exception, operation='write').recovery, 'reconcile')

    async def test_provider_need_not_inherit_protocol_or_support_refunds(self):
        class ProjectProvider:
            def __init__(self):
                self.operations = {}

            async def create(self, request: str, *, operation_id: str) -> str:
                self.operations.setdefault(operation_id, request)
                return operation_id

            async def get(self, provider_id: str) -> str:
                return self.operations[provider_id]

            def verify_event(self, body: bytes, headers) -> str | None:
                return None

        provider = ProjectProvider()
        contract: ProviderAdapter[str, str, str] = provider
        identifier = await contract.create('fixture', operation_id='opaque')
        self.assertEqual(await contract.get(identifier), 'fixture')
        self.assertIsNone(contract.verify_event(b'untrusted', {}))
        self.assertFalse(hasattr(provider, 'refund'))


if __name__ == '__main__':
    unittest.main()
