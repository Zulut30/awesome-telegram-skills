"""Fictional signed provider and separate SQLite effects; no network or real payments."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Any

from telegram_patterns.errors import PermissionDenied
from telegram_patterns.money import Money
from telegram_patterns.payment_ledger import (
    PaymentBinding,
    PaymentOperation,
    ProviderEvent,
    SQLitePaymentLedger,
)


class FakeProvider:
    """An invented fixture protocol; this is not Telegram or any payment provider's authentication."""

    key = b"offline-fixture-only-key"

    def __init__(self, database: Path) -> None:
        self.database = database
        with closing(sqlite3.connect(database)) as db, db:
            db.execute(
                "CREATE TABLE effects(operation_id TEXT PRIMARY KEY,body BLOB NOT NULL)"
            )

    def perform(self, operation_id: str, event: ProviderEvent) -> None:
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(
                "INSERT INTO effects VALUES (?,?)",
                (operation_id, json.dumps(asdict(event)).encode()),
            )

    def lookup(self, operation_id: str) -> tuple[bytes, str]:
        with closing(sqlite3.connect(self.database)) as db:
            body = db.execute(
                "SELECT body FROM effects WHERE operation_id=?", (operation_id,)
            ).fetchone()[0]
        return body, hmac.new(self.key, body, hashlib.sha256).hexdigest()

    def verify(self, raw: Any) -> ProviderEvent:
        if (
            not isinstance(raw, tuple)
            or len(raw) != 2
            or not isinstance(raw[0], bytes)
            or not isinstance(raw[1], str)
            or not hmac.compare_digest(
                hmac.new(self.key, raw[0], hashlib.sha256).hexdigest(), raw[1]
            )
        ):
            raise PermissionDenied("Fixture provider authentication failed")
        data = json.loads(raw[0])
        binding = data["binding"]
        binding["amount"] = Money(**binding["amount"])
        data["binding"] = PaymentBinding(**binding)
        if data["amount"] is not None:
            data["amount"] = Money(**data["amount"])
        return ProviderEvent(**data)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="payment-ledger-demo-") as temporary:
        root = Path(temporary)
        ledger = SQLitePaymentLedger(root / "ledger.sqlite")
        ledger.initialize()
        provider = FakeProvider(root / "provider.sqlite")
        binding = PaymentBinding(
            "fixture:test",
            100,
            200,
            "order:1",
            "fictional-provider",
            Money.from_decimal("10.00", "USD", 2),
            allow_partial_refunds=True,
        )
        ledger.create_order(binding, "invoice:1", now=90)
        with closing(sqlite3.connect(ledger.database)) as db, db:
            db.execute(
                "CREATE TABLE operators(actor_id INTEGER PRIMARY KEY,enabled INTEGER)"
            )
            db.execute("INSERT INTO operators VALUES (900,1)")

        def check(
            db: sqlite3.Connection, operation: PaymentOperation, _replayed: bool
        ) -> bool:
            if operation.kind == "invoice":
                return operation.binding.user_id == binding.user_id
            return (
                db.execute(
                    "SELECT enabled FROM operators WHERE actor_id=?",
                    (operation.actor_id,),
                ).fetchone()[0]
                == 1
            )

        claim = ledger.start_operation(
            binding, "invoice:1", "worker", check=check, now=100
        )
        invoice = ProviderEvent(
            binding,
            "invoice:event",
            "invoice-created",
            "created",
            "fixture-proof:invoice",
            operation_id="invoice:1",
            provider_ref="native:invoice",
        )
        provider.perform("invoice:1", invoice)
        ledger.mark_unknown(
            claim, now=101
        )  # The remote effect committed; its response was lost.
        unknown_invoice = ledger.get_operation(binding, "invoice:1")
        ledger.reconcile_operation(
            provider.lookup("invoice:1"),
            verify=provider.verify,
            expected_revision=unknown_invoice.revision,
            now=102,
        )
        invoice_grants_access = ledger.has_access(binding, now=102).active

        paid = ProviderEvent(
            binding,
            "payment:event",
            "paid",
            "captured",
            "fixture-proof:payment",
            charge_id="native:charge",
            amount=binding.amount,
            paid_at=102,
        )
        provider.perform("payment:1", paid)
        receipt = ledger.apply_event(
            provider.lookup("payment:1"), verify=provider.verify, now=102
        )
        duplicate = ledger.apply_event(
            provider.lookup("payment:1"), verify=provider.verify, now=102
        )
        paid_access = ledger.has_access(binding, now=102).active

        ledger.request_refund(
            binding,
            "native:charge",
            "refund:1",
            binding.amount,
            900,
            check=check,
            now=103,
        )
        ledger.start_operation(
            binding, "refund:1", "worker", check=check, lease_seconds=10, now=103
        )
        refund = ProviderEvent(
            binding,
            "refund:event",
            "refunded",
            "refund_succeeded",
            "fixture-proof:refund",
            operation_id="refund:1",
            charge_id="native:charge",
            refund_id="native:refund",
            amount=binding.amount,
        )
        provider.perform(
            "refund:1", refund
        )  # Again, the caller does not retain a response.
        restarted = SQLitePaymentLedger(ledger.database)
        restarted.recover_expired(binding, now=113)
        unknown = restarted.get_operation(binding, "refund:1")
        held = restarted.get_charge(binding, "native:charge")["reserved"].minor_units
        restarted.reconcile_operation(
            provider.lookup("refund:1"),
            verify=provider.verify,
            expected_revision=unknown.revision,
            now=114,
        )
        balance = restarted.get_charge(binding, "native:charge")
        with closing(sqlite3.connect(provider.database)) as db:
            remote_refunds = db.execute(
                "SELECT COUNT(*) FROM effects WHERE operation_id='refund:1'"
            ).fetchone()[0]
        print(
            json.dumps(
                {
                    "amount": binding.amount.to_decimal(),
                    "invoice_grants_access": invoice_grants_access,
                    "paid_receipt": receipt.kind,
                    "duplicate": duplicate.duplicate,
                    "paid_access": paid_access,
                    "lost_refund_state": unknown.state,
                    "held_minor_units": held,
                    "refunded_minor_units": balance["refunded"].minor_units,
                    "remaining_reserved_minor_units": balance["reserved"].minor_units,
                    "remote_refund_effects": remote_refunds,
                    "access_after_refund": restarted.has_access(
                        binding, now=114
                    ).active,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
