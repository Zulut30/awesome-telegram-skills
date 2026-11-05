"""Actual aiogram polling and file SQLite; no bot token or payment cabinet needed."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from aiogram import Bot, Dispatcher, Router
from aiogram.methods import AnswerPreCheckoutQuery, GetMe, GetUpdates
from aiogram.types import Update
from telegram_patterns import PermissionDenied
from telegram_shop_example.offline import SUPPORT, TERMS, TOKEN, stub
from telegram_shop_example.payments import payment_router
from telegram_shop_example.polling import PollingReadFailure, ShopDurablePolling
from telegram_shop_example.storage import connection
from telegram_shop_example.store import Store


class PrecheckoutTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shop-precheckout-")
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "shop.sqlite"
        self.store = Store(self.database, TOKEN, terms_version="demo-v1")
        self.transport = stub()
        self.bot = Bot(TOKEN, session=self.transport)
        self.addAsyncCleanup(self.transport.close)

    def query(self, update_id, *, query_id=None):
        row = self.store.create(42, str(uuid.uuid4()), ["bot-kit"], "demo-v1")
        self.store.claim_invoice(42, row["id"])
        native = {
            "update_id": update_id,
            "pre_checkout_query": {
                "id": query_id or f"query-{update_id}",
                "from": {"id": 42, "is_bot": False, "first_name": "Fixture"},
                "currency": "XTR",
                "total_amount": row["total"],
                "invoice_payload": self.store.payload(row["id"]),
            },
        }
        return native, row

    def intake(self, *, router=None, budget=8, capacity=4):
        dispatcher = Dispatcher()
        if router:
            dispatcher.include_router(router)
        dispatcher.include_router(
            payment_router(
                self.store,
                shop_url="https://fixture.invalid/",
                terms=TERMS,
                support=SUPPORT,
            )
        )
        self.addAsyncCleanup(dispatcher.fsm.close)
        result = ShopDurablePolling(
            self.store,
            self.bot,
            dispatcher,
            precheckout_budget=budget,
            precheckout_capacity=capacity,
        )
        result.install()
        self.addCleanup(result.close)
        return result

    def positives(self):
        return [
            call
            for call in self.transport.calls
            if isinstance(call, AnswerPreCheckoutQuery) and call.ok
        ]

    async def test_actual_sdk_polling_precheckout_answers_before_blocked_ordinary_handler_is_released(
        self,
    ):
        entered, release, answered, stop_fetch = (asyncio.Event() for _ in range(4))
        router = Router()

        @router.message()
        async def ordinary(message):
            entered.set()
            await release.wait()

        intake = self.intake(router=router, budget=2)
        native, row = self.query(1201)
        ordinary_update = {
            "update_id": 1200,
            "message": {
                "message_id": 1,
                "date": int(time.time()),
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42, "is_bot": False, "first_name": "Fixture"},
                "text": "blocked",
            },
        }
        offsets, answered_at = [], []

        async def fetch(method):
            offsets.append(method.offset)
            if len(offsets) == 1:
                return [ordinary_update]
            if len(offsets) == 2:
                await entered.wait()
                return [native]
            await stop_fetch.wait()
            return []

        def answer(method):
            self.assertFalse(release.is_set())
            self.assertTrue(method.ok)
            answered_at.append(time.time())
            answered.set()
            return True

        self.transport.respond(GetUpdates, fetch).respond(
            AnswerPreCheckoutQuery, answer
        ).respond(
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
            await asyncio.wait_for(answered.wait(), 5)
            record = intake.inbox.get(100, 1201)
            self.assertLessEqual(answered_at[0] - record.received_at, 2)
            self.assertFalse(
                release.is_set(),
                "Native answer must precede releasing the ordinary handler",
            )
            self.assertEqual(offsets[:3], [None, 1201, 1202])
            self.assertEqual(self.store.order(42, row["id"])["status"], "awaiting")
            with self.assertRaises(PermissionDenied):
                self.store.content(42, "bot-kit")
        finally:
            release.set()
            serve.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await serve
        self.assertEqual(len(self.positives()), 1)
        self.assertEqual(len(self.bot.session.middleware), 0)
        self.assertFalse(self.transport.closed)
        names = {task.get_name() for task in asyncio.all_tasks() if not task.done()}
        self.assertNotIn("shop-precheckout-worker", names)
        self.assertNotIn("shop-durable-worker", names)

    async def test_expired_real_admission_never_sends_positive_after_backlog_or_restart(
        self,
    ):
        intake = self.intake(budget=0.1)
        native, _ = self.query(1210)
        self.transport.respond(GetUpdates, [native])
        await self.bot.get_updates(offset=1210)
        first = intake.inbox.get(100, 1210).received_at
        await asyncio.sleep(0.15)
        self.assertTrue(await intake.process_one(critical=True))
        self.assertEqual(intake.precheckout.get("query-1210")["state"], "expired")
        self.assertEqual(intake.inbox.get(100, 1210).state, "quarantined")
        intake.close()
        restarted = self.intake(budget=0.1)
        await self.bot.get_updates(offset=1210)
        await restarted.drain_ready()
        self.assertEqual(restarted.inbox.get(100, 1210).received_at, first)
        self.assertEqual(self.positives(), [])

    async def test_failed_batch_cannot_be_ready_or_approve_and_retry_retains_first_admission(
        self,
    ):
        intake = self.intake()
        native, _ = self.query(1220)
        other = {"update_id": 1221, "future_fact": {"schema": 1}}
        offsets = []

        def fetch(method):
            offsets.append(method.offset)
            return [native, other]

        self.transport.respond(GetUpdates, fetch)
        original = intake.inbox.receive

        def fail_second(bot_id, update_id, *args, **kwargs):
            if update_id == 1221:
                raise sqlite3.OperationalError("Unavailable batch storage")
            return original(bot_id, update_id, *args, **kwargs)

        intake.inbox.receive = fail_second
        with self.assertRaises(PollingReadFailure):
            await self.bot.get_updates(offset=1220)
        retained = intake.inbox.get(100, 1220)
        self.assertEqual(intake.precheckout.get("query-1220")["state"], "pending")
        await intake.process_one(critical=True)
        intake.inbox.receive = original
        await self.bot.get_updates(offset=1220)
        await intake.drain_ready()
        self.assertEqual(offsets, [1220, 1220])
        self.assertEqual(intake.inbox.get(100, 1220).received_at, retained.received_at)
        self.assertEqual(intake.precheckout.get("query-1220")["state"], "refused")
        self.assertEqual(self.positives(), [])

    async def test_capacity_overflow_is_durable_quarantine_without_late_positive(self):
        intake = self.intake(capacity=1)
        first, _ = self.query(1230)
        second, _ = self.query(1231)
        self.transport.respond(GetUpdates, [first, second])
        await self.bot.get_updates(offset=1230)
        self.assertEqual(intake.precheckout.get("query-1231")["outcome"], "capacity")
        self.assertEqual(intake.inbox.get(100, 1231).state, "quarantined")
        await intake.drain_ready()
        self.assertEqual(
            [call.pre_checkout_query_id for call in self.positives()], ["query-1230"]
        )
        with connection(self.database) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_access").fetchone()[0], 0
            )

    async def test_lost_positive_answer_is_unknown_and_replay_restart_never_resends_true(
        self,
    ):
        intake = self.intake()
        native, row = self.query(1240)

        def lost_answer(method):
            self.assertTrue(method.ok)
            raise TimeoutError("Native accepted the answer; reply was lost")

        self.transport.respond(GetUpdates, [native]).respond(
            AnswerPreCheckoutQuery, lost_answer
        )
        await self.bot.get_updates(offset=1240)
        await intake.process_one(critical=True)
        self.assertEqual(intake.precheckout.get("query-1240")["state"], "unknown")
        self.assertEqual(intake.precheckout.get("query-1240")["positive"], 1)
        self.assertEqual(intake.inbox.get(100, 1240).state, "quarantined")
        intake.close()
        self.store = Store(self.database, TOKEN, terms_version="demo-v1")
        restarted = self.intake()
        # Both the original delivery and another delivery with the same native query ID are harmless.
        self.transport.respond(GetUpdates, [native, dict(native, update_id=1241)])
        await self.bot.get_updates(offset=1240)
        await restarted.drain_ready()
        self.assertEqual(len(self.positives()), 1)
        self.assertEqual(restarted.precheckout.get("query-1240")["state"], "unknown")
        self.assertEqual(self.store.order(42, row["id"])["status"], "awaiting")
        with self.assertRaises(PermissionDenied):
            self.store.content(42, "bot-kit")

    async def test_legacy_zero_lane_query_is_never_promoted_or_given_fresh_deadline(
        self,
    ):
        intake = self.intake()
        native, _ = self.query(1250)
        original = time.time()
        intake.inbox.receive(
            100,
            1250,
            Update.model_validate(native).model_dump(mode="json", exclude_none=True),
            now=original,
        )
        self.transport.respond(GetUpdates, [native])
        await self.bot.get_updates(offset=1250)
        retained = intake.inbox.get(100, 1250)
        self.assertEqual((retained.priority, retained.received_at), (0, original))
        await intake.drain_ready()
        self.assertEqual(intake.inbox.get(100, 1250).state, "quarantined")
        self.assertEqual(self.positives(), [])
        missing, _ = self.query(1251)
        intake.inbox.receive(
            100,
            1251,
            Update.model_validate(missing).model_dump(mode="json", exclude_none=True),
            priority=1,
            now=time.time(),
        )
        self.transport.respond(GetUpdates, [missing])
        await self.bot.get_updates(offset=1251)
        await intake.drain_ready()
        self.assertEqual(
            intake.precheckout.get("query-1251")["outcome"], "uncertain-admission"
        )
        self.assertEqual(intake.inbox.get(100, 1251).state, "quarantined")
        self.assertEqual(self.positives(), [])

    async def crash_child(self, native, phase):
        counter = Path(self.temp.name) / "external-answer-count"
        code = """
import asyncio,json,os,sys
from pathlib import Path
from aiogram import Bot,Dispatcher
from aiogram.methods import AnswerPreCheckoutQuery,GetUpdates
from telegram_shop_example.offline import TOKEN,TERMS,SUPPORT,stub
from telegram_shop_example.store import Store
from telegram_shop_example.payments import payment_router
from telegram_shop_example.polling import ShopDurablePolling
async def run():
    store=Store(Path(sys.argv[1]),TOKEN,terms_version='demo-v1')
    session=stub();bot=Bot(TOKEN,session=session);dispatcher=Dispatcher()
    dispatcher.include_router(payment_router(store,shop_url='https://fixture.invalid/',terms=TERMS,support=SUPPORT))
    intake=ShopDurablePolling(store,bot,dispatcher);intake.install()
    session.respond(GetUpdates,[json.loads(sys.argv[2])])
    if sys.argv[3]=='before-storage':
        def crash(*args):os._exit(88)
        intake.precheckout.observe=crash
    else:
        def answer(method):
            assert method.ok is True
            with open(sys.argv[4],'w') as stream:
                stream.write('1');stream.flush();os.fsync(stream.fileno())
            os._exit(89)
        session.respond(AnswerPreCheckoutQuery,answer)
    await bot.get_updates(offset=json.loads(sys.argv[2])['update_id'])
    await intake.process_one(critical=True)
    raise RuntimeError('Crash hook was not reached')
asyncio.run(run())
"""
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            str(self.database),
            json.dumps(native),
            phase,
            str(counter),
            env={
                **os.environ,
                "PYTHONPATH": str(Path(inspect.getfile(Store)).parents[1]),
                "PYTHONIOENCODING": "utf-8",
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), 12)
        self.assertEqual(
            process.returncode,
            88 if phase == "before-storage" else 89,
            (stdout, stderr),
        )
        return counter

    async def test_actual_process_crash_before_storage_refuses_unknown_first_admission(
        self,
    ):
        native, _ = self.query(1260)
        await self.crash_child(native, "before-storage")
        restarted = self.intake()
        advanced, hold = asyncio.Event(), asyncio.Event()
        offsets = []
        ordinary = {
            "update_id": 1259,
            "message": {
                "message_id": 2,
                "date": int(time.time()),
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42, "is_bot": False, "first_name": "Fixture"},
                "text": "/terms",
            },
        }

        async def fetch(method):
            offsets.append(method.offset)
            if len(offsets) == 1:
                return []
            if len(offsets) == 2:
                return [ordinary]
            if len(offsets) == 3:
                return [native]
            advanced.set()
            await hold.wait()
            return []

        self.transport.respond(GetUpdates, fetch).respond(
            GetMe,
            {
                "id": 100,
                "is_bot": True,
                "first_name": "Fixture",
                "username": "fixture_bot",
            },
        )
        serve = asyncio.create_task(restarted.serve(handle_signals=False))
        try:
            await asyncio.wait_for(advanced.wait(), 5)
            self.assertEqual(offsets[:4], [None, None, 1260, 1261])
            self.assertEqual(restarted.inbox.get(100, 1260).state, "quarantined")
        finally:
            serve.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await serve
        self.assertEqual(
            restarted.precheckout.get("query-1260")["outcome"], "uncertain-admission"
        )
        self.assertEqual(self.positives(), [])

    async def test_actual_process_crash_after_positive_rpc_never_resends_on_restart(
        self,
    ):
        native, row = self.query(1270)
        counter = await self.crash_child(native, "after-native-answer")
        restarted = self.intake()
        self.assertEqual(restarted.precheckout.get("query-1270")["state"], "unknown")
        self.assertEqual(counter.read_text(), "1")
        self.transport.respond(GetUpdates, [dict(native, update_id=1271)])
        await self.bot.get_updates(offset=1270)
        await restarted.drain_ready()
        self.assertEqual(counter.read_text(), "1")
        self.assertEqual(self.positives(), [])
        self.assertEqual(self.store.order(42, row["id"])["status"], "awaiting")
        with self.assertRaises(PermissionDenied):
            self.store.content(42, "bot-kit")
