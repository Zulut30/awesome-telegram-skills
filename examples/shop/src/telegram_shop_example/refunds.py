"""Shop-owned Stars protocol bridge and operator workflow over the public financial ledger.

The immutable legacy shop payload remains valid. One financial binding per native
charge also preserves second charges held for review; none can grant twice.
Only authenticated SDK ingress/history may append financial facts. A stored DTO
or a browser callback never becomes proof of a payment or refund.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message, TransactionPartnerUser
from telegram_patterns import (
    PaymentConflict,
    PermissionDenied,
    ProviderEvent,
    UnknownOutcome,
    ValidationFailure,
)
from telegram_patterns.aiogram import StarsPaymentAdapter

from .storage import io_call
from .store import Store


class ShopRefunds:
    def __init__(self, store: Store, bot: Bot, *, timeout_seconds: int = 15):
        if bot.id != store.bot_id:
            raise PermissionDenied()
        self.store, self.bot = store, bot
        self.adapter = StarsPaymentAdapter(
            bot, store.financial, timeout_seconds=timeout_seconds
        )
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _timestamp(value: datetime) -> int:
        if value.tzinfo is None or int(value.timestamp()) <= 0:
            raise ValidationFailure(
                "A native timezone-aware financial timestamp is required"
            )
        return int(value.timestamp())

    def _message(self, message: Message) -> int:
        if (
            message.bot is None
            or message.bot.id != self.bot.id
            or message.chat.type != "private"
            or message.from_user is None
            or message.from_user.is_bot
            or message.chat.id != message.from_user.id
            or message.business_connection_id is not None
        ):
            raise PermissionDenied()
        return message.from_user.id

    async def paid(self, message: Message) -> dict:
        actor = self._message(message)
        payment = message.successful_payment
        if (
            payment is None
            or payment.is_recurring is True
            or payment.is_first_recurring is True
            or payment.subscription_expiration_date is not None
        ):
            raise PermissionDenied()
        order = await io_call(
            self.store.receipt_target,
            actor,
            payment.invoice_payload,
            payment.currency,
            payment.total_amount,
        )
        event = {
            "kind": "paid",
            "actor": actor,
            "charge": payment.telegram_payment_charge_id,
            "payload": payment.invoice_payload,
            "amount": payment.total_amount,
            "currency": payment.currency,
            "paid_at": self._timestamp(message.date),
            "origin": "message",
            "provider_state": "successful_payment",
        }
        identifier = await io_call(
            self.store.record_financial_ingress,
            order,
            payment.telegram_payment_charge_id,
            "paid",
            event,
        )
        return await self.process(identifier)

    async def refunded(self, message: Message) -> dict:
        actor = self._message(message)
        payment = message.refunded_payment
        if payment is None:
            raise PermissionDenied()
        order = await io_call(
            self.store.receipt_target,
            actor,
            payment.invoice_payload,
            payment.currency,
            payment.total_amount,
        )
        event = {
            "kind": "refunded",
            "actor": actor,
            "charge": payment.telegram_payment_charge_id,
            "payload": payment.invoice_payload,
            "amount": payment.total_amount,
            "currency": payment.currency,
            "origin": "message",
            "provider_state": "refunded_payment",
        }
        identifier = await io_call(
            self.store.record_financial_ingress,
            order,
            payment.telegram_payment_charge_id,
            "refunded",
            event,
        )
        return await self.process(identifier)

    def _refund_operation(self, order_id: str, charge: str, binding) -> str | None:
        from .storage import connection

        with connection(self.store.database) as db:
            intents = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM shop_refund_intents WHERE bot_id=? AND order_id=? AND charge=?",
                    (self.store.bot_id, order_id, charge),
                )
            ]
        operations = []
        for intent in intents:
            try:
                operation = self.store.financial.get_operation(
                    binding, intent["operation"]
                )
            except PaymentConflict:
                continue
            if (
                operation.kind == "refund"
                and operation.charge_id == charge
                and operation.state in {"pending", "sending", "unknown", "confirmed"}
            ):
                operations.append(operation.operation_id)
        if len(operations) > 1:
            raise PaymentConflict("More than one full refund claims this charge")
        return operations[0] if operations else None

    async def process(self, identifier: int) -> dict:
        record = await io_call(self.store.financial_ingress, identifier)
        fact = json.loads(record["event_json"])
        # Resolve the original server order again; the durable trusted journal is not a client DTO endpoint.
        order = await io_call(
            self.store.receipt_target,
            fact["actor"],
            fact["payload"],
            fact["currency"],
            fact["amount"],
        )
        link = await io_call(self.store.payment_link, order["id"], fact["charge"])
        if link is None:
            raise PaymentConflict("Financial ingress lost its immutable charge binding")
        binding = self.store.link_binding(link)
        await io_call(
            self.store.financial.create_order,
            binding,
            link["invoice_operation"],
            now=int(self.store.now()),
        )
        operation = None
        if fact["kind"] == "refunded":
            operation = await io_call(
                self._refund_operation, order["id"], fact["charge"], binding
            )
        event = ProviderEvent(
            binding,
            "shop:"
            + fact["kind"]
            + ":"
            + hashlib.sha256(
                f"{self.store.bot_id}:{fact['charge']}".encode()
            ).hexdigest(),
            fact["kind"],
            fact["provider_state"],
            f"shop-trusted-ingress:{identifier}",
            operation_id=operation,
            charge_id=fact["charge"],
            refund_id=fact["charge"] if fact["kind"] == "refunded" else None,
            amount=binding.amount,
            paid_at=fact.get("paid_at"),
        )
        token = object()

        def verified(raw):
            if raw is not token:
                raise PermissionDenied()
            return event

        await io_call(
            self.store.financial.apply_event,
            token,
            verify=verified,
            now=int(self.store.now()),
        )
        # Tests may stop a process at this public boundary. Access already consults the ledger,
        # so a confirmed refund cannot leak content while the projection is still old.
        return await io_call(self.store.complete_financial_ingress, identifier)

    async def recover(self) -> int:
        processed = 0
        while pending := await io_call(self.store.pending_financial_ingress):
            for identifier in pending:
                await self.process(identifier)
                processed += 1
        return processed

    async def _history(
        self,
        token: str,
        order: dict,
        charge: str,
        kind: str,
        *,
        paid_at: int | None = None,
    ) -> int:
        """Bounded authenticated GET; absence, wrong direction and omitted fields prove nothing."""
        for page in range(5):
            await io_call(self.store.operator_identity, token)
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    history = await self.bot.get_star_transactions(
                        offset=page * 100, limit=100
                    )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                raise UnknownOutcome(
                    "Authenticated Stars history is unavailable; no write was retried"
                ) from error
            for transaction in history.transactions:
                partner = transaction.source if kind == "paid" else transaction.receiver
                other = transaction.receiver if kind == "paid" else transaction.source
                if (
                    transaction.id != charge
                    or other is not None
                    or not isinstance(partner, TransactionPartnerUser)
                    or partner.transaction_type != "invoice_payment"
                    or partner.user.id != order["actor_id"]
                    or partner.user.is_bot
                    or partner.invoice_payload != self.store.payload(order["id"])
                    or type(transaction.amount) is not int
                    or transaction.amount != order["total"]
                    or transaction.nanostar_amount not in (None, 0)
                ):
                    continue
                native_at = self._timestamp(transaction.date)
                if native_at > int(self.store.now()) or (
                    paid_at is not None and native_at < paid_at
                ):
                    continue
                await io_call(self.store.operator_identity, token)
                event = {
                    "kind": kind,
                    "actor": order["actor_id"],
                    "charge": charge,
                    "payload": self.store.payload(order["id"]),
                    "amount": order["total"],
                    "currency": "XTR",
                    "origin": "history",
                    "provider_state": "getStarTransactions-" + kind,
                }
                if kind == "paid":
                    event["paid_at"] = native_at
                identifier = await io_call(
                    self.store.record_financial_ingress, order, charge, kind, event
                )
                await self.process(identifier)
                return identifier
            if len(history.transactions) < 100:
                break
        raise UnknownOutcome(
            "Bounded authenticated history did not establish the original financial fact"
        )

    async def _known_charge(self, token: str, order: dict, charge: str):
        link = await io_call(self.store.payment_link, order["id"], charge)
        if link is not None:
            try:
                binding = self.store.link_binding(link)
                known = await io_call(self.store.financial.get_charge, binding, charge)
                if known["paid"] and link["financial_ready"]:
                    return link, binding
            except PaymentConflict:
                pass
        # Replay retained authenticated facts first; a native timestamp is never invented from receipt rowid/now.
        await self.recover()
        link = await io_call(self.store.payment_link, order["id"], charge)
        if link is not None:
            binding = self.store.link_binding(link)
            known = await io_call(self.store.financial.get_charge, binding, charge)
            if known["paid"] and link["financial_ready"]:
                return link, binding
        await self._history(token, order, charge, "paid")
        link = await io_call(self.store.payment_link, order["id"], charge)
        if link is None:
            raise PaymentConflict("Missing imported charge binding")
        return link, self.store.link_binding(link)

    @staticmethod
    def _view(operation) -> dict:
        return {
            "operation": operation.operation_id,
            "charge": operation.charge_id,
            "state": operation.state,
            "amount": operation.amount.minor_units,
            "currency": operation.amount.currency,
        }

    async def request(
        self, token: str, order_id: str, charge: str, operation_id: str
    ) -> dict:
        intent = await io_call(
            self.store.begin_refund_intent, token, order_id, charge, operation_id
        )
        order = await io_call(self.store.operator_order, token, order_id)
        try:
            _link, binding = await self._known_charge(token, order, charge)
        except UnknownOutcome:
            await io_call(
                self.store.record_operator_result,
                intent["actor_id"],
                order_id,
                operation_id,
                "refund-dispatch",
                "operator-review",
            )
            return {
                "operation": operation_id,
                "charge": charge,
                "state": "operator-review",
                "amount": order["total"],
                "currency": "XTR",
            }
        check = self.store.refund_check(token, intent["actor_id"])
        # Public reserve is replay-aware and checks current session/role in its writer before every path.
        operation = await io_call(
            self.store.financial.request_refund,
            binding,
            charge,
            operation_id,
            binding.amount,
            intent["actor_id"],
            check=check,
            now=int(self.store.now()),
        )
        if operation.state == "pending":
            try:
                operation = await self.adapter.refund(
                    binding,
                    charge,
                    operation_id,
                    intent["actor_id"],
                    check=check,
                    now=int(self.store.now()),
                )
            except UnknownOutcome:
                operation = await io_call(
                    self.store.financial.get_operation, binding, operation_id
                )
            except PaymentConflict:
                operation = await io_call(
                    self.store.financial.get_operation, binding, operation_id
                )
                if operation.state not in {"sending", "unknown", "confirmed"}:
                    raise
        # sending/unknown/confirmed are observed; none authorize a second send.
        await io_call(
            self.store.record_operator_result,
            intent["actor_id"],
            order_id,
            operation_id,
            "refund-dispatch",
            operation.state,
        )
        return self._view(operation)

    async def status(self, token: str, order_id: str, operation_id: str) -> dict | None:
        intent = await io_call(self.store.refund_intent, token, order_id, operation_id)
        if intent is None:
            return None
        link = await io_call(self.store.payment_link, order_id, intent["charge"])
        if link is not None:
            binding = self.store.link_binding(link)
            await io_call(
                self.store.financial.recover_expired, binding, now=int(self.store.now())
            )
            try:
                operation = await io_call(
                    self.store.financial.get_operation, binding, operation_id
                )
            except PaymentConflict:
                pass
            else:
                return self._view(operation)
        order = await io_call(self.store.operator_order, token, order_id)
        return {
            "operation": operation_id,
            "charge": intent["charge"],
            "state": "operator-review",
            "amount": order["total"],
            "currency": "XTR",
        }

    async def reconcile(
        self, token: str, order_id: str, operation_id: str
    ) -> dict | None:
        actor = await io_call(self.store.operator_identity, token)
        current = await self.status(token, order_id, operation_id)
        if current is None:
            return None
        intent = await io_call(self.store.refund_intent, token, order_id, operation_id)
        if intent is None:
            return None
        order = await io_call(self.store.operator_order, token, order_id)
        link = await io_call(self.store.payment_link, order_id, intent["charge"])
        if link is None or current["state"] == "operator-review":
            return current
        if current["state"] != "confirmed":
            binding = self.store.link_binding(link)
            known = await io_call(
                self.store.financial.get_charge, binding, intent["charge"]
            )
            try:
                await self._history(
                    token, order, intent["charge"], "refunded", paid_at=known["paid_at"]
                )
            except UnknownOutcome:
                pass
        current = await self.status(token, order_id, operation_id)
        if current is None:
            return None
        await io_call(
            self.store.record_operator_result,
            actor,
            order_id,
            operation_id,
            "refund-reconcile",
            current["state"],
        )
        return current

    async def overview(self, token: str, order_id: str) -> dict:
        order = await io_call(self.store.operator_order, token, order_id)
        receipts = await io_call(self.store.operator_receipts, token, order_id)
        refunds = []
        for intent in await io_call(self.store.refund_intents, token, order_id):
            refunds.append(await self.status(token, order_id, intent["operation"]))
        return {
            "order": self.store.view(order),
            "charges": receipts,
            "refunds": refunds,
        }
