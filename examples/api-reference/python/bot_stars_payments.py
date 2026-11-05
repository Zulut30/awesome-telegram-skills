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
    GetStarTransactions,
    RefundStarPayment,
)
from aiogram.types import Message, PreCheckoutQuery, Update
from bot_fixture import ACTOR, DATE, TOKEN
from telegram_patterns import (
    Money,
    PaymentBinding,
    PaymentOperation,
    ProviderEvent,
    SQLitePaymentLedger,
    settled_to_thread,
)
from telegram_patterns.aiogram import StarsPaymentAdapter, stars_invoice
from telegram_patterns.testing import StubSession


def apply_fixture(ledger: SQLitePaymentLedger, event: ProviderEvent, *, now: int) -> bool:
    # Только закрытая синтетическая фикстура. Реальный host принимает update своим проверенным ingress.
    token = object()

    def verified(raw: object) -> ProviderEvent:
        if raw is not token:
            raise ValueError('Untrusted fixture input')
        return event

    return ledger.apply_event(token, verify=verified, now=now).duplicate


def current_acl(connection: sqlite3.Connection, operation: PaymentOperation, replayed: bool) -> bool:
    # Реальное приложение читает текущую роль оператора в этой же writer-транзакции.
    return connection.in_transaction and operation.actor_id in (42, 900) and type(replayed) is bool


async def main() -> None:
    session = (StubSession().respond(CreateInvoiceLink, 'https://t.me/$stars_fixture')
               .respond(AnswerPreCheckoutQuery, True).respond(RefundStarPayment, True))
    bot = Bot(TOKEN, session=session)
    try:
        with TemporaryDirectory() as directory:
            ledger = SQLitePaymentLedger(Path(directory) / 'stars.sqlite')
            ledger.initialize()
            binding = PaymentBinding('merchant:fixture', bot.id, ACTOR.id, 'order:fixture', 'telegram',
                                     Money(20, 'XTR', 0), route='telegram-stars')
            adapter = StarsPaymentAdapter(bot, ledger)
            now = int(DATE.timestamp())
            payload = adapter.invoice_payload(binding, 'invoice:1')
            await settled_to_thread(ledger.create_order, binding, 'invoice:1', now=now)
            await settled_to_thread(ledger.start_operation, binding, 'invoice:1', 'invoice-worker',
                                    check=current_acl, now=now)
            invoice = stars_invoice('Fixture', 'Digital item', payload, 20)
            link = await bot(invoice)
            assert link == 'https://t.me/$stars_fixture'
            await settled_to_thread(apply_fixture, ledger, ProviderEvent(
                binding, 'fixture:invoice', 'invoice-created', 'created', 'fixture:native-link',
                operation_id='invoice:1', provider_ref=link), now=now)
            assert not ledger.has_access(binding, now=now).active
            router = Router(name='fixture-stars')

            @router.pre_checkout_query()
            async def checkout(query: PreCheckoutQuery) -> None:
                # Срок Telegram — 10 секунд; локальный бюджет проверки — 3 секунды.
                async with asyncio.timeout(3):
                    saved = await settled_to_thread(ledger.get_order, binding)
                    allowed = (query.from_user.id == binding.user_id and query.invoice_payload == payload
                               and query.currency == 'XTR' and query.total_amount == saved.binding.amount.minor_units)
                    await query.answer(ok=allowed, error_message=None if allowed else 'Order unavailable')

            @router.message(F.successful_payment)
            async def paid(message: Message) -> None:
                # Сюда реальный host передает только update из аутентифицированного долговечного входа.
                event = await adapter.paid_event(binding, message, invoice_operation_id='invoice:1',
                                                  evidence_ref='fixture:trusted-worker')
                await settled_to_thread(apply_fixture, ledger, event, now=now)

            dispatcher = Dispatcher()
            dispatcher.include_router(router)
            user = ACTOR.model_dump(mode='json')
            query = Update.model_validate({'update_id': 1, 'pre_checkout_query': {
                'id': 'query-fixture', 'from': user, 'currency': 'XTR', 'total_amount': 20,
                'invoice_payload': payload}})
            await dispatcher.feed_update(bot, query)
            answers = [call for call in session.calls if isinstance(call, AnswerPreCheckoutQuery)]
            assert len(answers) == 1 and answers[0].ok is True
            assert not ledger.has_access(binding, now=now).active
            update = Update.model_validate({'update_id': 2, 'message': {
                'message_id': 1, 'date': now, 'chat': {'id': 42, 'type': 'private'}, 'from': user,
                'successful_payment': {'currency': 'XTR', 'total_amount': 20, 'invoice_payload': payload,
                                       'telegram_payment_charge_id': 'charge-fixture',
                                       'provider_payment_charge_id': ''}}})
            await dispatcher.feed_update(bot, update)
            await dispatcher.feed_update(bot, update)
            assert ledger.has_access(binding, now=now).active and ledger.get_order(binding).confirmed_charges == 1
            result = await adapter.refund(binding, 'charge-fixture', 'refund:1', 900, check=current_acl, now=now)
            assert result.state == 'unknown' and ledger.has_access(binding, now=now).active
            # Официальный Bot API показывает положительную величину исходящей операции в receiver.
            session.respond(GetStarTransactions, {'transactions': [{
                'id': 'charge-fixture', 'amount': 20, 'date': now + 1,
                'receiver': {'type': 'user', 'transaction_type': 'invoice_payment', 'user': user,
                             'invoice_payload': payload}}]})
            final = await adapter.reconcile_refund(binding, 'refund:1', 900, invoice_operation_id='invoice:1',
                                                    check=current_acl, now=now + 1)
            assert final.state == 'confirmed' and not ledger.has_access(binding, now=now + 1).active
            assert len([call for call in session.calls if isinstance(call, RefundStarPayment)]) == 1
            print(json.dumps({'passed': True, 'case': 'bot_stars_payments', 'network': False,
                              'live_telegram_verified': False}))
    finally:
        await bot.session.close()


asyncio.run(main())
