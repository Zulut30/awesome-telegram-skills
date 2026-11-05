"""Офлайн: подставной YooKassa HTTP, проверка привязки, durable ledger, частичный возврат."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Any

from telegram_patterns.money import Money
from telegram_patterns.outbox import SQLiteOutbox
from telegram_patterns.payment_ledger import (
    PaymentBinding,
    ProviderEvent,
    SQLitePaymentLedger,
)
from telegram_patterns.providers import (
    InvoiceRequest,
    ProviderHttpRequest,
    ProviderHttpResponse,
    RefundRequest,
    YooKassaAdapter,
    YooKassaCreateOptions,
    binding_reference,
)


class OfflineTransport:
    """Только заданные ответы, без сети; это не доказательство настоящей аутентификации."""

    def __init__(self, order: PaymentBinding) -> None:
        self.writes = 0
        self.payment = {
            "id": "offline-payment",
            "status": "succeeded",
            "paid": True,
            "test": True,
            "amount": {
                "value": order.amount.to_decimal(),
                "currency": order.amount.currency,
            },
            "recipient": {"account_id": "offline-shop"},
            "metadata": {
                "telegram_binding": binding_reference(order, "invoice:1"),
                "telegram_operation": "invoice:1",
            },
            "confirmation": {
                "type": "redirect",
                "confirmation_url": "https://example.com/offline-only",
            },
        }
        self.refund = {
            "id": "offline-refund",
            "payment_id": "offline-payment",
            "status": "succeeded",
            "amount": {"value": "2.00", "currency": order.amount.currency},
        }

    async def send(self, request: ProviderHttpRequest) -> ProviderHttpResponse:
        if request.method == "POST":
            self.writes += 1
            if request.url.endswith("/payments"):
                assert request.body is not None
                if json.loads(request.body)["capture"] is False:
                    self.payment["status"] = "waiting_for_capture"
            if request.url.endswith("/capture") or (
                request.url.endswith("/payments")
                and self.payment["status"] == "succeeded"
            ):
                self.payment["status"] = "succeeded"
                self.payment["captured_at"] = "2026-11-05T12:00:00Z"
        data = self.refund if "/refunds" in request.url else self.payment
        return ProviderHttpResponse(200, json.dumps(data).encode("utf-8"))


def apply_verified(ledger: SQLitePaymentLedger, event: ProviderEvent) -> bool:
    # Доверенная функция получает событие только после await адаптера; это не публичный endpoint.
    token = object()

    def verify(raw: object) -> ProviderEvent:
        if raw is not token:
            raise ValueError("Недоверенное событие")
        return event

    return ledger.apply_event(token, verify=verify, now=1793880010).duplicate


def save_intent(
    journal: SQLiteOutbox,
    database: Path,
    scope: str,
    operation_id: str,
    payload: dict[str, Any],
    *,
    now: int,
) -> None:
    # Здесь можно атомарно изменить собственный серверный заказ в той же БД.
    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        journal.enqueue(connection, scope, operation_id, payload, now=now)
        connection.commit()


async def main() -> None:
    order = PaymentBinding(
        "merchant:offline",
        100,
        200,
        "order:offline",
        "yookassa",
        Money(1000, "RUB", 2),
        allow_partial_refunds=True,
    )
    transport = OfflineTransport(order)
    adapter = YooKassaAdapter(
        transport,
        merchant_id=order.merchant_id,
        shop_id="offline-shop",
        secret_key="offline-fixture-not-a-real-key",
        test=True,
    )
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "finance.sqlite"
        ledger = SQLitePaymentLedger(database)
        ledger.initialize()
        journal = SQLiteOutbox(database, max_attempts=1)
        journal.initialize()
        scope = "merchant:offline:bot:100:yookassa"
        account = {
            "shop_id": adapter.shop_id,
            "test": adapter.test,
            "credential_ref": "offline:shop",
        }
        ledger.create_order(order, "invoice:1", now=1793880000)
        invoice_request = InvoiceRequest(
            order, "Офлайн-заказ", "https://example.com/return"
        )
        save_intent(
            journal,
            database,
            scope,
            "invoice:1",
            {
                "binding": asdict(order),
                "invoice_operation_id": "invoice:1",
                "account": account,
                "idempotence_key": binding_reference(order, "invoice:1"),
                "request": {
                    "method": "POST",
                    "path": "payments",
                    "body": {
                        "amount": {
                            "value": order.amount.to_decimal(),
                            "currency": order.amount.currency,
                        },
                        "capture": False,
                        "confirmation": {
                            "type": "redirect",
                            "return_url": invoice_request.return_url,
                        },
                        "description": invoice_request.description,
                        "metadata": {
                            "telegram_binding": binding_reference(order, "invoice:1"),
                            "telegram_operation": "invoice:1",
                        },
                    },
                },
            },
            now=1793880000,
        )
        create_claim = journal.claim(scope, "offline-create-worker", now=1793880001)
        assert create_claim is not None
        ledger.start_operation(
            order, "invoice:1", "offline-worker", check=lambda *_: True, now=1793880001
        )
        created = await adapter.create(
            invoice_request,
            operation_id="invoice:1",
            options=YooKassaCreateOptions(capture=False),
        )
        journal.confirm(
            create_claim,
            {"provider_id": created.provider_id, "state": created.native_state},
            now=1793880002,
        )
        apply_verified(
            ledger,
            await adapter.invoice_event(
                order,
                created.provider_id,
                invoice_operation_id="invoice:1",
                evidence_ref="offline:create",
            ),
        )
        access_before_capture = ledger.has_access(order, now=1793880010).active
        capture_key = adapter.capture_key(
            order,
            created.provider_id,
            invoice_operation_id="invoice:1",
            operation_id="capture:1",
        )
        # В приложении сюда допускает серверная проверка права; ниже только офлайн-фикстура.
        # Весь неизменяемый запрос сохраняется до сети.
        save_intent(
            journal,
            database,
            scope,
            "capture:1",
            {
                "binding": asdict(order),
                "provider_id": created.provider_id,
                "invoice_operation_id": "invoice:1",
                "capture_operation_id": "capture:1",
                "idempotence_key": capture_key,
                "account": account,
                "request": {
                    "method": "POST",
                    "path": "payments/" + created.provider_id + "/capture",
                    "body": {
                        "amount": {
                            "value": order.amount.to_decimal(),
                            "currency": order.amount.currency,
                        }
                    },
                },
            },
            now=1793880010,
        )
        claim = journal.claim(scope, "offline-capture-worker", now=1793880011)
        assert claim is not None
        captured = await adapter.capture(
            order,
            created.provider_id,
            invoice_operation_id="invoice:1",
            operation_id="capture:1",
        )
        journal.confirm(
            claim,
            {
                "provider_id": captured.provider_id,
                "state": captured.native_state,
                "paid_at": captured.paid_at,
            },
            now=1793880012,
        )
        paid = await adapter.payment_event(
            order,
            created.provider_id,
            invoice_operation_id="invoice:1",
            evidence_ref="offline:paid",
        )
        apply_verified(ledger, paid)
        duplicate = apply_verified(ledger, paid)
        ledger.request_refund(
            order,
            created.provider_id,
            "refund:1",
            Money(200, "RUB", 2),
            900,
            check=lambda *_: True,
            now=1793880011,
        )
        ledger.start_operation(
            order, "refund:1", "offline-worker", check=lambda *_: True, now=1793880012
        )
        request = RefundRequest(
            order, created.provider_id, Money(200, "RUB", 2), "invoice:1"
        )
        save_intent(
            journal,
            database,
            scope,
            "refund:1",
            {
                "binding": asdict(order),
                "invoice_operation_id": "invoice:1",
                "refund_operation_id": "refund:1",
                "account": account,
                "idempotence_key": binding_reference(order, "refund:1"),
                "request": {
                    "method": "POST",
                    "path": "refunds",
                    "body": {
                        "payment_id": created.provider_id,
                        "amount": {
                            "value": request.amount.to_decimal(),
                            "currency": request.amount.currency,
                        },
                    },
                },
            },
            now=1793880012,
        )
        refund_claim = journal.claim(scope, "offline-refund-worker", now=1793880013)
        assert refund_claim is not None
        result = await adapter.refund(request, operation_id="refund:1")
        assert result.provider_id is not None
        journal.confirm(
            refund_claim,
            {"provider_id": result.provider_id, "state": result.native_state},
            now=1793880014,
        )
        apply_verified(
            ledger,
            await adapter.refund_event(
                request,
                result.provider_id,
                operation_id="refund:1",
                evidence_ref="offline:refund",
            ),
        )
        charge = ledger.get_charge(order, created.provider_id)
        capture_record = journal.get(scope, "capture:1")
        assert capture_record is not None
        print(
            json.dumps(
                {
                    "mode": "offline-fixture-only",
                    "provider_writes": transport.writes,
                    "access_before_capture": access_before_capture,
                    "capture_journal_state": capture_record.state,
                    "duplicate_payment": duplicate,
                    "refunded_minor_units": charge["refunded"].minor_units,
                    "access_active": ledger.has_access(order, now=1793880020).active,
                    "live_provider_verified": False,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
