"""Полный локальный SDK-сценарий Stars; StubSession не подтверждает реальный платеж."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram import Bot, Dispatcher, F, Router
from aiogram.methods import (
    AnswerPreCheckoutQuery,
    CreateInvoiceLink,
    EditUserStarSubscription,
    GetStarTransactions,
    RefundStarPayment,
)
from aiogram.types import BotSubscriptionUpdated, Message, PreCheckoutQuery, Update
from bot_fixture import ACTOR, DATE, TOKEN
from telegram_patterns import (
    Money,
    PaymentBinding,
    PaymentOperation,
    PermissionDenied,
    ProviderEvent,
    SQLitePaymentLedger,
    UnknownOutcome,
    settled_to_thread,
)
from telegram_patterns.aiogram import StarsPaymentAdapter, stars_invoice
from telegram_patterns.testing import StubSession


def apply_fixture(
    ledger: SQLitePaymentLedger, event: ProviderEvent, *, now: int
) -> bool:
    # Только закрытая синтетическая фикстура. Реальный host принимает update своим проверенным ingress.
    token = object()

    def verified(raw: object) -> ProviderEvent:
        if raw is not token:
            raise ValueError("Untrusted fixture input")
        return event

    return ledger.apply_event(token, verify=verified, now=now).duplicate


def current_acl(
    connection: sqlite3.Connection, operation: PaymentOperation, replayed: bool
) -> bool:
    # Реальное приложение читает текущую роль оператора в этой же writer-транзакции.
    return (
        connection.in_transaction
        and operation.actor_id in (42, 900)
        and type(replayed) is bool
    )


async def main() -> None:
    session = (
        StubSession()
        .respond(CreateInvoiceLink, "https://t.me/$stars_fixture")
        .respond(AnswerPreCheckoutQuery, True)
        .respond(RefundStarPayment, True)
        .respond(EditUserStarSubscription, True)
    )
    bot = Bot(TOKEN, session=session)
    try:
        with TemporaryDirectory() as directory:
            ledger = SQLitePaymentLedger(Path(directory) / "stars.sqlite")
            ledger.initialize()
            binding = PaymentBinding(
                "merchant:fixture",
                bot.id,
                ACTOR.id,
                "order:fixture",
                "telegram",
                Money(20, "XTR", 0),
                route="telegram-stars",
            )
            adapter = StarsPaymentAdapter(bot, ledger)
            now = int(DATE.timestamp())
            payload = adapter.invoice_payload(binding, "invoice:1")
            server_orders: dict[str, tuple[PaymentBinding, str]] = {
                payload: (binding, "invoice:1")
            }
            await settled_to_thread(ledger.create_order, binding, "invoice:1", now=now)
            await settled_to_thread(
                ledger.start_operation,
                binding,
                "invoice:1",
                "invoice-worker",
                check=current_acl,
                now=now,
            )
            invoice = stars_invoice("Fixture", "Digital item", payload, 20)
            link = await bot(invoice)
            assert link == "https://t.me/$stars_fixture"
            await settled_to_thread(
                apply_fixture,
                ledger,
                ProviderEvent(
                    binding,
                    "fixture:invoice",
                    "invoice-created",
                    "created",
                    "fixture:native-link",
                    operation_id="invoice:1",
                    provider_ref=link,
                ),
                now=now,
            )
            assert not ledger.has_access(binding, now=now).active
            router = Router(name="fixture-stars")

            @router.pre_checkout_query()
            async def checkout(query: PreCheckoutQuery) -> None:
                # Срок Telegram — 10 секунд; локальный бюджет проверки — 3 секунды.
                async with asyncio.timeout(3):
                    saved = await settled_to_thread(ledger.get_order, binding)
                    allowed = (
                        query.from_user.id == binding.user_id
                        and query.invoice_payload == payload
                        and query.currency == "XTR"
                        and query.total_amount == saved.binding.amount.minor_units
                    )
                    await query.answer(
                        ok=allowed,
                        error_message=None if allowed else "Order unavailable",
                    )

            @router.message(F.successful_payment)
            async def paid(message: Message) -> None:
                # Сюда реальный host передает только update из аутентифицированного долговечного входа.
                if message.successful_payment is None:
                    raise PermissionDenied("No trusted payment update")
                saved_binding, saved_invoice = server_orders[
                    message.successful_payment.invoice_payload
                ]
                event = await adapter.paid_event(
                    saved_binding,
                    message,
                    invoice_operation_id=saved_invoice,
                    evidence_ref="fixture:trusted-worker",
                )
                await settled_to_thread(apply_fixture, ledger, event, now=now)

            async def subscription_lookup(
                native: BotSubscriptionUpdated,
            ) -> tuple[PaymentBinding, str] | None:
                selected = server_orders.get(native.invoice_payload)
                return (
                    selected
                    if selected is not None and selected[0].subscription_id is not None
                    else None
                )

            dispatcher = Dispatcher()
            dispatcher.include_router(router)
            dispatcher.include_router(
                adapter.subscription_router(
                    subscription_lookup, stream_epoch="fixture:stream"
                )
            )
            user = ACTOR.model_dump(mode="json")
            query = Update.model_validate(
                {
                    "update_id": 1,
                    "pre_checkout_query": {
                        "id": "query-fixture",
                        "from": user,
                        "currency": "XTR",
                        "total_amount": 20,
                        "invoice_payload": payload,
                    },
                }
            )
            await dispatcher.feed_update(bot, query)
            answers = [
                call
                for call in session.calls
                if isinstance(call, AnswerPreCheckoutQuery)
            ]
            assert len(answers) == 1 and answers[0].ok is True
            assert not ledger.has_access(binding, now=now).active
            update = Update.model_validate(
                {
                    "update_id": 2,
                    "message": {
                        "message_id": 1,
                        "date": now,
                        "chat": {"id": 42, "type": "private"},
                        "from": user,
                        "successful_payment": {
                            "currency": "XTR",
                            "total_amount": 20,
                            "invoice_payload": payload,
                            "telegram_payment_charge_id": "charge-fixture",
                            "provider_payment_charge_id": "",
                        },
                    },
                }
            )
            await dispatcher.feed_update(bot, update)
            await dispatcher.feed_update(bot, update)
            assert (
                ledger.has_access(binding, now=now).active
                and ledger.get_order(binding).confirmed_charges == 1
            )
            result = await adapter.refund(
                binding, "charge-fixture", "refund:1", 900, check=current_acl, now=now
            )
            assert (
                result.state == "unknown" and ledger.has_access(binding, now=now).active
            )
            # Официальный Bot API показывает положительную величину исходящей операции в receiver.
            session.respond(
                GetStarTransactions,
                {
                    "transactions": [
                        {
                            "id": "charge-fixture",
                            "amount": 20,
                            "date": now + 1,
                            "receiver": {
                                "type": "user",
                                "transaction_type": "invoice_payment",
                                "user": user,
                                "invoice_payload": payload,
                            },
                        }
                    ]
                },
            )
            final = await adapter.reconcile_refund(
                binding,
                "refund:1",
                900,
                invoice_operation_id="invoice:1",
                check=current_acl,
                now=now + 1,
            )
            assert (
                final.state == "confirmed"
                and not ledger.has_access(binding, now=now + 1).active
            )
            assert (
                len(
                    [
                        call
                        for call in session.calls
                        if isinstance(call, RefundStarPayment)
                    ]
                )
                == 1
            )

            # Новый период оплачивается своим successful_payment, а не переключателем автопродления.
            recurring = PaymentBinding(
                "merchant:fixture",
                bot.id,
                ACTOR.id,
                "order:subscription",
                "telegram",
                Money(20, "XTR", 0),
                route="telegram-stars",
                subscription_id="sub:fixture",
            )
            recurring_payload = adapter.invoice_payload(
                recurring, "invoice:subscription"
            )
            server_orders[recurring_payload] = (recurring, "invoice:subscription")
            await settled_to_thread(
                ledger.create_order, recurring, "invoice:subscription", now=now
            )
            await settled_to_thread(
                ledger.start_operation,
                recurring,
                "invoice:subscription",
                "invoice-worker",
                check=current_acl,
                now=now,
            )
            subscription_link = await bot(
                stars_invoice(
                    "Monthly",
                    "Fixture subscription",
                    recurring_payload,
                    20,
                    monthly_subscription=True,
                )
            )
            await settled_to_thread(
                apply_fixture,
                ledger,
                ProviderEvent(
                    recurring,
                    "fixture:subscription-invoice",
                    "invoice-created",
                    "created",
                    "fixture:native-link",
                    operation_id="invoice:subscription",
                    provider_ref=subscription_link,
                ),
                now=now,
            )
            await settled_to_thread(
                ledger.register_renewal_stream, recurring, "fixture:stream"
            )
            recurring_update = Update.model_validate(
                {
                    "update_id": 3,
                    "message": {
                        "message_id": 3,
                        "date": now,
                        "chat": {"id": 42, "type": "private"},
                        "from": user,
                        "successful_payment": {
                            "currency": "XTR",
                            "total_amount": 20,
                            "invoice_payload": recurring_payload,
                            "telegram_payment_charge_id": "subscription-charge",
                            "provider_payment_charge_id": "",
                            "is_recurring": True,
                            "is_first_recurring": True,
                            "subscription_expiration_date": now + 2592000,
                        },
                    },
                }
            )
            await dispatcher.feed_update(bot, recurring_update)
            for operation_id, canceled in [
                ("renewal:cancel", True),
                ("renewal:resume", False),
            ]:
                edited = await adapter.edit_renewal(
                    recurring,
                    "subscription-charge",
                    operation_id,
                    900,
                    is_canceled=canceled,
                    check=current_acl,
                    now=now + 1,
                )
                assert edited.state == "confirmed"
                assert (
                    ledger.has_access(recurring, now=now + 2).expires_at
                    == now + 2592000
                )
            for update_id, state in [
                (10, "canceled"),
                (12, "active"),
                (11, "canceled"),
            ]:
                await dispatcher.feed_update(
                    bot,
                    Update.model_validate(
                        {
                            "update_id": update_id,
                            "subscription": {
                                "user": user,
                                "invoice_payload": recurring_payload,
                                "state": state,
                            },
                        }
                    ),
                )
            assert ledger.get_renewal_control(recurring)["last_update_id"] == 12
            assert ledger.has_access(recurring, now=now + 2).renewal == "active"

            fixture_setting = {"canceled": False}

            def lost_edit(_: object) -> object:
                fixture_setting["canceled"] = True
                raise EOFError("Local effect recorded; native reply lost")

            session.respond(EditUserStarSubscription, lost_edit)
            try:
                await adapter.edit_renewal(
                    recurring,
                    "subscription-charge",
                    "renewal:lost",
                    900,
                    is_canceled=True,
                    check=current_acl,
                    now=now + 2,
                )
            except UnknownOutcome:
                pass
            else:
                raise AssertionError("Lost edit response was treated as a known result")
            pending = ledger.get_operation(recurring, "renewal:lost")
            control = ledger.get_renewal_control(recurring)
            token = object()

            def operator_fixture(raw: object) -> ProviderEvent:
                # Только независимая локальная фикстура. Официальный GET настройки здесь не выдуман.
                if raw is not token or fixture_setting["canceled"] is not True:
                    raise PermissionDenied("No trusted fixture proof")
                return ProviderEvent(
                    recurring,
                    "fixture:renewal-proof",
                    "renewal-state",
                    "operator-verified",
                    "fixture:independent-setting",
                    operation_id="renewal:lost",
                    charge_id="subscription-charge",
                    renewal="canceled",
                )

            resolved = await adapter.reconcile_renewal(
                recurring,
                "renewal:lost",
                token,
                verify=operator_fixture,
                expected_revision=pending.revision,
                expected_control_revision=control["revision"],
                actor_id=900,
                check=current_acl,
                now=now + 3,
            )
            assert (
                resolved.state == "confirmed"
                and ledger.has_access(recurring, now=now + 3).renewal == "canceled"
            )
            assert ledger.has_access(recurring, now=now + 3).expires_at == now + 2592000
            assert (
                len(
                    [
                        call
                        for call in session.calls
                        if isinstance(call, EditUserStarSubscription)
                    ]
                )
                == 3
            )
            print(
                json.dumps(
                    {
                        "passed": True,
                        "case": "bot_stars_payments",
                        "network": False,
                        "live_telegram_verified": False,
                    }
                )
            )
    finally:
        await bot.session.close()


asyncio.run(main())
