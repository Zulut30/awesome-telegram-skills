"""Real SDK/local SQLite Stars flows; no Telegram test account or payment is exercised."""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from _support import integration
from aiogram import Bot, Dispatcher, F, Router
from aiogram.methods import AnswerPreCheckoutQuery, CreateInvoiceLink, GetStarTransactions, RefundStarPayment
from aiogram.types import Message, Update

from telegram_patterns import Money, PaymentBinding, ProviderEvent, SQLitePaymentLedger
from telegram_patterns._aiogram.stars_payments import StarsPaymentAdapter
from telegram_patterns.aiogram import stars_invoice
from telegram_patterns.errors import PermissionDenied, UnknownOutcome, ValidationFailure
from telegram_patterns.payment_ledger import PaymentConflict, PaymentLeaseLost
from telegram_patterns.testing import StubSession

TOKEN = '100:STARS_FIXTURE_ONLY'


def _binding(**changes):
    values = dict(
        merchant_id='merchant:stars',
        bot_id=100,
        user_id=42,
        order_id='order:stars',
        provider='telegram',
        amount=Money(20, 'XTR', 0),
        route='telegram-stars',
    )
    values.update(changes)
    return PaymentBinding(**values)


def _allow(_db, operation, _replayed):
    return operation.actor_id in (42, 900)


def _apply(ledger, event, now=100):
    # Closed synthetic fixture only. A production verifier authenticates its ingress before mapping.
    token = object()

    def trusted(raw):
        if raw is not token:
            raise PermissionDenied()
        return event

    return ledger.apply_event(token, verify=trusted, now=now)


def _message(bot, adapter, binding, *, refunded=False, charge='native-charge', **changes):
    payment = dict(
        currency='XTR',
        total_amount=binding.amount.minor_units,
        invoice_payload=adapter.invoice_payload(binding, 'invoice:1'),
        telegram_payment_charge_id=charge,
        provider_payment_charge_id='',
    )
    payment.update(changes.pop('payment', {}))
    data = dict(
        message_id=10,
        date=100,
        chat={'id': 42, 'type': 'private'},
        **{'from': {'id': 42, 'is_bot': False, 'first_name': 'Fixture'}},
        **{'refunded_payment' if refunded else 'successful_payment': payment},
    )
    data.update(changes)
    return Message.model_validate(data, context={'bot': bot})


def _transaction(adapter, binding, **changes):
    data = dict(
        id='native-charge',
        amount=20,
        date=101,
        receiver={
            'type': 'user',
            'transaction_type': 'invoice_payment',
            'user': {'id': 42, 'is_bot': False, 'first_name': 'Fixture'},
            'invoice_payload': adapter.invoice_payload(binding, 'invoice:1'),
        },
    )
    data.update(changes)
    return data


def _prepare(database, binding):
    ledger = SQLitePaymentLedger(database)
    ledger.initialize()
    ledger.create_order(binding, 'invoice:1', now=90)
    _apply(
        ledger,
        ProviderEvent(
            binding,
            'fixture:paid',
            'paid',
            'successful_payment',
            'fixture:ingress',
            charge_id='native-charge',
            amount=binding.amount,
            paid_at=100,
        ),
    )
    return ledger


def _effect(database, *, crash):
    with closing(sqlite3.connect(database)) as remote:
        remote.execute('INSERT INTO calls(charge) VALUES (?)', ('native-charge',))
        remote.commit()
    if crash:
        os._exit(29)
    return True


def _refund_child(database, remote, gate, results, *, crash=False):
    async def run():
        session = StubSession().respond(RefundStarPayment, lambda _: _effect(remote, crash=crash))
        bot = Bot(TOKEN, session=session)
        ledger = SQLitePaymentLedger(database)
        adapter = StarsPaymentAdapter(bot, ledger)
        if gate is not None:
            await asyncio.to_thread(gate.wait, 15)
        try:
            state = await adapter.refund(_binding(), 'native-charge', 'refund:1', 900, check=_allow, now=100)
            if results is not None:
                results.put(state.state)
        except (PaymentLeaseLost, PaymentConflict):
            if results is not None:
                results.put('blocked')
        finally:
            await bot.session.close()

    asyncio.run(run())


class StarsPaymentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / 'finance.sqlite'
        self.binding = _binding()
        self.ledger = SQLitePaymentLedger(self.database)
        self.ledger.initialize()
        self.ledger.create_order(self.binding, 'invoice:1', now=90)
        self.session = StubSession().respond(RefundStarPayment, True)
        self.bot = Bot(TOKEN, session=self.session)
        self.adapter = StarsPaymentAdapter(self.bot, self.ledger)

    async def asyncTearDown(self):
        await self.bot.session.close()
        self.temp.cleanup()

    async def paid(self):
        event = await self.adapter.paid_event(
            self.binding,
            _message(self.bot, self.adapter, self.binding),
            invoice_operation_id='invoice:1',
            evidence_ref='fixture:paid',
        )
        _apply(self.ledger, event)

    async def unknown(self):
        await self.paid()
        return await self.adapter.refund(self.binding, 'native-charge', 'refund:1', 900, check=_allow, now=100)

    async def test_full_sdk_invoice_precheckout_paid_duplicate_refund_history_and_access(self):
        payload = self.adapter.invoice_payload(self.binding, 'invoice:1')
        self.session.respond(CreateInvoiceLink, 'https://t.me/$fixture').respond(AnswerPreCheckoutQuery, True)
        invoice = stars_invoice('Fixture', 'Fixture digital item', payload, 20)
        self.assertEqual(await self.bot(invoice), 'https://t.me/$fixture')
        self.assertFalse(self.ledger.has_access(self.binding, now=100).active)
        router = Router()

        @router.pre_checkout_query()
        async def checkout(query):
            async with asyncio.timeout(3):
                allowed = (
                    query.from_user.id == 42
                    and query.invoice_payload == payload
                    and query.currency == 'XTR'
                    and query.total_amount == 20
                )
                await query.answer(ok=allowed, error_message=None if allowed else 'Order unavailable')

        @router.message(F.successful_payment)
        async def payment(message):
            event = await self.adapter.paid_event(
                self.binding, message, invoice_operation_id='invoice:1', evidence_ref='fixture:authenticated-worker'
            )
            _apply(self.ledger, event)

        dispatcher = Dispatcher()
        dispatcher.include_router(router)
        user = {'id': 42, 'is_bot': False, 'first_name': 'Fixture'}
        query = {'id': 'checkout', 'from': user, 'currency': 'XTR', 'total_amount': 20, 'invoice_payload': payload}
        await dispatcher.feed_update(self.bot, Update.model_validate({'update_id': 1, 'pre_checkout_query': query}))
        self.assertTrue([call for call in self.session.calls if isinstance(call, AnswerPreCheckoutQuery)][0].ok)
        self.assertFalse(self.ledger.has_access(self.binding, now=100).active)
        message = _message(self.bot, self.adapter, self.binding)
        update = Update(update_id=2, message=message)
        await dispatcher.feed_update(self.bot, update)
        await dispatcher.feed_update(self.bot, update)
        self.assertEqual(self.ledger.get_order(self.binding).confirmed_charges, 1)
        self.assertTrue(self.ledger.has_access(self.binding, now=100).active)
        operation = await self.adapter.refund(self.binding, 'native-charge', 'refund:1', 900, check=_allow, now=100)
        self.assertEqual(operation.state, 'unknown')
        self.assertTrue(self.ledger.has_access(self.binding, now=101).active)
        self.session.respond(GetStarTransactions, {'transactions': [_transaction(self.adapter, self.binding)]})
        done = await self.adapter.reconcile_refund(
            self.binding, 'refund:1', 900, invoice_operation_id='invoice:1', check=_allow, now=101
        )
        self.assertEqual(done.state, 'confirmed')
        self.assertFalse(self.ledger.has_access(self.binding, now=101).active)
        sent = [call for call in self.session.calls if isinstance(call, RefundStarPayment)]
        self.assertEqual(len(sent), 1)
        self.assertEqual((sent[0].user_id, sent[0].telegram_payment_charge_id), (42, 'native-charge'))

    async def test_wrong_bot_owner_amount_currency_payload_and_context_never_map_payment(self):
        invalid = [
            _message(self.bot, self.adapter, self.binding, payment={'total_amount': 19}),
            _message(self.bot, self.adapter, self.binding, payment={'currency': 'USD'}),
            _message(self.bot, self.adapter, self.binding, payment={'invoice_payload': 'foreign'}),
            _message(self.bot, self.adapter, self.binding, chat={'id': 77, 'type': 'private'}),
            _message(self.bot, self.adapter, self.binding, chat={'id': 42, 'type': 'group'}),
            _message(self.bot, self.adapter, self.binding, business_connection_id='foreign'),
            _message(
                self.bot, self.adapter, self.binding, **{'from': {'id': 77, 'is_bot': False, 'first_name': 'Other'}}
            ),
            _message(
                self.bot,
                self.adapter,
                self.binding,
                payment={'is_recurring': True, 'subscription_expiration_date': 300},
            ),
        ]
        for index, message in enumerate(invalid):
            with self.subTest(case=index), self.assertRaises(PermissionDenied):
                await self.adapter.paid_event(
                    self.binding, message, invoice_operation_id='invoice:1', evidence_ref='fixture:wrong'
                )
        other_bot = Bot('101:OTHER_FIXTURE', session=StubSession())
        try:
            with self.assertRaises(PermissionDenied):
                await StarsPaymentAdapter(other_bot, self.ledger).paid_event(
                    self.binding, invalid[0], invoice_operation_id='invoice:1', evidence_ref='fixture:wrong'
                )
        finally:
            await other_bot.session.close()
        self.assertFalse(self.ledger.has_access(self.binding, now=100).active)
        self.assertEqual(self.session.calls, [])

    async def test_recurring_receipt_uses_native_period_and_refund_revokes_only_its_charge(self):
        binding = replace(self.binding, order_id='subscription:1', subscription_id='subscription:bound')
        self.ledger.create_order(binding, 'subscription-invoice', now=90)
        payload = self.adapter.invoice_payload(binding, 'subscription-invoice')
        for charge, paid_at, expires in [('first', 100, 200), ('second', 200, 300)]:
            message = _message(
                self.bot,
                self.adapter,
                binding,
                charge=charge,
                date=paid_at,
                payment={
                    'invoice_payload': payload,
                    'is_recurring': True,
                    'is_first_recurring': charge == 'first',
                    'subscription_expiration_date': expires,
                },
            )
            event = await self.adapter.paid_event(
                binding, message, invoice_operation_id='subscription-invoice', evidence_ref='fixture:subscription'
            )
            _apply(self.ledger, event, now=paid_at)
        self.assertTrue(self.ledger.has_access(binding, now=250).active)
        refund = _message(
            self.bot, self.adapter, binding, refunded=True, charge='first', payment={'invoice_payload': payload}
        )
        event = await self.adapter.refund_event(
            binding, refund, invoice_operation_id='subscription-invoice', evidence_ref='fixture:refund-subscription'
        )
        _apply(self.ledger, event, now=250)
        self.assertTrue(self.ledger.has_access(binding, now=250).active)
        self.assertFalse(self.ledger.has_access(binding, now=300).active)

    async def test_true_false_error_and_cancel_never_confirm_without_authoritative_refund(self):
        await self.paid()
        for response in (False, RuntimeError('fixture-private-detail')):
            with self.subTest(case=type(response).__name__):

                def result(_):
                    if isinstance(response, BaseException):
                        raise response
                    return response

                self.session.respond(RefundStarPayment, result)
                name = 'refund:' + type(response).__name__
                # Use a separate already-paid order to avoid reusing a held full refund budget.
                binding = replace(self.binding, order_id='order:' + type(response).__name__)
                self.ledger.create_order(binding, 'invoice:' + type(response).__name__, now=90)
                _apply(
                    self.ledger,
                    ProviderEvent(
                        binding,
                        'fixture:paid:' + name,
                        'paid',
                        'paid',
                        'fixture:paid',
                        charge_id='charge:' + name,
                        amount=binding.amount,
                        paid_at=100,
                    ),
                )
                with self.assertRaises(UnknownOutcome):
                    await self.adapter.refund(binding, 'charge:' + name, name, 900, check=_allow, now=100)
                self.assertEqual(self.ledger.get_operation(binding, name).state, 'unknown')
                self.assertTrue(self.ledger.has_access(binding, now=100).active)
        entered = asyncio.Event()

        async def suspended(_):
            entered.set()
            await asyncio.Event().wait()

        self.session.respond(RefundStarPayment, suspended)
        task = asyncio.create_task(
            self.adapter.refund(self.binding, 'native-charge', 'refund:cancel', 900, check=_allow, now=100)
        )
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.ledger.get_operation(self.binding, 'refund:cancel').state, 'unknown')
        self.assertTrue(self.ledger.has_access(self.binding, now=100).active)

    async def test_current_acl_at_reservation_start_and_replay_blocks_native_send(self):
        await self.paid()
        with self.assertRaises(PermissionDenied):
            await self.adapter.refund(self.binding, 'native-charge', 'refund:1', 900, check=lambda *_: False, now=100)
        checks = []

        def revoked_at_start(db, operation, replayed):
            self.assertTrue(db.in_transaction)
            checks.append((operation.state, replayed))
            return len(checks) == 1

        with self.assertRaises(PermissionDenied):
            await self.adapter.refund(self.binding, 'native-charge', 'refund:1', 900, check=revoked_at_start, now=100)
        self.assertEqual(checks, [('pending', False), ('pending', False)])
        self.assertEqual(self.session.calls, [])
        await self.adapter.refund(self.binding, 'native-charge', 'refund:1', 900, check=_allow, now=100)
        with self.assertRaises(PermissionDenied):
            await self.adapter.refund(self.binding, 'native-charge', 'refund:1', 900, check=lambda *_: False, now=101)
        self.assertEqual(len(self.session.calls), 1)
        with self.assertRaises(PaymentLeaseLost):
            await self.adapter.refund(self.binding, 'native-charge', 'refund:1', 900, check=_allow, now=101)
        self.assertEqual(len(self.session.calls), 1)

    async def test_history_mismatch_absence_direction_fraction_time_and_optional_payload_stay_unknown(self):
        await self.unknown()
        valid = _transaction(self.adapter, self.binding)
        wrong_partner = {**valid['receiver'], 'invoice_payload': None}
        other_user = {**valid['receiver'], 'user': {'id': 77, 'is_bot': False, 'first_name': 'Other'}}
        cases = [
            [],
            [{**valid, 'amount': 19}],
            [{**valid, 'amount': -20}],
            [{**valid, 'nanostar_amount': 1}],
            [{**valid, 'source': valid['receiver'], 'receiver': None}],
            [{**valid, 'receiver': other_user}],
            [{**valid, 'receiver': wrong_partner}],
            [{**valid, 'date': 99}],
            [{**valid, 'date': 102}],
            [{**valid, 'id': 'foreign-charge'}],
        ]
        for index, rows in enumerate(cases):
            self.session.respond(GetStarTransactions, {'transactions': rows})
            with self.subTest(case=index), self.assertRaises(UnknownOutcome):
                await self.adapter.reconcile_refund(
                    self.binding, 'refund:1', 900, invoice_operation_id='invoice:1', check=_allow, now=101
                )
            self.assertEqual(self.ledger.get_operation(self.binding, 'refund:1').state, 'unknown')
            self.assertTrue(self.ledger.has_access(self.binding, now=101).active)
        self.assertEqual(len([call for call in self.session.calls if isinstance(call, RefundStarPayment)]), 1)

    async def test_bounded_history_only_and_acl_recheck_before_lookup(self):
        await self.unknown()
        self.session.respond(
            GetStarTransactions, {'transactions': [_transaction(self.adapter, self.binding, id='unrelated')]}
        )
        with self.assertRaises(UnknownOutcome):
            await self.adapter.reconcile_refund(
                self.binding,
                'refund:1',
                900,
                invoice_operation_id='invoice:1',
                check=_allow,
                max_pages=2,
                page_size=1,
                now=101,
            )
        gets = [call for call in self.session.calls if isinstance(call, GetStarTransactions)]
        self.assertEqual([(call.offset, call.limit) for call in gets], [(0, 1), (1, 1)])
        with self.assertRaises(PermissionDenied):
            await self.adapter.reconcile_refund(
                self.binding, 'refund:1', 900, invoice_operation_id='invoice:1', check=lambda *_: False, now=101
            )
        self.assertEqual(len([call for call in self.session.calls if isinstance(call, GetStarTransactions)]), 2)

    async def test_refunded_update_after_history_is_one_financial_effect_and_wrong_amount_denied(self):
        await self.unknown()
        self.session.respond(GetStarTransactions, {'transactions': [_transaction(self.adapter, self.binding)]})
        await self.adapter.reconcile_refund(
            self.binding, 'refund:1', 900, invoice_operation_id='invoice:1', check=_allow, now=101
        )
        event = await self.adapter.refund_event(
            self.binding,
            _message(self.bot, self.adapter, self.binding, refunded=True),
            invoice_operation_id='invoice:1',
            evidence_ref='fixture:update',
        )
        _apply(self.ledger, event, now=101)
        self.assertTrue(_apply(self.ledger, event, now=101).duplicate)
        self.assertEqual(self.ledger.get_order(self.binding).fully_refunded_charges, 1)
        self.assertFalse(self.ledger.has_access(self.binding, now=101).active)
        with self.assertRaises(PermissionDenied):
            await self.adapter.refund_event(
                self.binding,
                _message(self.bot, self.adapter, self.binding, refunded=True, payment={'total_amount': 19}),
                invoice_operation_id='invoice:1',
                evidence_ref='fixture:wrong',
            )

    async def test_out_of_order_refunded_update_then_paid_never_grants_access(self):
        refund = _message(self.bot, self.adapter, self.binding, refunded=True)
        event = await self.adapter.refund_event(
            self.binding, refund, invoice_operation_id='invoice:1', evidence_ref='fixture:early-refund'
        )
        _apply(self.ledger, event, now=100)
        self.assertFalse(self.ledger.has_access(self.binding, now=100).active)
        await self.paid()
        self.assertFalse(self.ledger.has_access(self.binding, now=100).active)
        self.assertEqual(self.ledger.get_order(self.binding).fully_refunded_charges, 1)
        self.assertEqual(self.session.calls, [])

    async def test_trusted_refund_update_racing_native_reply_settles_without_extra_history(self):
        await self.paid()

        async def native_reply(_):
            event = await self.adapter.refund_event(
                self.binding,
                _message(self.bot, self.adapter, self.binding, refunded=True),
                invoice_operation_id='invoice:1',
                evidence_ref='fixture:concurrent-ingress',
                operation_id='refund:1',
            )
            _apply(self.ledger, event, now=101)
            return True

        self.session.respond(RefundStarPayment, native_reply)
        result = await self.adapter.refund(self.binding, 'native-charge', 'refund:1', 900, check=_allow, now=100)
        self.assertEqual(result.state, 'confirmed')
        self.assertFalse(self.ledger.has_access(self.binding, now=101).active)
        self.assertEqual(len(self.session.calls), 1)
        self.assertIsInstance(self.session.calls[0], RefundStarPayment)

    async def test_native_timeout_preserves_unknown_and_never_automatically_resends(self):
        await self.paid()
        entered = asyncio.Event()

        async def no_reply(_):
            entered.set()
            await asyncio.Event().wait()

        self.session.respond(RefundStarPayment, no_reply)
        adapter = StarsPaymentAdapter(self.bot, self.ledger, timeout_seconds=1)
        with self.assertRaises(UnknownOutcome):
            await adapter.refund(self.binding, 'native-charge', 'refund:timeout', 900, check=_allow, now=100)
        self.assertTrue(entered.is_set())
        self.assertEqual(self.ledger.get_operation(self.binding, 'refund:timeout').state, 'unknown')
        self.assertTrue(self.ledger.has_access(self.binding, now=100).active)
        self.assertEqual(len(self.session.calls), 1)

    async def test_subscription_period_boundary_and_naive_message_time_are_rejected(self):
        binding = replace(self.binding, order_id='subscription:invalid', subscription_id='bound:subscription')
        self.ledger.create_order(binding, 'subscription-invoice', now=90)
        payload = self.adapter.invoice_payload(binding, 'subscription-invoice')
        for expiration in (None, 99, 100):
            message = _message(
                self.bot,
                self.adapter,
                binding,
                payment={
                    'invoice_payload': payload,
                    'is_recurring': True,
                    'subscription_expiration_date': expiration,
                },
            )
            with self.subTest(case=str(expiration)), self.assertRaises(PermissionDenied):
                await self.adapter.paid_event(
                    binding, message, invoice_operation_id='subscription-invoice', evidence_ref='fixture:invalid-period'
                )
        naive = _message(self.bot, self.adapter, self.binding, date=datetime(2026, 1, 1))
        with self.assertRaises(ValidationFailure):
            await self.adapter.paid_event(
                self.binding, naive, invoice_operation_id='invoice:1', evidence_ref='fixture:naive-time'
            )

    async def test_constructor_route_history_limits_and_unstarted_reconciliation_are_explicit(self):
        for timeout in (0, 21, True):
            with self.subTest(case=str(timeout)), self.assertRaises(ValidationFailure):
                StarsPaymentAdapter(self.bot, self.ledger, timeout_seconds=timeout)
        with self.assertRaises(PermissionDenied):
            self.adapter.invoice_payload(replace(self.binding, bot_id=101), 'invoice:1')
        with self.assertRaises(PaymentConflict):
            await self.adapter.reconcile_refund(
                self.binding, 'invoice:1', 900, invoice_operation_id='invoice:1', check=_allow, now=100
            )
        await self.paid()
        self.ledger.request_refund(
            self.binding, 'native-charge', 'refund:1', self.binding.amount, 900, check=_allow, now=100
        )
        with self.assertRaises(PaymentConflict):
            await self.adapter.reconcile_refund(
                self.binding, 'refund:1', 900, invoice_operation_id='invoice:1', check=_allow, now=100
            )
        for options in ({'page_size': 0}, {'page_size': 101}, {'max_pages': 0}, {'max_pages': 21}):
            with self.subTest(case=next(iter(options))), self.assertRaises(ValidationFailure):
                await self.adapter.reconcile_refund(
                    self.binding, 'refund:1', 900, invoice_operation_id='invoice:1', check=_allow, now=100, **options
                )
        self.assertEqual(self.session.calls, [])


class StarsProcessTests(unittest.TestCase):
    @integration
    def test_crash_after_native_effect_reopens_and_history_reconciles_without_resending(self):
        with tempfile.TemporaryDirectory() as directory:
            database, remote = [str(Path(directory) / name) for name in ('finance.sqlite', 'telegram.sqlite')]
            binding = _binding()
            ledger = _prepare(database, binding)
            with closing(sqlite3.connect(remote)) as connection:
                connection.execute('CREATE TABLE calls(charge TEXT)')
                connection.commit()
            process = multiprocessing.get_context('spawn').Process(
                target=_refund_child, args=(database, remote, None, None), kwargs={'crash': True}
            )
            process.start()
            process.join(20)
            self.assertEqual(process.exitcode, 29)
            self.assertEqual(ledger.get_operation(binding, 'refund:1').state, 'sending')
            self.assertEqual(ledger.recover_expired(binding, now=120), 1)
            with closing(sqlite3.connect(remote)) as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM calls').fetchone()[0], 1)

            async def reconcile():
                session = StubSession()
                bot = Bot(TOKEN, session=session)
                adapter = StarsPaymentAdapter(bot, SQLitePaymentLedger(database))
                session.respond(GetStarTransactions, {'transactions': [_transaction(adapter, binding)]})
                try:
                    result = await adapter.reconcile_refund(
                        binding, 'refund:1', 900, invoice_operation_id='invoice:1', check=_allow, now=121
                    )
                    self.assertEqual(result.state, 'confirmed')
                    self.assertTrue(all(isinstance(call, GetStarTransactions) for call in session.calls))
                finally:
                    await bot.session.close()

            asyncio.run(reconcile())
            self.assertFalse(SQLitePaymentLedger(database).has_access(binding, now=121).active)

    @integration
    def test_two_processes_cannot_dispatch_same_full_refund_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            database, remote = [str(Path(directory) / name) for name in ('finance.sqlite', 'telegram.sqlite')]
            ledger = _prepare(database, _binding())
            with closing(sqlite3.connect(remote)) as connection:
                connection.execute('CREATE TABLE calls(charge TEXT)')
                connection.commit()
            context = multiprocessing.get_context('spawn')
            gate, results = context.Barrier(2), context.Queue()
            children = [context.Process(target=_refund_child, args=(database, remote, gate, results)) for _ in range(2)]
            for process in children:
                process.start()
            for process in children:
                process.join(20)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(sorted(results.get(timeout=5) for _ in children), ['blocked', 'unknown'])
            with closing(sqlite3.connect(remote)) as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM calls').fetchone()[0], 1)
            self.assertEqual(ledger.get_operation(_binding(), 'refund:1').state, 'unknown')


if __name__ == '__main__':
    unittest.main()
