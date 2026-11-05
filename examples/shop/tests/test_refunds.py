"""Real HTTP/file SQLite and an independent persistent fake Stars service; no live payments."""

from __future__ import annotations

import asyncio
import copy
import json
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.methods import GetMe, GetStarTransactions, GetUpdates, RefundStarPayment
from aiogram.types import Message
from aiohttp import ClientConnectionError, ClientSession, web
from telegram_patterns import PaymentConflict, PermissionDenied
from telegram_shop_example.api import create_app
from telegram_shop_example.offline import SUPPORT, TERMS, TOKEN, signed, stub, update
from telegram_shop_example.offline_refunds import FakeStarsHistory
from telegram_shop_example.payments import payment_router
from telegram_shop_example.polling import PollingReadFailure, ShopDurablePolling
from telegram_shop_example.refunds import ShopRefunds
from telegram_shop_example.storage import connection
from telegram_shop_example.store import Store


class RefundTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shop-refunds-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "shop.sqlite"
        self.clock = [int(time.time())]
        self.store = self.reopen()
        self.store.configure_operator(77, True)
        self.provider = FakeStarsHistory(self.root / "independent-fake-stars.sqlite")
        self.transport = stub()
        self.bot = Bot(TOKEN, session=self.transport)
        self.addAsyncCleanup(self.transport.close)
        self.transport.respond(RefundStarPayment, self.refund_effect).respond(
            GetStarTransactions, self.history
        )
        self.financial = ShopRefunds(self.store, self.bot, timeout_seconds=2)
        self.operator = self.store.session(signed(77, timestamp=self.clock[0]))["token"]
        self.buyer = self.store.session(signed(42, timestamp=self.clock[0]))["token"]
        self.frontend = self.root / "frontend"
        (self.frontend / "assets").mkdir(parents=True)
        (self.frontend / "index.html").write_text(
            "<html><!-- telegram-sdk --></html>", encoding="utf-8"
        )
        self.client = ClientSession()
        self.addAsyncCleanup(self.client.close)

    def reopen(self):
        return Store(
            self.database, TOKEN, terms_version="demo-v1", now=lambda: self.clock[0]
        )

    def refund_effect(self, method):
        return self.provider.refund(
            method.user_id, method.telegram_payment_charge_id, self.clock[0]
        )

    def history(self, method):
        return self.provider.history(method.offset or 0, method.limit or 100)

    def row(self):
        row = self.store.create(42, str(uuid.uuid4()), ["bot-kit"], "demo-v1")
        self.store.claim_invoice(42, row["id"])
        return row

    async def paid(self, row=None, charge="primary-charge"):
        row = row or self.row()
        message = update(self.store, row, charge=charge).message.as_(self.bot)
        result = await self.financial.paid(message)
        self.provider.paid(
            charge,
            42,
            row["total"],
            self.store.payload(row["id"]),
            int(message.date.timestamp()),
        )
        return row, result

    def refunded_message(self, row, charge="primary-charge", **changes):
        fields = {
            "currency": "XTR",
            "total_amount": row["total"],
            "invoice_payload": self.store.payload(row["id"]),
            "telegram_payment_charge_id": charge,
        } | changes
        return Message.model_validate(
            {
                "message_id": 9,
                "date": self.clock[0],
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42, "is_bot": False, "first_name": "Fixture"},
                "refunded_payment": fields,
            },
            context={"bot": self.bot},
        )

    @asynccontextmanager
    async def running(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        sock.setblocking(False)
        origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
        app = create_app(
            self.store,
            self.bot,
            self.frontend,
            origin=origin,
            terms=TERMS,
            support=SUPPORT,
            loopback_dev=True,
        )

        @web.middleware
        async def lost_reply(request, handler):
            response = await handler(request)
            if (
                request.headers.get("X-Fixture-Drop-Reply") == "yes"
                and response.status == 200
            ):
                request.transport.abort()
            return response

        app.middlewares.append(lost_reply)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        await web.SockSite(runner, sock).start()
        try:
            yield origin
        finally:
            await runner.cleanup()

    async def call(self, origin, method, path, *, token=None, body=None, status=200):
        headers = {"Origin": origin}
        if token:
            headers["Authorization"] = "Bearer " + token
        async with self.client.request(
            method, origin + path, json=body, headers=headers
        ) as response:
            self.assertEqual(response.status, status, f"{method} {path}")
            return await response.json()

    @staticmethod
    def path(row):
        return "/api/operator/orders/" + row["id"] + "/refunds"

    async def test_operator_role_and_body_fields_never_authorize_a_buyer_refund(self):
        row, _ = await self.paid()
        request = {"operation": str(uuid.uuid4()), "charge": "primary-charge"}
        async with self.running() as origin:
            await self.call(
                origin,
                "GET",
                "/api/operator/orders/" + row["id"],
                token=self.buyer,
                status=403,
            )
            await self.call(
                origin,
                "POST",
                self.path(row),
                token=self.buyer,
                body=request,
                status=403,
            )
            for extra in (
                {"actor_id": 77},
                {"user_id": 42},
                {"role": "operator"},
                {"amount": 1},
                {"currency": "XTR"},
            ):
                await self.call(
                    origin,
                    "POST",
                    self.path(row),
                    token=self.operator,
                    body=request | extra,
                    status=422,
                )
            self.assertEqual(self.provider.calls(), 0)
            result = await self.call(
                origin, "POST", self.path(row), token=self.operator, body=request
            )
            self.assertEqual(result["state"], "unknown")
            self.assertEqual(self.provider.calls(), 1)
            await self.call(origin, "GET", "/api/content/bot-kit", token=self.buyer)
            calls = [
                call
                for call in self.transport.calls
                if isinstance(call, RefundStarPayment)
            ]
            self.assertEqual(
                [(call.user_id, call.telegram_payment_charge_id) for call in calls],
                [(42, "primary-charge")],
            )
            self.store.configure_operator(77, False)
            await self.call(
                origin,
                "GET",
                self.path(row) + "/" + request["operation"],
                token=self.operator,
                status=403,
            )
        with connection(self.database) as db:
            audit = [
                tuple(row)
                for row in db.execute(
                    "SELECT actor_id,action,outcome FROM shop_operator_audit"
                )
            ]
        self.assertEqual(
            audit,
            [
                (77, "refund-request", "intent-saved"),
                (77, "refund-dispatch", "unknown"),
            ],
        )

    async def test_lost_native_and_http_replies_preserve_one_refund_across_explicit_replay(
        self,
    ):
        row, _ = await self.paid()
        request = {"operation": str(uuid.uuid4()), "charge": "primary-charge"}

        def lost(method):
            self.refund_effect(method)
            raise TimeoutError("Synthetic lost native reply after commit")

        self.transport.respond(RefundStarPayment, lost)
        async with self.running() as origin:
            with self.assertRaises(ClientConnectionError):
                async with self.client.post(
                    origin + self.path(row),
                    json=request,
                    headers={
                        "Origin": origin,
                        "Authorization": "Bearer " + self.operator,
                        "X-Fixture-Drop-Reply": "yes",
                    },
                ) as response:
                    await response.read()
            self.assertEqual(self.provider.calls(), 1)
            result = await self.call(
                origin, "POST", self.path(row), token=self.operator, body=request
            )
            self.assertEqual(result["state"], "unknown")
            self.assertEqual(self.provider.calls(), 1)
            await self.call(
                origin,
                "POST",
                self.path(row),
                token=self.operator,
                body=request | {"operation": str(uuid.uuid4())},
                status=409,
            )
            await self.call(
                origin,
                "POST",
                self.path(row),
                token=self.operator,
                body=request | {"charge": "different-charge"},
                status=409,
            )
            result = await self.call(
                origin,
                "GET",
                self.path(row) + "/" + request["operation"],
                token=self.operator,
            )
            self.assertEqual(result["state"], "unknown")
            self.assertEqual(self.provider.calls(), 1)
        reopened = self.reopen()
        link = reopened.payment_link(row["id"], "primary-charge")
        self.assertEqual(
            reopened.financial.get_operation(
                reopened.link_binding(link), request["operation"]
            ).state,
            "unknown",
        )

    async def test_current_operator_and_session_are_rechecked_between_reserve_and_send(
        self,
    ):
        row, _ = await self.paid()
        operation = str(uuid.uuid4())
        original = self.store.financial.start_operation

        def revoked(*args, **kwargs):
            self.store.configure_operator(77, False)
            return original(*args, **kwargs)

        self.store.financial.start_operation = revoked
        with self.assertRaises(PermissionDenied):
            await self.financial.request(
                self.operator, row["id"], "primary-charge", operation
            )
        self.assertEqual(self.provider.calls(), 0)
        self.store.configure_operator(77, True)

        def expired(*args, **kwargs):
            self.store.revoke_session(self.operator)
            return original(*args, **kwargs)

        self.store.financial.start_operation = expired
        with self.assertRaises(PermissionDenied):
            await self.financial.request(
                self.operator, row["id"], "primary-charge", operation
            )
        self.assertEqual(self.provider.calls(), 0)
        self.store.financial.start_operation = original
        fresh = self.store.session(signed(77, timestamp=self.clock[0]))["token"]
        result = await self.financial.request(
            fresh, row["id"], "primary-charge", operation
        )
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(self.provider.calls(), 1)

    async def test_confirmed_ledger_blocks_content_before_projection_and_recovery_finishes_atomically(
        self,
    ):
        row, _ = await self.paid()
        operation = str(uuid.uuid4())
        await self.financial.request(
            self.operator, row["id"], "primary-charge", operation
        )
        original = self.store.complete_financial_ingress

        def fail(identifier):
            if self.store.financial_ingress(identifier)["kind"] == "refunded":
                raise RuntimeError("Synthetic failure after financial commit")
            return original(identifier)

        self.store.complete_financial_ingress = fail
        with self.assertRaisesRegex(RuntimeError, "after financial"):
            await self.financial.reconcile(self.operator, row["id"], operation)
        self.assertEqual(self.store.order(42, row["id"])["status"], "paid")
        with connection(self.database) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_access").fetchone()[0], 1
            )
        with self.assertRaises(PermissionDenied):
            self.store.content(42, "bot-kit")
        with connection(self.database, write=True) as db:
            db.execute("DELETE FROM shop_refund_facts")
        with self.assertRaises(PermissionDenied):
            self.store.content(42, "bot-kit")
        self.assertEqual(
            (await self.financial.status(self.operator, row["id"], operation))["state"],
            "confirmed",
        )
        reopened = self.reopen()
        recovery = ShopRefunds(reopened, self.bot)
        self.assertEqual(await recovery.recover(), 1)
        self.assertEqual(await recovery.recover(), 0)
        self.assertEqual(reopened.order(42, row["id"])["status"], "refunded")
        with self.assertRaises(PermissionDenied):
            reopened.content(42, "bot-kit")
        self.assertEqual(self.provider.calls(), 1)

    async def test_legacy_out_of_band_refund_closes_access_before_ledger_and_late_paid_cannot_reopen(
        self,
    ):
        row = self.row()
        self.store.paid(
            100, 42, self.store.payload(row["id"]), "XTR", 25, "legacy-out-of-band"
        )
        self.store.content(42, "bot-kit")
        original = self.store.financial.apply_event

        def fail_before_ledger(*args, **kwargs):
            raise RuntimeError("Synthetic stop before financial application")

        self.store.financial.apply_event = fail_before_ledger
        with self.assertRaises(RuntimeError):
            await self.financial.refunded(
                self.refunded_message(row, charge="legacy-out-of-band")
            )
        self.assertEqual(self.store.order(42, row["id"])["status"], "paid")
        with self.assertRaises(PermissionDenied):
            self.store.content(42, "bot-kit")
        self.store.financial.apply_event = original
        # An out-of-order original paid event cannot reopen a persisted, trusted full refund.
        await self.financial.paid(
            update(self.store, row, charge="legacy-out-of-band").message.as_(self.bot)
        )
        with self.assertRaises(PermissionDenied):
            self.store.content(42, "bot-kit")
        self.assertEqual(await self.financial.recover(), 1)
        self.assertEqual(self.store.order(42, row["id"])["status"], "refunded")
        late = await self.financial.paid(
            update(self.store, row, charge="late-charge-after-refund").message.as_(
                self.bot
            )
        )
        self.assertTrue(late["review"])
        self.assertEqual(self.store.order(42, row["id"])["status"], "refunded")
        with self.assertRaises(PermissionDenied):
            self.store.content(42, "bot-kit")
        self.assertEqual(self.provider.calls(), 0)

    async def test_legacy_receipt_needs_native_time_and_preserves_old_access_until_verified(
        self,
    ):
        row = self.row()
        self.store.paid(
            100, 42, self.store.payload(row["id"]), "XTR", 25, "legacy-charge"
        )
        operation = str(uuid.uuid4())
        result = await self.financial.request(
            self.operator, row["id"], "legacy-charge", operation
        )
        self.assertEqual(result["state"], "operator-review")
        self.assertEqual(self.provider.calls(), 0)
        self.assertIsNone(self.store.payment_link(row["id"], "legacy-charge"))
        self.store.content(42, "bot-kit")
        native_at = self.clock[0] - 100
        self.provider.paid(
            "legacy-charge", 42, 25, self.store.payload(row["id"]), native_at
        )
        result = await self.financial.request(
            self.operator, row["id"], "legacy-charge", operation
        )
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(self.provider.calls(), 1)
        link = self.store.payment_link(row["id"], "legacy-charge")
        binding = self.store.link_binding(link)
        self.assertEqual(
            self.store.financial.get_charge(binding, "legacy-charge")["paid_at"],
            native_at,
        )
        self.assertEqual(
            (await self.financial.reconcile(self.operator, row["id"], operation))[
                "state"
            ],
            "confirmed",
        )
        with self.assertRaises(PermissionDenied):
            self.store.content(42, "bot-kit")

    async def test_mismatched_or_optional_history_fields_never_confirm_and_never_resend(
        self,
    ):
        row, _ = await self.paid()
        operation = str(uuid.uuid4())
        await self.financial.request(
            self.operator, row["id"], "primary-charge", operation
        )
        actual = self.provider.history()
        outgoing = copy.deepcopy(actual["transactions"][-1])
        self.assertIn("receiver", outgoing)
        variants = []
        for field, value in [
            ("amount", 1),
            ("amount", -25),
            ("nanostar_amount", 1),
            ("date", self.clock[0] + 100),
            ("date", self.clock[0] - 1),
        ]:
            value_row = copy.deepcopy(outgoing)
            value_row[field] = value
            variants.append(value_row)
        for field, value in [
            ("invoice_payload", "other-order"),
            ("user", {"id": 77, "is_bot": False, "first_name": "Other"}),
            ("transaction_type", "paid_media_payment"),
        ]:
            value_row = copy.deepcopy(outgoing)
            value_row["receiver"][field] = value
            variants.append(value_row)
        missing = copy.deepcopy(outgoing)
        del missing["receiver"]["invoice_payload"]
        variants.append(missing)
        both = copy.deepcopy(outgoing)
        both["source"] = copy.deepcopy(both["receiver"])
        variants.append(both)
        variants.append(copy.deepcopy(actual["transactions"][0]))
        for index, candidate in enumerate(variants):
            with self.subTest(case=index):
                self.transport.respond(
                    GetStarTransactions, {"transactions": [candidate]}
                )
                result = await self.financial.reconcile(
                    self.operator, row["id"], operation
                )
                self.assertEqual(result["state"], "unknown")
                self.assertEqual(self.provider.calls(), 1)
                self.store.content(42, "bot-kit")
        self.transport.respond(GetStarTransactions, self.history)
        self.assertEqual(
            (await self.financial.reconcile(self.operator, row["id"], operation))[
                "state"
            ],
            "confirmed",
        )

    async def test_refund_before_payment_and_duplicate_native_events_never_grant(self):
        row = self.row()
        refund = self.refunded_message(row)
        self.assertFalse((await self.financial.refunded(refund))["replayed"])
        with self.assertRaises(PermissionDenied):
            self.store.content(42, "bot-kit")
        await self.financial.paid(
            update(self.store, row, charge="primary-charge").message.as_(self.bot)
        )
        await self.financial.refunded(refund)
        self.assertEqual(self.store.order(42, row["id"])["status"], "refunded")
        with self.assertRaises(PermissionDenied):
            self.store.content(42, "bot-kit")
        for changes in (
            {"total_amount": 1},
            {"invoice_payload": "shop:100:" + str(uuid.uuid4())},
        ):
            with self.assertRaises(PermissionDenied):
                await self.financial.refunded(self.refunded_message(row, **changes))
        with self.assertRaises(ValueError):
            self.refunded_message(row, currency="USD")
        with connection(self.database) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_receipts").fetchone()[0], 1
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_access").fetchone()[0], 0
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_refund_facts").fetchone()[0], 1
            )
        self.assertEqual(self.provider.calls(), 0)

    async def test_refunding_second_review_charge_does_not_remove_primary_entitlement(
        self,
    ):
        row, _ = await self.paid()
        _, second = await self.paid(row, "second-charge")
        self.assertTrue(second["review"])
        self.store.content(42, "bot-kit")
        operation = str(uuid.uuid4())
        await self.financial.request(
            self.operator, row["id"], "second-charge", operation
        )
        self.assertEqual(
            (await self.financial.reconcile(self.operator, row["id"], operation))[
                "state"
            ],
            "confirmed",
        )
        self.store.content(42, "bot-kit")
        self.assertEqual(self.store.order(42, row["id"])["status"], "paid")
        first = self.store.payment_link(row["id"], "primary-charge")
        second = self.store.payment_link(row["id"], "second-charge")
        self.assertNotEqual(first["financial_order"], second["financial_order"])
        self.assertTrue(
            self.store.financial.has_access(
                self.store.link_binding(first), now=self.clock[0]
            ).active
        )
        self.assertFalse(
            self.store.financial.has_access(
                self.store.link_binding(second), now=self.clock[0]
            ).active
        )
        original = str(uuid.uuid4())
        await self.financial.request(
            self.operator, row["id"], "primary-charge", original
        )
        await self.financial.reconcile(self.operator, row["id"], original)
        with self.assertRaises(PermissionDenied):
            self.store.content(42, "bot-kit")
        self.assertEqual(self.provider.calls(), 2)

    async def test_concurrent_same_operation_has_one_external_send_and_no_fresh_budget(
        self,
    ):
        row, _ = await self.paid()
        operation = str(uuid.uuid4())
        entered = asyncio.Event()
        release = asyncio.Event()

        async def held(method):
            accepted = self.refund_effect(method)
            entered.set()
            await release.wait()
            return accepted

        self.transport.respond(RefundStarPayment, held)
        first = asyncio.create_task(
            self.financial.request(
                self.operator, row["id"], "primary-charge", operation
            )
        )
        await asyncio.wait_for(entered.wait(), 5)
        try:
            second = await self.financial.request(
                self.operator, row["id"], "primary-charge", operation
            )
            self.assertEqual(second["state"], "sending")
            self.assertEqual(self.provider.calls(), 1)
            with self.assertRaises(PaymentConflict):
                await self.financial.request(
                    self.operator, row["id"], "primary-charge", str(uuid.uuid4())
                )
        finally:
            release.set()
        self.assertEqual((await first)["state"], "unknown")
        self.assertEqual(self.provider.calls(), 1)

    async def test_durable_paid_ingress_survives_projection_failure_without_premature_access(
        self,
    ):
        row = self.row()

        def fail(identifier):
            raise RuntimeError("Synthetic projection interruption")

        self.store.complete_financial_ingress = fail
        with self.assertRaises(RuntimeError):
            await self.financial.paid(
                update(self.store, row, charge="durable-charge").message.as_(self.bot)
            )
        self.assertEqual(self.store.order(42, row["id"])["status"], "awaiting")
        with self.assertRaises(PermissionDenied):
            self.store.content(42, "bot-kit")
        reopened = self.reopen()
        recovery = ShopRefunds(reopened, self.bot)
        self.assertEqual(await recovery.recover(), 1)
        reopened.content(42, "bot-kit")
        self.assertEqual(await recovery.recover(), 0)
        self.assertEqual(reopened.order(42, row["id"])["status"], "paid")

    async def test_another_current_operator_can_reconcile_without_changing_original_requester(
        self,
    ):
        row, _ = await self.paid()
        operation = str(uuid.uuid4())
        await self.financial.request(
            self.operator, row["id"], "primary-charge", operation
        )
        self.store.configure_operator(88, True)
        other = self.store.session(signed(88, timestamp=self.clock[0]))["token"]
        self.store.configure_operator(77, False)
        self.assertEqual(
            (await self.financial.reconcile(other, row["id"], operation))["state"],
            "confirmed",
        )
        link = self.store.payment_link(row["id"], "primary-charge")
        self.assertEqual(
            self.store.financial.get_operation(
                self.store.link_binding(link), operation
            ).actor_id,
            77,
        )
        with connection(self.database) as db:
            self.assertEqual(
                tuple(
                    db.execute(
                        "SELECT actor_id,action,outcome FROM shop_operator_audit ORDER BY sequence DESC LIMIT 1"
                    ).fetchone()
                ),
                (88, "refund-reconcile", "confirmed"),
            )
        self.assertEqual(self.provider.calls(), 1)

    async def test_additive_v2_migration_keeps_legacy_receipts_sessions_and_explicit_access_policy(
        self,
    ):
        row = self.row()
        self.store.paid(100, 42, self.store.payload(row["id"]), "XTR", 25, "v2-charge")
        # A real old layout has none of the host financial/capability tables. Only this temporary fixture is changed.
        with connection(self.database, write=True) as db:
            for table in (
                "shop_operators",
                "shop_payment_links",
                "shop_payment_ingress",
                "shop_refund_facts",
                "shop_refund_intents",
                "shop_operator_audit",
            ):
                db.execute("DROP TABLE " + table)
            db.execute("UPDATE shop_schema SET version=2")
        migrated = self.reopen()
        self.assertEqual(migrated.authenticate(self.buyer), 42)
        self.assertEqual(migrated.order(42, row["id"])["status"], "paid")
        migrated.content(42, "bot-kit")
        self.assertIsNone(migrated.payment_link(row["id"], "v2-charge"))
        with self.assertRaises(PermissionDenied):
            migrated.operator_identity(self.operator)
        with connection(self.database) as db:
            self.assertEqual(
                db.execute("SELECT version FROM shop_schema").fetchone()[0], 3
            )
            self.assertEqual(
                db.execute("SELECT charge FROM shop_receipts").fetchone()[0],
                "v2-charge",
            )
        migrated.configure_operator(77, True)
        self.assertEqual(migrated.operator_identity(self.operator), 77)

    def intake(self):
        dispatcher = Dispatcher()
        dispatcher.include_router(
            payment_router(
                self.store,
                shop_url="https://fixture.invalid/",
                terms=TERMS,
                support=SUPPORT,
            )
        )
        self.addAsyncCleanup(dispatcher.fsm.close)
        intake = ShopDurablePolling(self.store, self.bot, dispatcher)
        intake.install()
        self.addCleanup(intake.close)
        return intake

    async def test_polling_batch_is_durable_before_offset_and_storage_failure_reuses_same_offset(
        self,
    ):
        row = self.row()
        native = update(self.store, row, charge="queued-payment").model_dump(
            mode="json", exclude_none=True
        )
        first = {**native, "update_id": 800}
        second = {**native, "update_id": 801}
        offsets = []

        def batch(method):
            offsets.append(method.offset)
            return [first, second]

        self.transport.respond(GetUpdates, batch)
        intake = self.intake()
        receive = intake.inbox.receive

        def fail_second(bot_id, update_id, *args, **kwargs):
            if update_id == 801:
                raise sqlite3.OperationalError(
                    "Synthetic admission storage unavailable"
                )
            return receive(bot_id, update_id, *args, **kwargs)

        intake.inbox.receive = fail_second
        with self.assertRaisesRegex(PollingReadFailure, "offset retained") as sanitized:
            await self.bot.get_updates(offset=800, timeout=1)
        self.assertNotIn("admission storage", str(sanitized.exception))
        self.assertEqual(intake.inbox.get(100, 800).state, "pending")
        self.assertIsNone(intake.inbox.get(100, 801))
        self.assertEqual(self.store.order(42, row["id"])["status"], "awaiting")
        intake.inbox.receive = receive
        admitted = await self.bot.get_updates(offset=800, timeout=1)
        self.assertEqual(offsets, [800, 800])
        for item in admitted:
            await intake.dispatcher.feed_update(self.bot, item)
        self.assertEqual(
            self.store.order(42, row["id"])["status"],
            "awaiting",
            "ordinary polling branch must not dispatch a second consumer",
        )
        self.assertEqual(await intake.drain_ready(), 2)
        self.assertEqual(
            intake.inbox.counts(100),
            {"pending": 0, "processing": 0, "done": 2, "quarantined": 0},
        )
        with connection(self.database) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_receipts").fetchone()[0], 1
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_access").fetchone()[0], 1
            )
        self.store.content(42, "bot-kit")

    async def test_actual_sdk_polling_retries_failed_admission_without_advancing_offset(
        self,
    ):
        row = self.row()
        native = update(self.store, row, charge="sdk-loop-charge").model_dump(
            mode="json", exclude_none=True
        )
        native["update_id"] = 950
        intake = self.intake()
        original_receive = intake.inbox.receive
        failure = [True]
        offsets = []
        advanced = asyncio.Event()
        delivered = asyncio.Event()
        blocked = asyncio.Event()

        def receive(*args, **kwargs):
            if failure[0]:
                failure[0] = False
                raise sqlite3.OperationalError("Synthetic durable admission failure")
            return original_receive(*args, **kwargs)

        intake.inbox.receive = receive

        async def fetch(method):
            offsets.append(method.offset)
            if len(offsets) <= 2:
                return [native]
            advanced.set()
            await blocked.wait()
            return []

        original_complete = intake.inbox.complete
        loop = asyncio.get_running_loop()

        def complete(*args, **kwargs):
            value = original_complete(*args, **kwargs)
            loop.call_soon_threadsafe(delivered.set)
            return value

        intake.inbox.complete = complete
        self.transport.respond(GetUpdates, fetch).respond(
            GetMe,
            {
                "id": 100,
                "is_bot": True,
                "first_name": "Fixture",
                "username": "fixture_bot",
            },
        )
        serve = asyncio.create_task(intake.serve(handle_signals=False))
        try:
            await asyncio.wait_for(advanced.wait(), 10)
            await asyncio.wait_for(delivered.wait(), 10)
            self.assertEqual(offsets[:3], [None, None, 951])
            self.assertEqual(intake.inbox.get(100, 950).state, "done")
            self.store.content(42, "bot-kit")
        finally:
            serve.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await serve
        self.assertEqual(len(self.bot.session.middleware), 0)
        self.assertFalse(
            self.transport.closed, "intake must not close its host-owned Bot/session"
        )

    async def test_polling_read_budget_stops_owned_tasks_without_applying_it_to_financial_rpc(
        self,
    ):
        intake = self.intake()
        intake.max_read_failures = 2

        def failed_read(method):
            raise TimeoutError("Synthetic persistent read failure")

        self.transport.respond(GetUpdates, failed_read).respond(
            GetMe,
            {
                "id": 100,
                "is_bot": True,
                "first_name": "Fixture",
                "username": "fixture_bot",
            },
        )
        with self.assertRaisesRegex(RuntimeError, "read retry budget exhausted"):
            await asyncio.wait_for(intake.serve(handle_signals=False), 10)
        self.assertEqual(
            len(
                [call for call in self.transport.calls if isinstance(call, GetUpdates)]
            ),
            2,
        )
        self.assertEqual(len(self.bot.session.middleware), 0)
        self.assertFalse(self.transport.closed)
        # Unknown native writes are tested separately; this read budget never invokes a refund.
        self.assertEqual(self.provider.calls(), 0)

    async def test_unknown_polled_update_is_retained_in_quarantine_and_cleanup_removes_only_owned_hooks(
        self,
    ):
        intake = self.intake()
        before_request = len(self.bot.session.middleware)
        before_dispatch = len(intake.dispatcher.update.outer_middleware)
        intake.install()
        self.assertEqual(len(self.bot.session.middleware), before_request)
        self.transport.respond(
            GetUpdates,
            [{"update_id": 900, "future_financial_fact": {"schema": 2, "amount": 25}}],
        )
        updates = await self.bot.get_updates(offset=900, timeout=1)
        retained = intake.inbox.get(100, 900)
        self.assertEqual(
            (retained.state, retained.reason), ("quarantined", "unknown-update-kind")
        )
        self.assertEqual(
            retained.payload["future_financial_fact"], {"schema": 2, "amount": 25}
        )
        await intake.dispatcher.feed_update(self.bot, updates[0])
        self.assertFalse(await intake.process_one())
        intake.close()
        intake.close()
        self.assertEqual(len(self.bot.session.middleware), before_request - 1)
        self.assertEqual(
            len(intake.dispatcher.update.outer_middleware), before_dispatch - 1
        )

    async def test_admitted_payment_failure_retries_from_durable_claim_without_second_grant(
        self,
    ):
        row = self.row()
        native = update(self.store, row, charge="retained-payment").model_dump(
            mode="json", exclude_none=True
        )
        native["update_id"] = 901
        intake = self.intake()
        self.transport.respond(GetUpdates, [native])
        await self.bot.get_updates(offset=901, timeout=1)
        original = self.store.complete_financial_ingress

        def fail(identifier):
            raise RuntimeError("Synthetic local projection unavailable")

        self.store.complete_financial_ingress = fail
        self.assertTrue(await intake.process_one())
        self.assertEqual(intake.inbox.get(100, 901).state, "pending")
        self.assertEqual(self.store.order(42, row["id"])["status"], "awaiting")
        self.clock[0] += 2
        self.store.complete_financial_ingress = original
        self.assertTrue(await intake.process_one())
        self.assertEqual(intake.inbox.get(100, 901).state, "done")
        self.assertEqual(intake.inbox.get(100, 901).attempts, 2)
        self.store.content(42, "bot-kit")
        with connection(self.database) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_access").fetchone()[0], 1
            )

    async def test_cancelled_worker_joins_owned_sqlite_write_then_retains_claim_for_safe_replay(
        self,
    ):
        row = self.row()
        native = update(self.store, row, charge="cancelled-worker").model_dump(
            mode="json", exclude_none=True
        )
        native["update_id"] = 902
        intake = self.intake()
        self.transport.respond(GetUpdates, [native])
        await self.bot.get_updates(offset=902, timeout=1)
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        original = self.store.complete_financial_ingress

        def held(identifier):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Owned test writer was not released")
            try:
                return original(identifier)
            finally:
                finished.set()

        self.store.complete_financial_ingress = held
        work = asyncio.create_task(intake.process_one())
        self.assertTrue(await asyncio.wait_for(asyncio.to_thread(entered.wait, 3), 4))
        work.cancel()
        await asyncio.sleep(0)
        self.assertFalse(work.done())
        self.assertFalse(finished.is_set())
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await work
        self.assertTrue(finished.is_set())
        self.assertEqual(intake.inbox.get(100, 902).state, "pending")
        self.store.complete_financial_ingress = original
        self.assertTrue(await intake.process_one())
        self.assertEqual(intake.inbox.get(100, 902).state, "done")
        with connection(self.database) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_receipts").fetchone()[0], 1
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_access").fetchone()[0], 1
            )

    async def test_actual_process_crash_before_handler_replays_durable_sdk_batch_after_restart(
        self,
    ):
        async with self.process() as (origin, child, ready, command, _read):
            buyer = (
                await self.call(
                    origin,
                    "POST",
                    "/api/session",
                    body={"initData": ready["launch"]["42"]},
                )
            )["token"]
            row = await self.call(
                origin,
                "POST",
                "/api/orders",
                token=buyer,
                body={
                    "operation": str(uuid.uuid4()),
                    "items": ["bot-kit"],
                    "terms": "demo-v1",
                },
            )
            await self.call(
                origin,
                "POST",
                "/api/orders/" + row["id"] + "/invoice",
                token=buyer,
                body={},
            )
            marker = await command(
                {
                    "action": "poll-admit-crash",
                    "id": row["id"],
                    "charge": "admitted-native-charge",
                }
            )
            self.assertEqual(marker["phase"], "crash-before-handler")
            self.assertTrue(marker["receipt_committed"])
            self.assertEqual(await child.wait(), 87)
        with connection(self.database) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_receipts").fetchone()[0], 0
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_payment_ingress").fetchone()[0], 0
            )
        async with self.process() as (origin, child, ready, command, _read):
            self.assertEqual(ready["inbox_recovered"], 1)
            await self.call(origin, "GET", "/api/content/bot-kit", token=buyer)
            stats = await command({"action": "stats"})
            self.assertEqual(
                (stats["orders"], stats["receipts"], stats["access"]), (1, 1, 1)
            )
            self.assertEqual(stats["refund_requests"], 0)
            self.assertEqual(stats["external_network_attempts"], 0)

    @asynccontextmanager
    async def process(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "telegram_shop_example.offline",
            "--database",
            str(self.database),
            "--frontend",
            str(self.frontend),
            "--port",
            str(port),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def read():
            return json.loads(await asyncio.wait_for(child.stdout.readline(), 30))

        async def command(value):
            child.stdin.write((json.dumps(value) + "\n").encode())
            await child.stdin.drain()
            return await read()

        try:
            ready = await read()
            self.assertEqual(ready["phase"], "ready")
            yield f"http://127.0.0.1:{port}", child, ready, command, read
        finally:
            if child.returncode is None:
                child.stdin.write(b'{"action":"stop"}\n')
                await child.stdin.drain()
                try:
                    _out, err = await asyncio.wait_for(child.communicate(), 10)
                except BaseException:
                    if child.returncode is None:
                        child.kill()
                    await child.wait()
                    raise
                self.assertEqual(child.returncode, 0, err.decode(errors="replace"))

    async def test_actual_process_crashes_preserve_refund_and_block_content_before_projection(
        self,
    ):
        async with self.process() as (origin, child, ready, command, read):
            await command({"action": "operator", "actor": 77, "enabled": True})
            operator = (
                await self.call(
                    origin,
                    "POST",
                    "/api/session",
                    body={"initData": ready["launch"]["77"]},
                )
            )["token"]
            buyer = (
                await self.call(
                    origin,
                    "POST",
                    "/api/session",
                    body={"initData": ready["launch"]["42"]},
                )
            )["token"]
            row = await self.call(
                origin,
                "POST",
                "/api/orders",
                token=buyer,
                body={
                    "operation": str(uuid.uuid4()),
                    "items": ["bot-kit"],
                    "terms": "demo-v1",
                },
            )
            await self.call(
                origin,
                "POST",
                "/api/orders/" + row["id"] + "/invoice",
                token=buyer,
                body={},
            )
            await command(
                {"action": "receipt", "id": row["id"], "charge": "crash-refund-charge"}
            )
            await command({"action": "refund-mode", "mode": "crash"})
            operation = str(uuid.uuid4())
            task = asyncio.create_task(
                self.call(
                    origin,
                    "POST",
                    self.path(row),
                    token=operator,
                    body={"operation": operation, "charge": "crash-refund-charge"},
                )
            )
            marker = await read()
            self.assertEqual(marker["phase"], "crash-refund")
            self.assertTrue(marker["effect_committed"])
            self.assertEqual(marker["refund_calls"], 1)
            self.assertEqual(await child.wait(), 85)
            with self.assertRaises(ClientConnectionError):
                await task
        async with self.process() as (origin, child, ready, command, read):
            await command({"action": "clock-advance", "seconds": 30})
            status = await self.call(
                origin, "GET", self.path(row) + "/" + operation, token=operator
            )
            self.assertEqual(status["state"], "unknown")
            await command({"action": "crash-refund-projection"})
            task = asyncio.create_task(
                self.call(
                    origin,
                    "POST",
                    self.path(row) + "/" + operation + "/reconcile",
                    token=operator,
                    body={},
                )
            )
            marker = await read()
            self.assertEqual(marker["phase"], "crash-refund-projection")
            self.assertTrue(marker["ledger_confirmed"])
            self.assertEqual(marker["refund_calls"], 1)
            self.assertEqual(await child.wait(), 86)
            with self.assertRaises(ClientConnectionError):
                await task
        # New Store has no automatic projection replay: this is the actual ledger/projection gap.
        raw = self.reopen()
        self.assertEqual(raw.order(42, row["id"])["status"], "paid")
        with connection(self.database) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_access").fetchone()[0], 1
            )
        with self.assertRaises(PermissionDenied):
            raw.content(42, "bot-kit")
        async with self.process() as (origin, child, ready, command, read):
            self.assertEqual(ready["financial_recovered"], 1)
            status = await self.call(
                origin, "GET", self.path(row) + "/" + operation, token=operator
            )
            self.assertEqual(status["state"], "confirmed")
            await self.call(
                origin, "GET", "/api/content/bot-kit", token=buyer, status=403
            )
            self.assertEqual((await command({"action": "stats"}))["refund_requests"], 1)
