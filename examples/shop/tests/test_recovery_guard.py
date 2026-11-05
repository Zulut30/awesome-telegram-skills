"""Real prepared-shop HTTP/SDK/worker gates, offline locks and publication crash boundaries."""

from __future__ import annotations

import asyncio
import hashlib
import json
import multiprocessing
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiohttp import ClientSession, ClientTimeout, web
from telegram_patterns import SQLiteOutbox, backup_sqlite
from telegram_shop_example import runtime
from telegram_shop_example.api import create_app
from telegram_shop_example.offline import SUPPORT, TERMS, TOKEN, signed, stub
from telegram_shop_example.payments import payment_router
from telegram_shop_example.polling import ShopDurablePolling
from telegram_shop_example.recovery import (
    RecoveryPrepareError,
    inspect_restored_shop,
    prepare_restored_shop,
)
from telegram_shop_example.recovery_state import RecoveryMaintenance, readiness
from telegram_shop_example.storage import ProcessLock
from telegram_shop_example.store import Store


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def held_owner(path, entered, release):
    owner = ProcessLock(Path(path))
    try:
        entered.set()
        if not release.wait(15):
            raise AssertionError("Parent did not release owned process")
    finally:
        owner.close()


def crash_prepare(arguments, phase):
    from telegram_shop_example import recovery

    if phase == "before-quarantine":

        def stop(*args, **kwargs):
            os._exit(91)

        recovery._quarantine = stop
    else:
        publish = recovery._publish_guarded

        def stop(*args, **kwargs):
            publish(*args, **kwargs)
            os._exit(92)

        recovery._publish_guarded = stop
    recovery.prepare_restored_shop(**arguments)


class RecoveryGuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="shop-recovery-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.assertTrue(self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.live_root, self.snapshots, self.targets = (
            self.root / name for name in ("live", "snapshots", "candidates")
        )
        for folder in (self.live_root, self.snapshots, self.targets):
            folder.mkdir(mode=0o700)
        self.live, self.snapshot, self.candidate = (
            self.live_root / "shop.sqlite",
            self.snapshots / "checkpoint.sqlite",
            self.targets / "restored-new.sqlite",
        )
        self.clock = int(time.time())
        self.store = Store(
            self.live, TOKEN, terms_version="demo-v1", now=lambda: self.clock
        )
        self.store.configure_operator(77, True)
        self.buyer = self.store.session(signed(42, timestamp=self.clock))["token"]
        self.operator = self.store.session(signed(77, timestamp=self.clock))["token"]
        self.order = self.store.create(
            42, "11111111-1111-4111-8111-111111111111", ["bot-kit"], "demo-v1"
        )
        self.store.claim_invoice(42, self.order["id"])
        self.store.finish_invoice(
            42, self.order["id"], "https://t.me/$synthetic-recovery"
        )
        self.store.paid(
            100,
            42,
            self.store.payload(self.order["id"]),
            "XTR",
            self.order["total"],
            "baseline-synthetic-charge",
        )
        self.frontend = self.root / "frontend"
        (self.frontend / "assets").mkdir(parents=True)
        (self.frontend / "index.html").write_text(
            "<html><!-- telegram-sdk --></html>", "utf8"
        )

    def checkpoint(self, *, outbox=False):
        if outbox:
            queue = SQLiteOutbox(self.live)
            queue.initialize()
            for kind in ("pending", "sending", "unknown"):
                with closing(sqlite3.connect(self.live)) as db, db:
                    db.execute("BEGIN IMMEDIATE")
                    queue.enqueue(
                        db,
                        "scope:" + kind,
                        "original:" + kind,
                        {"order": self.order["id"]},
                        now=self.clock,
                    )
                if kind != "pending":
                    claim = queue.claim(
                        "scope:" + kind, "before-checkpoint", now=self.clock
                    )
                    if kind == "unknown":
                        queue.mark_unknown(claim, now=self.clock)
        backup_sqlite(
            self.live,
            self.snapshot,
            source_root=self.live_root,
            destination_root=self.snapshots,
        )
        return self.arguments()

    def arguments(self, **changes):
        result = {
            "live": self.live,
            "snapshot": self.snapshot,
            "candidate": self.candidate,
            "live_root": self.live_root,
            "snapshot_root": self.snapshots,
            "target_root": self.targets,
            "bot_id": 100,
            "expected_snapshot_sha256": sha(self.snapshot),
        }
        result.update(changes)
        return result

    def prepare(self, *, outbox=False):
        return prepare_restored_shop(**self.checkpoint(outbox=outbox))

    async def test_prepare_default_shop_needs_no_optional_outbox_and_preserves_paid_facts(
        self,
    ):
        arguments = self.checkpoint()
        original, checkpoint = sha(self.live), sha(self.snapshot)
        result = prepare_restored_shop(**arguments)
        self.assertFalse(result["ready"])
        self.assertEqual(
            (
                result["revoked_sessions"],
                result["blocked_actors"],
                result["quarantined_outgoing"],
            ),
            (2, 2, 0),
        )
        self.assertTrue(result["cleanup_complete"] and result["old_source_unchanged"])
        self.assertEqual(result["candidate_sha256"], sha(self.candidate))
        self.assertEqual((sha(self.live), sha(self.snapshot)), (original, checkpoint))
        before = sha(self.candidate)
        store = Store(self.candidate, TOKEN, terms_version="demo-v1")
        self.assertEqual(
            sha(self.candidate),
            before,
            "Maintenance Store must not migrate or recover the candidate",
        )
        for action, args in (
            (store.authenticate, (self.buyer,)),
            (store.session, (signed(909),)),
            (store.orders, (42,)),
            (store.content, (42, "bot-kit")),
            (
                store.create,
                (909, "99999999-9999-4999-8999-999999999999", ["ui-guide"], "demo-v1"),
            ),
            (store.configure_role, (42, "customer")),
            (store.configure_operator, (77, True)),
        ):
            with (
                self.subTest(action=action.__name__),
                self.assertRaises(RecoveryMaintenance),
            ):
                action(*args)
        with closing(sqlite3.connect(self.candidate)) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_orders").fetchone()[0],
                1,
                "Recovery rejection must precede core SQLiteOnce business commit",
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM telegram_pattern_operations"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                db.execute("SELECT count(*) FROM shop_sessions").fetchone()[0], 0
            )
            self.assertEqual(
                db.execute("SELECT role FROM shop_roles ORDER BY actor_id").fetchall(),
                [("blocked",), ("blocked",)],
            )
            self.assertEqual(
                db.execute("SELECT enabled FROM shop_operators").fetchall(), [(0,)]
            )
            self.assertEqual(
                db.execute("SELECT charge FROM shop_receipts").fetchall(),
                [("baseline-synthetic-charge",)],
            )
            self.assertEqual(
                db.execute("SELECT status,operation FROM shop_orders").fetchall(),
                [("paid", "11111111-1111-4111-8111-111111111111")],
            )
        self.assertFalse(
            inspect_restored_shop(self.candidate, target_root=self.targets)["ready"]
        )

    async def test_post_checkpoint_effect_does_not_make_restored_pending_safely_retryable(
        self,
    ):
        arguments = self.checkpoint(outbox=True)
        queue = SQLiteOutbox(self.live)
        sent = queue.claim("scope:pending", "old-sender", now=self.clock)
        external = self.root / "independent-fake-service.sqlite"
        with closing(sqlite3.connect(external)) as db, db:
            db.execute("CREATE TABLE effects(operation_key TEXT)")
            db.execute("INSERT INTO effects VALUES (?)", (sent.operation_key,))
        queue.confirm(sent, {"message_id": 1}, now=self.clock)
        self.store.revoke_session(self.buyer)
        result = prepare_restored_shop(**arguments)
        self.assertEqual(result["quarantined_outgoing"], 2)
        restored = SQLiteOutbox(self.candidate)
        expected = {"pending": (1, 0), "sending": (2, 1), "unknown": (2, 1)}
        for kind, (revision, attempts) in expected.items():
            record = restored.get("scope:" + kind, "original:" + kind)
            self.assertEqual(
                (record.state, record.revision, record.attempts),
                ("unknown", revision, attempts),
            )
            self.assertEqual(record.payload, {"order": self.order["id"]})
            self.assertIsNone(
                restored.claim(
                    "scope:" + kind, "restored-worker", now=self.clock + 10000
                )
            )
        with closing(sqlite3.connect(self.candidate)) as db:
            self.assertEqual(
                db.execute(
                    "SELECT operation_key,before_state,before_revision,after_revision,attempts FROM shop_recovery_outgoing ORDER BY operation_key"
                ).fetchall(),
                [
                    ("original:pending", "pending", 0, 1, 0),
                    ("original:sending", "sending", 1, 2, 1),
                ],
            )
        with closing(sqlite3.connect(external)) as db:
            self.assertEqual(
                db.execute("SELECT operation_key FROM effects").fetchall(),
                [("original:pending",)],
            )

    async def test_real_http_and_sdk_requests_stay_closed_for_old_and_new_actors(self):
        self.prepare(outbox=True)
        store = Store(self.candidate, TOKEN, terms_version="demo-v1")
        transport = stub()
        bot = Bot(TOKEN, session=transport)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        sock.setblocking(False)
        origin = "http://127.0.0.1:" + str(sock.getsockname()[1])
        app = create_app(
            store,
            bot,
            self.frontend,
            origin=origin,
            terms=TERMS,
            support=SUPPORT,
            loopback_dev=True,
        )
        runner = web.AppRunner(app, access_log=None, shutdown_timeout=1)
        try:
            await runner.setup()
            await web.SockSite(runner, sock).start()
            async with ClientSession(timeout=ClientTimeout(total=3)) as client:
                async with client.get(origin + "/api/readiness") as response:
                    self.assertEqual(response.status, 503)
                    self.assertEqual(
                        await response.json(),
                        {
                            "ready": False,
                            "mode": "recovery-maintenance",
                            "reason": "operator-reconciliation-required",
                        },
                    )
                requests = [
                    ("GET", "/api/orders", None),
                    ("GET", "/api/content/bot-kit", None),
                    ("POST", "/api/session", {"initData": signed(909)}),
                    (
                        "POST",
                        "/api/orders",
                        {
                            "operation": "22222222-2222-4222-8222-222222222222",
                            "items": ["ui-guide"],
                            "terms": "demo-v1",
                        },
                    ),
                    (
                        "POST",
                        "/api/operator/orders/" + self.order["id"] + "/refunds",
                        {
                            "operation": "33333333-3333-4333-8333-333333333333",
                            "charge": "baseline-synthetic-charge",
                        },
                    ),
                ]
                for method, path, body in requests:
                    async with client.request(
                        method,
                        origin + path,
                        json=body,
                        headers={
                            "Origin": origin,
                            "Authorization": "Bearer " + self.buyer,
                        },
                    ) as response:
                        self.assertEqual(response.status, 503)
                        self.assertEqual(
                            await response.json(), {"error": "recovery-maintenance"}
                        )
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
            for action in (bot.get_me(), bot.send_message(42, "must not send")):
                with self.assertRaises(RecoveryMaintenance):
                    await action
            self.assertEqual(transport.calls, [])
            dispatcher = Dispatcher()
            try:
                with self.assertRaises(RecoveryMaintenance):
                    ShopDurablePolling(store, bot, dispatcher)
            finally:
                await dispatcher.fsm.close()
        finally:
            await runner.cleanup()
            sock.close()
            await bot.session.close()
        self.assertEqual(
            len(bot.session.middleware),
            0,
            "App cleanup removes only its own transport guard",
        )
        bare_transport = stub()
        bare_bot = Bot(TOKEN, session=bare_transport)
        dispatcher = Dispatcher()
        dispatcher.include_router(
            payment_router(
                store, shop_url="https://fixture.invalid/", terms=TERMS, support=SUPPORT
            )
        )
        try:
            message = Update.model_validate(
                {
                    "update_id": 1001,
                    "message": {
                        "message_id": 1,
                        "date": self.clock,
                        "chat": {"id": 42, "type": "private"},
                        "from": {"id": 42, "is_bot": False, "first_name": "Fixture"},
                        "text": "/start",
                        "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
                    },
                },
                context={"bot": bare_bot},
            )
            with self.assertRaises(RecoveryMaintenance):
                await dispatcher.feed_update(bare_bot, message)
            self.assertEqual(bare_transport.calls, [])
        finally:
            await dispatcher.fsm.close()
            await bare_bot.session.close()

    async def test_runtime_maintenance_opens_readiness_without_recover_polling_or_sdk(
        self,
    ):
        self.prepare()
        transport = stub()
        bot = Bot(TOKEN, session=transport)
        entered, release = asyncio.Event(), asyncio.Event()

        async def wait():
            entered.set()
            await release.wait()

        reserve = socket.socket()
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
        reserve.close()
        terms = self.root / "terms.txt"
        terms.write_text(TERMS, "utf8")
        args = SimpleNamespace(
            database=self.candidate,
            terms=terms,
            terms_version="demo-v1",
            frontend=self.frontend,
            origin="https://fixture.invalid",
            support=SUPPORT,
            port=port,
        )
        with (
            patch.object(
                runtime.BotSettings,
                "from_env",
                return_value=SimpleNamespace(token=TOKEN),
            ),
            patch.object(runtime, "create_bot", return_value=bot),
            patch.object(runtime, "maintenance_wait", wait),
            patch.object(
                runtime.ShopRefunds,
                "recover",
                new=AsyncMock(
                    side_effect=AssertionError("No recovery during maintenance")
                ),
            ),
            patch.object(
                runtime,
                "payment_router",
                side_effect=AssertionError("No live router during maintenance"),
            ),
            patch.object(
                runtime,
                "ShopDurablePolling",
                side_effect=AssertionError("No poller during maintenance"),
            ),
        ):
            task = asyncio.create_task(runtime.live(args))
            try:
                await asyncio.wait_for(entered.wait(), 5)
                with self.assertRaises(RuntimeError):
                    ProcessLock(self.candidate)
                async with (
                    ClientSession(timeout=ClientTimeout(total=3)) as client,
                    client.get(f"http://127.0.0.1:{port}/api/readiness") as response,
                ):
                    self.assertEqual(response.status, 503)
                    self.assertFalse((await response.json())["ready"])
            finally:
                release.set()
                await asyncio.wait_for(task, 5)
        self.assertEqual(transport.calls, [])
        owner = ProcessLock(self.candidate)
        owner.close()

    async def test_actual_old_or_candidate_owner_refuses_before_restoration(self):
        arguments = self.checkpoint()
        context = multiprocessing.get_context("spawn")
        for path, code in (
            (self.live, "old-writer-active"),
            (self.candidate, "candidate-writer-active"),
        ):
            entered, release = context.Event(), context.Event()
            child = context.Process(
                target=held_owner, args=(str(path), entered, release)
            )
            child.start()
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 10))
                with self.assertRaises(RecoveryPrepareError) as error:
                    prepare_restored_shop(**arguments)
                self.assertEqual(error.exception.code, code)
                self.assertFalse(self.candidate.exists())
                self.assertEqual(list(self.targets.glob(".shop-recovery-*")), [])
            finally:
                release.set()
                await asyncio.to_thread(child.join, 5)
                if child.is_alive():
                    child.terminate()
                    child.join(5)
            self.assertEqual(child.exitcode, 0)

    async def test_process_crashes_leave_final_absent_or_already_guarded(self):
        self.checkpoint()
        old, snapshot = sha(self.live), sha(self.snapshot)
        for phase, code in [("before-quarantine", 91), ("after-publication", 92)]:
            path = self.targets / (phase + ".sqlite")
            child = multiprocessing.get_context("spawn").Process(
                target=crash_prepare, args=(self.arguments(candidate=path), phase)
            )
            child.start()
            await asyncio.to_thread(child.join, 15)
            if child.is_alive():
                child.terminate()
                child.join(5)
            self.assertEqual(child.exitcode, code)
            if phase == "before-quarantine":
                self.assertFalse(
                    path.exists(),
                    "Unmarked restored sessions must stay private, never at final path",
                )
                self.assertTrue(
                    list(self.targets.glob(".shop-recovery-*/prepared.sqlite"))
                )
            else:
                self.assertTrue(path.exists())
                self.assertFalse(readiness(path)["ready"])
                reopened = Store(path, TOKEN, terms_version="demo-v1")
                with self.assertRaises(RecoveryMaintenance):
                    reopened.session(signed(909))
                with closing(sqlite3.connect(path)) as db:
                    self.assertEqual(
                        db.execute("SELECT count(*) FROM shop_sessions").fetchone()[0],
                        0,
                    )
            lock = ProcessLock(path)
            lock.close()
        self.assertEqual((sha(self.live), sha(self.snapshot)), (old, snapshot))

    async def test_bad_digest_existing_target_wrong_context_and_unknown_marker_fail_closed(
        self,
    ):
        arguments = self.checkpoint()
        before = sha(self.live), sha(self.snapshot)
        with self.assertRaises(RecoveryPrepareError) as error:
            prepare_restored_shop(**self.arguments(expected_snapshot_sha256="0" * 64))
        self.assertEqual(error.exception.code, "checkpoint-digest-mismatch")
        with self.assertRaises(RecoveryPrepareError) as error:
            prepare_restored_shop(**self.arguments(bot_id=101))
        self.assertEqual(error.exception.code, "wrong-host-context")
        self.candidate.write_bytes(b"CALLER-OWNED")
        with self.assertRaises(RecoveryPrepareError) as error:
            prepare_restored_shop(**arguments)
        self.assertEqual(error.exception.code, "candidate-exists")
        self.assertEqual(self.candidate.read_bytes(), b"CALLER-OWNED")
        self.assertEqual((sha(self.live), sha(self.snapshot)), before)
        malformed = self.targets / "malformed-marker.sqlite"
        with closing(sqlite3.connect(malformed)) as db, db:
            db.execute("CREATE TABLE shop_recovery_meta(unrecognized TEXT)")
        self.assertFalse(readiness(malformed)["ready"])
        self.assertFalse(
            inspect_restored_shop(malformed, target_root=self.targets)["ready"]
        )

    async def test_operator_cli_prepare_inspect_and_no_activation_or_secret_echo(self):
        arguments = self.checkpoint()
        command = [sys.executable, "-I", "-m", "telegram_shop_example.recovery"]
        values = [
            "prepare",
            "--live",
            str(self.live),
            "--snapshot",
            str(self.snapshot),
            "--candidate",
            str(self.candidate),
            "--live-root",
            str(self.live_root),
            "--snapshot-root",
            str(self.snapshots),
            "--target-root",
            str(self.targets),
            "--bot-id",
            "100",
            "--expected-snapshot-sha256",
            arguments["expected_snapshot_sha256"],
        ]
        result = await asyncio.to_thread(
            subprocess.run,
            [*command, *values],
            capture_output=True,
            text=True,
            encoding="utf8",
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["ready"])
        inspected = await asyncio.to_thread(
            subprocess.run,
            [
                *command,
                "inspect",
                "--candidate",
                str(self.candidate),
                "--target-root",
                str(self.targets),
            ],
            capture_output=True,
            text=True,
            encoding="utf8",
            timeout=10,
        )
        self.assertEqual(inspected.returncode, 3)
        self.assertTrue(json.loads(inspected.stdout)["prepared"])
        for args in [
            ["activate", "--PRIVATE-SECRET"],
            ["prepare", "--bot-id", "PRIVATE-SECRET"],
        ]:
            rejected = await asyncio.to_thread(
                subprocess.run,
                [*command, *args],
                capture_output=True,
                text=True,
                encoding="utf8",
                timeout=10,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertNotIn("PRIVATE-SECRET", rejected.stdout + rejected.stderr)
            self.assertEqual(json.loads(rejected.stderr)["code"], "invalid-arguments")


if __name__ == "__main__":
    unittest.main()
