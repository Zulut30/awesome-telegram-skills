"""Bounded Stars refund dispatch and observations over a host-owned authenticated SDK ingress."""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message, StarTransaction, TransactionPartnerUser

from ..errors import PermissionDenied, UnknownOutcome, ValidationFailure
from ..payment_ledger import (
    PaymentBinding,
    PaymentCheck,
    PaymentConflict,
    PaymentLeaseLost,
    PaymentOperation,
    ProviderEvent,
    SQLitePaymentLedger,
)
from ..providers.http import binding_reference
from ..worker import settled_to_thread


class StarsPaymentAdapter:
    """Trusted server integration, not authentication of constructed SDK objects.

    The host accepts Message only from its authenticated Telegram ingress, retains
    durable updates and owns Bot/session lifecycle. Never expose event helpers as
    an endpoint accepting client DTOs. Session middleware must not retry writes.
    Ledger methods are finite local work; async methods join that work on cancel.
    """

    def __init__(self, bot: Bot, ledger: SQLitePaymentLedger, *, timeout_seconds: int = 15) -> None:
        if not isinstance(bot, Bot) or not isinstance(ledger, SQLitePaymentLedger):
            raise ValidationFailure('Use the host Bot and initialized financial ledger')
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 20:
            raise ValidationFailure('Use a bounded Stars request timeout from one to twenty seconds')
        self.bot = bot
        self.ledger = ledger
        self.timeout_seconds = timeout_seconds

    def _binding(self, binding: PaymentBinding) -> None:
        if binding.bot_id != self.bot.id or binding.route != 'telegram-stars':
            raise PermissionDenied('Stars order belongs to another bot or payment route')
        if binding.amount.currency != 'XTR' or binding.amount.exponent != 0 or binding.allow_partial_refunds:
            raise PermissionDenied('Stars requires a full whole-XTR order')

    def invoice_payload(self, binding: PaymentBinding, invoice_operation_id: str) -> str:
        """Opaque full server binding, never a bearer credential or payment proof."""
        self._binding(binding)
        return binding_reference(binding, invoice_operation_id)

    def _message(self, binding: PaymentBinding, message: Message) -> None:
        self._binding(binding)
        if (
            message.bot is None
            or message.bot.id != self.bot.id
            or message.chat.type != 'private'
            or message.chat.id != binding.user_id
            or message.business_connection_id is not None
            or message.from_user is None
            or message.from_user.is_bot
            or message.from_user.id != binding.user_id
        ):
            raise PermissionDenied('Use a trusted private payment update for the bound buyer and bot')

    def _invoice(self, binding: PaymentBinding, invoice_operation_id: str) -> None:
        if self.ledger.get_operation(binding, invoice_operation_id).kind != 'invoice':
            raise PaymentConflict('Stars receipt needs its original saved invoice operation')

    @staticmethod
    def _event_id(kind: str, binding: PaymentBinding, charge_id: str, operation_id: str | None = None) -> str:
        raw = f'{binding.bot_id}:{binding.user_id}:{charge_id}:{operation_id or ""}'
        return 'stars:' + kind + ':' + hashlib.sha256(raw.encode('utf-8')).hexdigest()

    @staticmethod
    def _timestamp(value: datetime) -> int:
        if value.tzinfo is None:
            raise ValidationFailure('Use a native timezone-aware Telegram timestamp')
        instant = int(value.timestamp())
        if instant <= 0:
            raise ValidationFailure('Use a positive native Telegram timestamp')
        return instant

    async def paid_event(
        self, binding: PaymentBinding, message: Message, *, invoice_operation_id: str, evidence_ref: str
    ) -> ProviderEvent:
        """Map a host-authenticated successful_payment; constructing Message does not authenticate it."""
        self._message(binding, message)
        await settled_to_thread(self._invoice, binding, invoice_operation_id)
        payment = message.successful_payment
        if (
            payment is None
            or payment.currency != 'XTR'
            or payment.total_amount != binding.amount.minor_units
            or payment.invoice_payload != self.invoice_payload(binding, invoice_operation_id)
        ):
            raise PermissionDenied('Stars paid receipt does not match the immutable order')
        recurring = binding.subscription_id is not None
        if (payment.is_recurring is True) != recurring:
            raise PermissionDenied('Stars recurring receipt differs from the order route')
        paid_at = self._timestamp(message.date)
        expires = payment.subscription_expiration_date
        if recurring and (type(expires) is not int or expires <= paid_at):
            raise PermissionDenied('Stars subscription requires its native paid period')
        if not recurring and (expires is not None or payment.is_first_recurring is True):
            raise PermissionDenied('One-time Stars payment cannot supply a subscription period')
        return ProviderEvent(
            binding,
            self._event_id('paid', binding, payment.telegram_payment_charge_id),
            'paid',
            'successful_payment',
            evidence_ref,
            charge_id=payment.telegram_payment_charge_id,
            amount=binding.amount,
            paid_at=paid_at,
            period_start=paid_at if recurring else None,
            period_end=expires if recurring else None,
            first_recurring=payment.is_first_recurring is True,
        )

    async def refund_event(
        self,
        binding: PaymentBinding,
        message: Message,
        *,
        invoice_operation_id: str,
        evidence_ref: str,
        operation_id: str | None = None,
    ) -> ProviderEvent:
        """Map authenticated RefundedPayment, including an out-of-band refund without a local intent."""
        self._message(binding, message)
        await settled_to_thread(self._invoice, binding, invoice_operation_id)
        refund = message.refunded_payment
        if (
            refund is None
            or refund.currency != 'XTR'
            or refund.total_amount != binding.amount.minor_units
            or refund.invoice_payload != self.invoice_payload(binding, invoice_operation_id)
        ):
            raise PermissionDenied('Stars refunded receipt does not match the immutable order')
        return ProviderEvent(
            binding,
            self._event_id('refund-update', binding, refund.telegram_payment_charge_id, operation_id),
            'refunded',
            'refunded_payment',
            evidence_ref,
            operation_id=operation_id,
            charge_id=refund.telegram_payment_charge_id,
            refund_id=refund.telegram_payment_charge_id,
            amount=binding.amount,
        )

    async def refund(
        self,
        binding: PaymentBinding,
        charge_id: str,
        operation_id: str,
        actor_id: int,
        *,
        check: PaymentCheck,
        worker_id: str = 'stars-refund',
        now: int | None = None,
    ) -> PaymentOperation:
        """Reserve and dispatch one full refund; even True awaits independent financial reconciliation."""
        self._binding(binding)
        await settled_to_thread(
            self.ledger.request_refund, binding, charge_id, operation_id, binding.amount, actor_id, check=check, now=now
        )
        claim = await settled_to_thread(
            self.ledger.start_operation,
            binding,
            operation_id,
            worker_id,
            check=check,
            lease_seconds=self.timeout_seconds + 5,
            now=now,
        )
        try:
            async with asyncio.timeout(self.timeout_seconds):
                accepted = await self.bot.refund_star_payment(
                    user_id=binding.user_id, telegram_payment_charge_id=charge_id
                )
            if accepted is not True:
                raise UnknownOutcome('Stars refund did not establish a successful native response')
        except asyncio.CancelledError:
            # Cancellation cannot unsend the request. A crash before this write is recovered from its lease.
            try:
                await settled_to_thread(self.ledger.mark_unknown, claim, now=now)
            except PaymentLeaseLost:
                pass  # An authenticated update may already have settled the operation.
            raise
        except Exception as error:
            try:
                await settled_to_thread(self.ledger.mark_unknown, claim, now=now)
            except PaymentLeaseLost:
                pass
            raise UnknownOutcome('Stars refund needs authenticated reconciliation before another send') from error
        try:
            return await settled_to_thread(self.ledger.mark_unknown, claim, now=now)
        except PaymentLeaseLost:
            return await settled_to_thread(self.ledger.get_operation, binding, operation_id)

    def _refund_transaction(
        self,
        binding: PaymentBinding,
        transaction: StarTransaction,
        *,
        charge_id: str,
        payload: str,
        paid_at: int,
        now: int,
    ) -> bool:
        partner = transaction.receiver
        # Bot API emits positive magnitudes and distinguishes direction with receiver/source.
        return (
            transaction.id == charge_id
            and transaction.source is None
            and isinstance(partner, TransactionPartnerUser)
            and partner.transaction_type == 'invoice_payment'
            and partner.user.id == binding.user_id
            and not partner.user.is_bot
            and partner.invoice_payload == payload
            and transaction.amount == binding.amount.minor_units
            and transaction.nanostar_amount in (None, 0)
            and paid_at <= self._timestamp(transaction.date) <= now
        )

    async def reconcile_refund(
        self,
        binding: PaymentBinding,
        operation_id: str,
        actor_id: int,
        *,
        invoice_operation_id: str,
        check: PaymentCheck,
        max_pages: int = 5,
        page_size: int = 100,
        now: int | None = None,
    ) -> PaymentOperation:
        """Bounded authenticated GET only. Missing/mismatched/optional fields never authorize a retry."""
        self._binding(binding)
        if type(max_pages) is not int or not 1 <= max_pages <= 20:
            raise ValidationFailure('Use one to twenty bounded history pages')
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValidationFailure('Use one to one hundred transactions per page')
        current = await settled_to_thread(self.ledger.get_operation, binding, operation_id)
        if current.kind != 'refund' or current.charge_id is None:
            raise PaymentConflict('Reconcile the saved Stars refund operation')
        charge_id = current.charge_id
        # Replayed reservation checks the exact current operator ACL in the writer transaction.
        current = await settled_to_thread(
            self.ledger.request_refund,
            binding,
            charge_id,
            operation_id,
            binding.amount,
            actor_id,
            check=check,
            now=now,
        )
        if current.state == 'confirmed':
            return current
        if current.state != 'unknown':
            raise PaymentConflict('Recover an expired sender before reconciling its unknown refund')
        charge = await settled_to_thread(self.ledger.get_charge, binding, charge_id)
        payload = self.invoice_payload(binding, invoice_operation_id)
        await settled_to_thread(self._invoice, binding, invoice_operation_id)
        instant = int(time.time()) if now is None else now
        if type(instant) is not int or instant <= 0:
            raise ValidationFailure('Use a positive exact reconciliation time')
        for page in range(max_pages):
            async with asyncio.timeout(self.timeout_seconds):
                history = await self.bot.get_star_transactions(offset=page * page_size, limit=page_size)
            for transaction in history.transactions:
                if self._refund_transaction(
                    binding,
                    transaction,
                    charge_id=charge_id,
                    payload=payload,
                    paid_at=charge['paid_at'],
                    now=instant,
                ):
                    event = ProviderEvent(
                        binding,
                        self._event_id('refund-history', binding, charge_id, operation_id),
                        'refunded',
                        'getStarTransactions-refund',
                        'stars:authenticated-history',
                        operation_id=operation_id,
                        charge_id=charge_id,
                        refund_id=charge_id,
                        amount=binding.amount,
                    )
                    # Only the authenticated Bot call above supplies this closed local verifier.
                    token = object()

                    def verified(raw: object) -> ProviderEvent:
                        if raw is not token:
                            raise PermissionDenied('Untrusted Stars history observation')
                        return event

                    await settled_to_thread(
                        self.ledger.reconcile_operation,
                        token,
                        verify=verified,
                        expected_revision=current.revision,
                        now=instant,
                    )
                    return await settled_to_thread(self.ledger.get_operation, binding, operation_id)
            if len(history.transactions) < page_size:
                break
        raise UnknownOutcome('Bounded Stars history did not establish this refund; preserve its operation')
