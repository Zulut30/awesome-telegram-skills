"""Durable Bot API polling admission using public aiogram middleware and SQLiteInbox.

A fetched batch is committed before the SDK returns it to aiogram's offset loop.
Ordinary polling dispatch only acknowledges admission. Two finite workers keep
pre-checkout separate from ordinary handlers. No MTProto or write retry layer.
"""

from __future__ import annotations

import asyncio
import time

from aiogram import Bot, Dispatcher
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.methods import GetUpdates
from aiogram.types import Update
from telegram_patterns import InboxLeaseLost, SQLiteInbox

from .precheckout import PrecheckoutAdmissions
from .storage import io_call
from .store import Store
from .recovery_state import RecoveryMaintenance


class PollingReadFailure(RuntimeError):
    """Sanitized read/admission failure; SDK polling logs must not print raw update decoding data."""


class ShopDurablePolling:
    def __init__(
        self,
        store: Store,
        bot: Bot,
        dispatcher: Dispatcher,
        *,
        max_read_failures: int = 10,
        read_timeout_seconds: int = 25,
        precheckout_budget: float = 8,
        precheckout_capacity: int = 4,
    ):
        if bot.id != store.bot_id:
            raise ValueError("Polling bot and store must match")
        if (
            type(max_read_failures) is not int
            or not 1 <= max_read_failures <= 100
            or type(read_timeout_seconds) is not int
            or not 1 <= read_timeout_seconds <= 120
        ):
            raise ValueError("Use a finite polling read budget and timeout")
        self.max_read_failures, self.read_timeout_seconds = (
            max_read_failures,
            read_timeout_seconds,
        )
        self._read_failures = 0
        self._read_failed = asyncio.Event()
        self.store, self.bot, self.dispatcher = store, bot, dispatcher
        store.require_operational()
        self.inbox = SQLiteInbox(store.database, timeout=1, max_attempts=5)
        self.inbox.initialize()
        self.precheckout = PrecheckoutAdmissions(
            store, budget=precheckout_budget, capacity=precheckout_capacity
        )
        self.clock = time.time
        self._admission = asyncio.Lock()
        self._first_seen: dict[int, float] = {}
        self._uncertain = False
        self._restart_uncertain = False
        self.kinds = frozenset(dispatcher.resolve_used_update_types())
        self._claim_token = object()
        self._installed = False

    async def _request(self, make_request, bot, method):
        await io_call(self.store.require_operational)
        if not isinstance(method, GetUpdates):
            return await make_request(
                bot, method
            )  # exactly one invocation; financial RPCs never inherit read retries
        fetched = False
        try:
            async with asyncio.timeout(self.read_timeout_seconds):
                result = await make_request(bot, method)
            fetched = True
            if bot.id != self.bot.id:
                raise ValueError("Do not mix polling bot identities")
            observed = self.clock()
            if len(result) > 100:
                raise ValueError("GetUpdates batch exceeds bounded admission")
            async with self._admission:
                entries = []
                for update in result:
                    if update.pre_checkout_query is not None:
                        if (
                            update.update_id not in self._first_seen
                            and len(self._first_seen) < 100
                        ):
                            self._first_seen[update.update_id] = observed
                        retained = await io_call(
                            self.inbox.get, self.bot.id, update.update_id
                        )
                        first = (
                            retained.received_at
                            if retained
                            else self._first_seen.get(update.update_id, observed)
                        )
                        uncertain = (
                            self._uncertain
                            or self._restart_uncertain
                            or update.update_id not in self._first_seen
                        )
                        if retained:
                            prior_meta = await io_call(
                                self.precheckout.get, update.pre_checkout_query.id
                            )
                            if retained.priority != 1 or prior_meta is None:
                                uncertain = True
                        entries.append(
                            (
                                update.update_id,
                                update.pre_checkout_query,
                                first,
                                uncertain,
                            )
                        )
                await io_call(self.precheckout.observe, entries, observed)
                # All receipts commit BEFORE ready metadata, SDK return and offset advancement.
                for update in result:
                    payload = update.model_dump(mode="json", exclude_none=True)
                    known = len(set(payload) - {"update_id"}) == 1 and bool(
                        (set(payload) - {"update_id"}) & self.kinds
                    )
                    critical = update.pre_checkout_query is not None
                    meta = (
                        await io_call(
                            self.precheckout.get, update.pre_checkout_query.id
                        )
                        if critical
                        else None
                    )
                    refused = meta is not None and meta["state"] == "refused"
                    await io_call(
                        self.inbox.receive,
                        self.bot.id,
                        update.update_id,
                        payload,
                        priority=1 if critical else 0,
                        quarantine_reason="manual-review"
                        if refused
                        else None
                        if known
                        else "unknown-update-kind",
                        now=self._first_seen.get(update.update_id, observed)
                        if critical
                        else self.store.now(),
                    )
                await io_call(
                    self.precheckout.finish_batch,
                    [update.update_id for update in result],
                )
                for update in result:
                    self._first_seen.pop(update.update_id, None)
                if entries:
                    # Empty/ordinary batches prove nothing about the first-seen time
                    # of a query lost before metadata storage in an earlier owner.
                    self._restart_uncertain = False
                    self._uncertain = bool(self._first_seen)
        except asyncio.CancelledError:
            if fetched:
                self._uncertain = True
            raise
        except Exception:  # noqa: BLE001 -- prevent SDK decode payloads from reaching its polling logger
            self._uncertain = True
            self._read_failures += 1
            if self._read_failures >= self.max_read_failures:
                self._read_failed.set()
            raise PollingReadFailure(
                "Polling read or durable admission failed; offset retained"
            ) from None
        else:
            self._read_failures = 0
            return result

    async def _queue_only(self, handler, event, data):
        if data.get("shop_durable_claim") is self._claim_token:
            return await handler(event, data)
        return None  # aiogram may now advance its offset: the batch was already durably admitted.

    def install(self) -> None:
        if self._installed:
            return
        self.store.require_operational()
        self._restart_uncertain = self.precheckout.open_owner()
        self.bot.session.middleware.register(self._request)
        self.dispatcher.update.outer_middleware.register(self._queue_only)
        self._installed = True

    def close(self) -> None:
        if not self._installed:
            return
        self.bot.session.middleware.unregister(self._request)
        self.dispatcher.update.outer_middleware.unregister(self._queue_only)
        self._installed = False
        if not self._uncertain and not self._restart_uncertain:
            try:
                self.precheckout.close_owner()
            except RecoveryMaintenance:
                pass  # Cleanup never reopens a recovery gate or rewrites its restored owner state.

    async def process_one(self, *, critical: bool = False) -> bool:
        await io_call(self.store.require_operational)
        async with self._admission:
            claim = await io_call(
                self.inbox.claim,
                self.bot.id,
                "shop-precheckout-worker" if critical else "shop-polling-worker",
                lease_seconds=30,
                priorities=(1,) if critical else (0,),
                now=self.clock() if critical else max(self.clock(), self.store.now()),
            )
        if claim is None:
            return False
        try:
            update = Update.model_validate(claim.payload, context={"bot": self.bot})
            if update.pre_checkout_query is not None:
                record = await io_call(self.inbox.get, self.bot.id, claim.update_id)
                accepted = (
                    critical
                    and record is not None
                    and await self.precheckout.answer(
                        update.pre_checkout_query,
                        claim.update_id,
                        record.received_at,
                        self.clock,
                    )
                )
                if accepted:
                    await io_call(self.inbox.complete, claim, now=self.clock())
                else:
                    await io_call(
                        self.inbox.quarantine,
                        claim,
                        reason="manual-review",
                        now=self.clock(),
                    )
                return True
            async with asyncio.timeout(8):
                result = await self.dispatcher.feed_update(
                    self.bot, update, shop_durable_claim=self._claim_token
                )
        except asyncio.CancelledError:
            try:
                await io_call(
                    self.inbox.retry, claim, delay_seconds=0, now=self.store.now()
                )
            except InboxLeaseLost:
                pass
            raise
        except Exception:  # noqa: BLE001 -- retain failed handler work instead of acknowledging it
            try:
                await io_call(
                    self.inbox.retry, claim, delay_seconds=1, now=self.store.now()
                )
            except InboxLeaseLost:
                pass
        else:
            if result is UNHANDLED:
                await io_call(
                    self.inbox.quarantine,
                    claim,
                    reason="handler-rejected",
                    now=self.store.now(),
                )
            else:
                await io_call(self.inbox.complete, claim, now=self.store.now())
        return True

    async def drain_ready(self) -> int:
        processed = 0
        while await self.process_one(critical=True) or await self.process_one():
            processed += 1
        return processed

    async def run(self, stop: asyncio.Event, *, critical: bool = False) -> None:
        while not stop.is_set():
            if not await self.process_one(critical=critical):
                try:
                    await asyncio.wait_for(
                        stop.wait(), timeout=0.025 if critical else 0.1
                    )
                except TimeoutError:
                    pass

    async def serve(self, *, handle_signals: bool = True) -> None:
        self.install()
        stop = asyncio.Event()
        worker = asyncio.create_task(self.run(stop), name="shop-durable-worker")
        urgent = asyncio.create_task(
            self.run(stop, critical=True), name="shop-precheckout-worker"
        )
        polling = asyncio.create_task(
            self.dispatcher.start_polling(
                self.bot,
                close_bot_session=False,
                handle_signals=handle_signals,
                handle_as_tasks=False,
                polling_timeout=10,
                allowed_updates=sorted(self.kinds),
            ),
            name="shop-update-admission",
        )
        failed = asyncio.create_task(
            self._read_failed.wait(), name="shop-poll-read-health"
        )
        try:
            done, _ = await asyncio.wait(
                {worker, urgent, polling, failed}, return_when=asyncio.FIRST_COMPLETED
            )
            if failed in done:
                raise RuntimeError(
                    "Durable polling read retry budget exhausted; stored updates remain recoverable"
                )
            if worker in done:
                await worker
                raise RuntimeError("Durable worker stopped before polling")
            if urgent in done:
                await urgent
                raise RuntimeError("Pre-checkout worker stopped before polling")
            await polling
        finally:
            failed.cancel()
            await asyncio.gather(failed, return_exceptions=True)
            if not polling.done():
                polling.cancel()
            await asyncio.gather(polling, return_exceptions=True)
            stop.set()  # stop new claims, join a finite current handler before closing the Bot/session/lock.
            try:
                await asyncio.wait_for(
                    asyncio.shield(asyncio.gather(worker, urgent)), timeout=10
                )
            except (TimeoutError, asyncio.CancelledError):
                worker.cancel()
                urgent.cancel()
                await asyncio.gather(worker, urgent, return_exceptions=True)
            finally:
                self.close()
