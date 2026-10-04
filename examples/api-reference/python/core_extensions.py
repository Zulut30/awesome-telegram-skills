"""Структурные интерфейсы; модель fixture не является платежным протоколом."""
import asyncio
import json
from typing import Mapping
from telegram_patterns import AsyncTransport, ProviderAdapter, RefundProvider

class LocalTransport:
    async def send(self, request: str) -> str:
        return request

class FixtureProvider:
    def __init__(self, transport: AsyncTransport[str, str]): self.transport = transport
    async def create(self, request: str, *, operation_id: str) -> str:
        return await self.transport.send('fixture:' + operation_id)
    async def get(self, provider_id: str) -> str:
        return await self.transport.send(provider_id)
    def verify_event(self, body: bytes, headers: Mapping[str, str]) -> str | None:
        # Проверяемый отказ без выдуманной подписи/доверия к внешнему событию.
        return None
    async def refund(self, request: str, *, operation_id: str) -> str:
        return await self.transport.send('fixture-refund:' + operation_id)

async def main() -> None:
    transport: AsyncTransport[str, str] = LocalTransport()
    implementation = FixtureProvider(transport)
    provider: ProviderAdapter[str, str, str] = implementation
    refunds: RefundProvider[str, str] = implementation
    invoice = await provider.create('public-product', operation_id='server-operation-1')
    assert await provider.get(invoice) == invoice
    assert provider.verify_event(b'untrusted', {}) is None
    assert await refunds.refund(invoice, operation_id='server-refund-1') == 'fixture-refund:server-refund-1'
    # Нет remote effect, provider idempotency, оплаты или выдачи доступа.
    print(json.dumps({'passed': True, 'case': 'core_extensions', 'network': False}))

if __name__ == '__main__': asyncio.run(main())
