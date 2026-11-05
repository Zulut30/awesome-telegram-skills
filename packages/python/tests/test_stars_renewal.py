"""Stars renewal edits through the real SDK with durable ordering and explicit manual reconciliation."""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from _support import integration, requires_aiogram
from aiogram import Bot, Dispatcher
from aiogram.methods import EditUserStarSubscription
from aiogram.types import Update
from test_stars_payments import TOKEN, _allow, _apply, _binding

from telegram_patterns import ProviderEvent, SQLitePaymentLedger
from telegram_patterns.aiogram import StarsPaymentAdapter
from telegram_patterns.errors import PermissionDenied, UnknownOutcome
from telegram_patterns.payment_ledger import PaymentConflict, PaymentLeaseLost
from telegram_patterns.testing import StubSession


def _subscription_binding():
    return _binding(order_id='subscription:order', subscription_id='subscription:bound')


def _prepare(database):
    binding = _subscription_binding()
    ledger = SQLitePaymentLedger(database)
    ledger.initialize()
    ledger.create_order(binding, 'invoice:1', now=90)
    _apply(
        ledger,
        ProviderEvent(
            binding,
            'fixture:subscription-paid',
            'paid',
            'successful_payment',
            'fixture:paid',
            charge_id='native-charge',
            amount=binding.amount,
            paid_at=100,
            period_start=100,
            period_end=200,
            first_recurring=True,
        ),
    )
    ledger.register_renewal_stream(binding, 'stream:one')
    return ledger


def _effect(remote, canceled, *, crash=False):
    with closing(sqlite3.connect(remote)) as connection:
        connection.execute('INSERT INTO calls(canceled) VALUES (?)', (int(canceled),))
        connection.execute('UPDATE setting SET canceled=?', (int(canceled),))
        connection.commit()
    if crash:
        os._exit(31)
    return True


def _renewal_child(database, remote, gate, entered, release, results, canceled, *, crash=False):
    async def run():
        async def native(method):
            _effect(remote, method.is_canceled, crash=crash)
            if entered is not None:
                entered.set()
                if not await asyncio.to_thread(release.wait, 15):
                    raise AssertionError('Parent did not release the native reply')
            return True

        session = StubSession().respond(EditUserStarSubscription, native)
        bot = Bot(TOKEN, session=session)
        adapter = StarsPaymentAdapter(bot, SQLitePaymentLedger(database))
        if gate is not None:
            await asyncio.to_thread(gate.wait, 15)
        try:
            operation = await adapter.edit_renewal(
                _subscription_binding(),
                'native-charge',
                'edit:cancel' if canceled else 'edit:resume',
                900,
                is_canceled=canceled,
                check=_allow,
                now=101,
            )
            if results is not None:
                results.put(operation.state)
        except (PaymentConflict, PaymentLeaseLost):
            if results is not None:
                results.put('blocked')
        finally:
            await bot.session.close()

    asyncio.run(run())


class StarsRenewalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / 'stars.sqlite'
        self.ledger = _prepare(self.database)
        self.binding = _subscription_binding()
        self.session = StubSession().respond(EditUserStarSubscription, True)
        self.bot = Bot(TOKEN, session=self.session)
        self.adapter = StarsPaymentAdapter(self.bot, self.ledger)

    async def asyncTearDown(self):
        await self.bot.session.close()
        self.temp.cleanup()

    def update(self, native_id, state, **changes):
        native = {
            'user': {'id': 42, 'is_bot': False, 'first_name': 'Fixture'},
            'invoice_payload': self.adapter.invoice_payload(self.binding, 'invoice:1'),
            'state': state,
        }
        native.update(changes)
        return Update.model_validate({'update_id': native_id, 'subscription': native}, context={'bot': self.bot})

    async def edit(self, operation='edit:cancel', *, canceled=True, check=_allow):
        return await self.adapter.edit_renewal(
            self.binding, 'native-charge', operation, 900, is_canceled=canceled, check=check, now=101
        )

    async def test_actual_native_cancel_resume_and_cancel_preserve_exact_paid_period(self):
        before = self.ledger.get_charge(self.binding, 'native-charge')
        for operation, canceled in [('cancel:one', True), ('resume:one', False), ('cancel:two', True)]:
            result = await self.edit(operation, canceled=canceled)
            self.assertEqual(result.state, 'confirmed')
            decision = self.ledger.has_access(self.binding, now=199)
            self.assertTrue(decision.active)
            self.assertEqual((decision.expires_at, decision.renewal), (200, 'canceled' if canceled else 'active'))
            self.assertFalse(self.ledger.has_access(self.binding, now=200).active)
        self.assertEqual(self.ledger.get_charge(self.binding, 'native-charge'), before)
        self.assertEqual(
            [(call.user_id, call.telegram_payment_charge_id, call.is_canceled) for call in self.session.calls],
            [(42, 'native-charge', True), (42, 'native-charge', False), (42, 'native-charge', True)],
        )

    async def test_resume_without_bot_cancel_and_replayed_or_changed_intent_never_send(self):
        with self.assertRaises(PaymentConflict):
            await self.edit('resume:unproven', canceled=False)
        self.assertEqual(self.session.calls, [])
        await self.edit()
        with self.assertRaises(PaymentLeaseLost):
            await self.edit()
        with self.assertRaises(PaymentConflict):
            await self.edit(canceled=False)
        self.assertEqual(len(self.session.calls), 1)

    async def test_current_acl_denial_at_reserve_start_and_replay_prevents_native_edit(self):
        with self.assertRaises(PermissionDenied):
            await self.edit(check=lambda *_: False)
        self.assertEqual(self.session.calls, [])
        calls = []

        def revoked(db, operation, replayed):
            self.assertTrue(db.in_transaction)
            calls.append((operation.state, replayed))
            return len(calls) == 1

        with self.assertRaises(PermissionDenied):
            await self.edit(check=revoked)
        self.assertEqual(calls, [('pending', False), ('pending', False)])
        self.assertEqual(self.session.calls, [])
        await self.edit()
        with self.assertRaises(PermissionDenied):
            await self.edit(check=lambda *_: False)
        self.assertEqual(len(self.session.calls), 1)

    @requires_aiogram((3, 31), 'BotSubscriptionUpdated observer')
    async def test_router_handles_native_update_identity_order_and_duplicate_without_granting_time(self):
        async def lookup(native):
            return (self.binding, 'invoice:1') if native.user.id == 42 else None

        dispatcher = Dispatcher()
        dispatcher.include_router(self.adapter.subscription_router(lookup, stream_epoch='stream:one'))
        self.assertIn('subscription', dispatcher.resolve_used_update_types())
        for update in [
            self.update(10, 'canceled'),
            self.update(12, 'active'),
            self.update(11, 'canceled'),
            self.update(12, 'active'),
        ]:
            await dispatcher.feed_update(self.bot, update)
        control = self.ledger.get_renewal_control(self.binding)
        self.assertEqual((control['last_update_id'], control['effective_state']), (12, 'active'))
        self.assertEqual(self.ledger.has_access(self.binding, now=150).expires_at, 200)
        self.assertFalse(self.ledger.has_access(self.binding, now=200).active)
        self.assertEqual(self.session.calls, [])
        outcomes = [entry['outcome'] for entry in self.ledger.audit(self.binding)]
        self.assertIn('stale', outcomes)
        self.assertIn('duplicate', outcomes)

    @requires_aiogram((3, 31), 'BotSubscriptionUpdated observer')
    async def test_foreign_user_payload_bot_epoch_and_unknown_state_are_rejected(self):
        cases = [
            self.update(1, 'active', user={'id': 77, 'is_bot': False, 'first_name': 'Other'}),
            self.update(1, 'active', invoice_payload='foreign'),
            self.update(1, 'future-state'),
        ]
        for index, update in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(PermissionDenied):
                await self.adapter.subscription_event(
                    self.binding,
                    update,
                    invoice_operation_id='invoice:1',
                    stream_epoch='stream:one',
                    evidence_ref='fixture:wrong',
                )
        with self.assertRaises(PaymentConflict):
            await self.adapter.subscription_event(
                self.binding,
                self.update(1, 'active'),
                invoice_operation_id='invoice:1',
                stream_epoch='foreign:epoch',
                evidence_ref='fixture:wrong',
            )
        other = Bot('101:OTHER_FIXTURE', session=StubSession())
        try:
            with self.assertRaises(PermissionDenied):
                await StarsPaymentAdapter(other, self.ledger).subscription_event(
                    self.binding,
                    self.update(1, 'active'),
                    invoice_operation_id='invoice:1',
                    stream_epoch='stream:one',
                    evidence_ref='fixture:wrong',
                )
        finally:
            await other.session.close()
        self.assertEqual(self.ledger.get_renewal_control(self.binding)['last_update_id'], -1)
        self.assertEqual(self.session.calls, [])

    @requires_aiogram((3, 31), 'BotSubscriptionUpdated observer')
    async def test_lost_reply_and_matching_update_keep_operation_unknown_without_second_edit(self):
        effects = []

        def lost_reply(method):
            effects.append(method.is_canceled)
            raise EOFError('Native fixture effect committed but reply lost')

        self.session.respond(EditUserStarSubscription, lost_reply)
        with self.assertRaises(UnknownOutcome):
            await self.edit()
        event = await self.adapter.subscription_event(
            self.binding,
            self.update(5, 'canceled'),
            invoice_operation_id='invoice:1',
            stream_epoch='stream:one',
            evidence_ref='fixture:uncorrelated',
        )
        _apply(self.ledger, event, now=102)
        self.assertEqual(self.ledger.get_operation(self.binding, 'edit:cancel').state, 'unknown')
        self.assertEqual(self.ledger.has_access(self.binding, now=150).renewal, 'unknown')
        with self.assertRaises(PaymentConflict):
            await self.edit('edit:new-id')
        self.assertEqual(effects, [True])
        self.assertEqual(len(self.session.calls), 1)

    async def test_task_cancel_after_dispatch_keeps_started_change_unknown(self):
        entered = asyncio.Event()

        async def delayed(_):
            entered.set()
            await asyncio.Event().wait()

        self.session.respond(EditUserStarSubscription, delayed)
        task = asyncio.create_task(self.edit())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.ledger.get_operation(self.binding, 'edit:cancel').state, 'unknown')
        self.assertTrue(self.ledger.has_access(self.binding, now=199).active)
        self.assertEqual(len(self.session.calls), 1)

    async def test_native_false_response_never_confirms_or_retries_setting(self):
        self.session.respond(EditUserStarSubscription, False)
        with self.assertRaises(UnknownOutcome):
            await self.edit()
        self.assertEqual(self.ledger.get_operation(self.binding, 'edit:cancel').state, 'unknown')
        self.assertEqual(self.ledger.has_access(self.binding, now=150).renewal, 'unknown')
        self.assertEqual(len(self.session.calls), 1)

    @requires_aiogram((3, 31), 'BotSubscriptionUpdated observer')
    async def test_conflicting_update_during_native_edit_keeps_future_unknown_after_true_reply(self):
        async def concurrent(method):
            self.assertTrue(method.is_canceled)
            observed = await self.adapter.subscription_event(
                self.binding,
                self.update(1, 'active'),
                invoice_operation_id='invoice:1',
                stream_epoch='stream:one',
                evidence_ref='fixture:during-rpc',
            )
            _apply(self.ledger, observed, now=101)
            return True

        self.session.respond(EditUserStarSubscription, concurrent)
        operation = await self.edit()
        self.assertEqual(operation.state, 'confirmed')
        self.assertEqual(self.ledger.get_renewal_control(self.binding)['effective_state'], 'unknown')
        self.assertEqual(self.ledger.has_access(self.binding, now=199).expires_at, 200)
        self.assertFalse(self.ledger.has_access(self.binding, now=200).active)
        self.assertEqual(len(self.session.calls), 1)

    @requires_aiogram((3, 31), 'BotSubscriptionUpdated observer')
    async def test_one_native_update_id_cannot_be_rebound_to_another_subscription(self):
        first = await self.adapter.subscription_event(
            self.binding,
            self.update(10, 'active'),
            invoice_operation_id='invoice:1',
            stream_epoch='stream:one',
            evidence_ref='fixture:first',
        )
        _apply(self.ledger, first)
        other = replace(self.binding, order_id='other:order', user_id=77, subscription_id='other:subscription')
        self.ledger.create_order(other, 'other:invoice', now=90)
        self.ledger.register_renewal_stream(other, 'stream:one')
        native = Update.model_validate(
            {
                'update_id': 10,
                'subscription': {
                    'user': {'id': 77, 'is_bot': False, 'first_name': 'Other'},
                    'invoice_payload': self.adapter.invoice_payload(other, 'other:invoice'),
                    'state': 'canceled',
                },
            },
            context={'bot': self.bot},
        )
        second = await self.adapter.subscription_event(
            other,
            native,
            invoice_operation_id='other:invoice',
            stream_epoch='stream:one',
            evidence_ref='fixture:conflicting-native-id',
        )
        self.assertEqual(first.event_id, second.event_id)
        with self.assertRaises(PaymentConflict):
            _apply(self.ledger, second)
        self.assertEqual(self.ledger.get_renewal_control(other)['last_update_id'], -1)

    async def test_native_timeout_is_unknown_and_does_not_send_again(self):
        async def delayed(_):
            await asyncio.Event().wait()

        self.session.respond(EditUserStarSubscription, delayed)
        adapter = StarsPaymentAdapter(self.bot, self.ledger, timeout_seconds=1)
        with self.assertRaises(UnknownOutcome):
            await adapter.edit_renewal(
                self.binding, 'native-charge', 'edit:timeout', 900, is_canceled=True, check=_allow, now=101
            )
        self.assertEqual(self.ledger.get_operation(self.binding, 'edit:timeout').state, 'unknown')
        self.assertEqual(len(self.session.calls), 1)


class StarsRenewalProcessTests(unittest.TestCase):
    def remote(self, path):
        with closing(sqlite3.connect(path)) as connection:
            connection.execute('CREATE TABLE calls(canceled INTEGER)')
            connection.execute('CREATE TABLE setting(canceled INTEGER)')
            connection.execute('INSERT INTO setting VALUES (0)')
            connection.commit()

    @integration
    def test_crash_after_separate_native_effect_reopens_and_manual_proof_reconciles_without_rpc_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            database, remote = [str(Path(directory) / name) for name in ('finance.sqlite', 'native.sqlite')]
            ledger = _prepare(database)
            binding = _subscription_binding()
            self.remote(remote)
            context = multiprocessing.get_context('spawn')
            child = context.Process(
                target=_renewal_child, args=(database, remote, None, None, None, None, True), kwargs={'crash': True}
            )
            child.start()
            child.join(20)
            if child.is_alive():
                child.terminate()
                child.join(5)
                self.fail('Native effect worker did not finish')
            self.assertEqual(child.exitcode, 31)
            self.assertEqual(ledger.get_operation(binding, 'edit:cancel').state, 'sending')
            self.assertEqual(ledger.recover_expired(binding, now=121), 1)
            unknown = ledger.get_operation(binding, 'edit:cancel')
            control = ledger.get_renewal_control(binding)
            with closing(sqlite3.connect(remote)) as native:
                self.assertEqual(native.execute('SELECT count(*) FROM calls').fetchone()[0], 1)
                self.assertEqual(native.execute('SELECT canceled FROM setting').fetchone()[0], 1)

            async def reconcile():
                session = StubSession()  # No invented official renewal-status GET or repeated write.
                bot = Bot(TOKEN, session=session)
                adapter = StarsPaymentAdapter(bot, SQLitePaymentLedger(database))
                token = object()

                def verified(raw):
                    if raw is not token:
                        raise PermissionDenied()
                    # Explicit independent operator/provider fixture proof, not a Telegram API endpoint.
                    with closing(sqlite3.connect(remote)) as native:
                        if native.execute('SELECT canceled FROM setting').fetchone()[0] != 1:
                            raise PermissionDenied()
                    return ProviderEvent(
                        binding,
                        'operator:verified-setting',
                        'renewal-state',
                        'operator-verified',
                        'fixture:separate-native-db',
                        operation_id='edit:cancel',
                        charge_id='native-charge',
                        renewal='canceled',
                    )

                try:
                    result = await adapter.reconcile_renewal(
                        binding,
                        'edit:cancel',
                        token,
                        verify=verified,
                        expected_revision=unknown.revision,
                        expected_control_revision=control['revision'],
                        actor_id=900,
                        check=_allow,
                        now=122,
                    )
                    self.assertEqual(result.state, 'confirmed')
                    self.assertEqual(session.calls, [])
                finally:
                    await bot.session.close()

            asyncio.run(reconcile())
            self.assertEqual(SQLitePaymentLedger(database).has_access(binding, now=150).renewal, 'canceled')
            self.assertFalse(SQLitePaymentLedger(database).has_access(binding, now=200).active)

    @integration
    def test_concurrent_cancel_resume_different_ids_cannot_both_dispatch_while_effect_is_unresolved(self):
        with tempfile.TemporaryDirectory() as directory:
            database, remote = [str(Path(directory) / name) for name in ('finance.sqlite', 'native.sqlite')]
            _prepare(database)
            self.remote(remote)

            async def initial_cancel():
                session = StubSession().respond(
                    EditUserStarSubscription, lambda method: _effect(remote, method.is_canceled)
                )
                bot = Bot(TOKEN, session=session)
                try:
                    await StarsPaymentAdapter(bot, SQLitePaymentLedger(database)).edit_renewal(
                        _subscription_binding(),
                        'native-charge',
                        'initial:cancel',
                        900,
                        is_canceled=True,
                        check=_allow,
                        now=100,
                    )
                finally:
                    await bot.session.close()

            asyncio.run(initial_cancel())
            context = multiprocessing.get_context('spawn')
            gate, entered, release, results = context.Barrier(2), context.Event(), context.Event(), context.Queue()
            children = [
                context.Process(
                    target=_renewal_child, args=(database, remote, gate, entered, release, results, canceled)
                )
                for canceled in (True, False)
            ]
            for child in children:
                child.start()
            try:
                self.assertTrue(entered.wait(20))
                self.assertEqual(results.get(timeout=10), 'blocked')
            finally:
                release.set()
                for child in children:
                    child.join(20)
                    if child.is_alive():
                        child.terminate()
                        child.join(5)
            self.assertTrue(all(child.exitcode == 0 for child in children))
            self.assertEqual(results.get(timeout=10), 'confirmed')
            with closing(sqlite3.connect(remote)) as native:
                self.assertEqual(native.execute('SELECT count(*) FROM calls').fetchone()[0], 2)  # Initial + one winner.


if __name__ == '__main__':
    unittest.main()
