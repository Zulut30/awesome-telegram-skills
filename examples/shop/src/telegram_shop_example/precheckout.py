"""Bounded local pre-checkout admission; an SDK answer is never a paid receipt.

Telegram's ten seconds start at Telegram send time. Our persisted eight-second
local budget starts at first receipt and cannot guarantee transport latency.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable

from aiogram.types import PreCheckoutQuery

from .storage import connection, io_call
from .store import Store


def fingerprint(query: PreCheckoutQuery) -> str:
    fields = [
        query.id,
        query.from_user.id,
        query.currency,
        query.total_amount,
        query.invoice_payload,
    ]
    return hashlib.sha256(
        json.dumps(fields, separators=(",", ":")).encode()
    ).hexdigest()


class PrecheckoutAdmissions:
    """Application-local reply journal. No row here grants purchased content."""

    def __init__(self, store: Store, *, budget: float = 8, capacity: int = 4):
        if type(budget) not in (int, float) or not 0.05 <= budget <= 8:
            raise ValueError(
                "Use a finite local pre-checkout budget up to eight seconds"
            )
        if type(capacity) is not int or not 1 <= capacity <= 100:
            raise ValueError("Use a bounded pre-checkout admission capacity")
        self.store, self.budget, self.capacity = store, budget, capacity
        with connection(store.database, write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS shop_precheckout_admission (
                bot_id INTEGER NOT NULL, query_id TEXT NOT NULL, update_id INTEGER NOT NULL,
                fingerprint TEXT NOT NULL, received_at REAL NOT NULL, deadline REAL NOT NULL,
                state TEXT NOT NULL, outcome TEXT NOT NULL, positive INTEGER NOT NULL DEFAULT 0,
                answered_at REAL, PRIMARY KEY(bot_id,query_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS shop_polling_owner (
                bot_id INTEGER PRIMARY KEY, unclean INTEGER NOT NULL)""")

    def open_owner(self) -> bool:
        with connection(self.store.database, write=True) as db:
            row = db.execute(
                "SELECT unclean FROM shop_polling_owner WHERE bot_id=?",
                (self.store.bot_id,),
            ).fetchone()
            db.execute(
                "INSERT OR REPLACE INTO shop_polling_owner VALUES (?,1)",
                (self.store.bot_id,),
            )
            db.execute(
                """UPDATE shop_precheckout_admission SET state='unknown',outcome='interrupted-native-answer'
                WHERE bot_id=? AND state='reply-started'""",
                (self.store.bot_id,),
            )
            return bool(row and row[0])

    def close_owner(self) -> None:
        with connection(self.store.database, write=True) as db:
            db.execute(
                "UPDATE shop_polling_owner SET unclean=0 WHERE bot_id=?",
                (self.store.bot_id,),
            )

    def observe(
        self, entries: list[tuple[int, PreCheckoutQuery, float, bool]], now: float
    ) -> None:
        with connection(self.store.database, write=True) as db:
            db.execute(
                """UPDATE shop_precheckout_admission SET state='expired',outcome='local-deadline'
                WHERE bot_id=? AND state IN ('pending','ready') AND deadline<=?""",
                (self.store.bot_id, now),
            )
            for update_id, query, first_seen, uncertain in entries:
                old = db.execute(
                    "SELECT * FROM shop_precheckout_admission WHERE bot_id=? AND query_id=?",
                    (self.store.bot_id, query.id),
                ).fetchone()
                if old:
                    # Incomplete prior batch, legacy receipt or changed native identity cannot gain freshness.
                    if old["state"] == "pending":
                        db.execute(
                            """UPDATE shop_precheckout_admission SET state='refused',outcome='incomplete-batch'
                            WHERE bot_id=? AND query_id=?""",
                            (self.store.bot_id, query.id),
                        )
                    continue
                active = db.execute(
                    """SELECT count(*) FROM shop_precheckout_admission
                    WHERE bot_id=? AND state IN ('pending','ready','reply-started') AND deadline>?""",
                    (self.store.bot_id, now),
                ).fetchone()[0]
                outcome = (
                    "uncertain-admission"
                    if uncertain
                    else "capacity"
                    if active >= self.capacity
                    else "admitting"
                )
                state = "pending" if outcome == "admitting" else "refused"
                db.execute(
                    """INSERT INTO shop_precheckout_admission
                    (bot_id,query_id,update_id,fingerprint,received_at,deadline,state,outcome)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        self.store.bot_id,
                        query.id,
                        update_id,
                        fingerprint(query),
                        first_seen,
                        first_seen + self.budget,
                        state,
                        outcome,
                    ),
                )

    def finish_batch(self, update_ids: list[int]) -> None:
        with connection(self.store.database, write=True) as db:
            for update_id in update_ids:
                db.execute(
                    """UPDATE shop_precheckout_admission SET state='ready',outcome='batch-committed'
                    WHERE bot_id=? AND update_id=? AND state='pending'""",
                    (self.store.bot_id, update_id),
                )

    def get(self, query_id: str) -> dict | None:
        with connection(self.store.database) as db:
            row = db.execute(
                "SELECT * FROM shop_precheckout_admission WHERE bot_id=? AND query_id=?",
                (self.store.bot_id, query_id),
            ).fetchone()
            return dict(row) if row else None

    def begin_answer(
        self, query: PreCheckoutQuery, update_id: int, positive: bool, now: float
    ) -> bool:
        with connection(self.store.database, write=True) as db:
            row = db.execute(
                "SELECT * FROM shop_precheckout_admission WHERE bot_id=? AND query_id=?",
                (self.store.bot_id, query.id),
            ).fetchone()
            if (
                not row
                or row["state"] != "ready"
                or row["update_id"] != update_id
                or row["fingerprint"] != fingerprint(query)
                or row["deadline"] <= now
            ):
                return False
            if positive:
                self.store._authorize(db, query.from_user.id, write=True)
                order = self.store.payment_order(
                    db,
                    self.store.bot_id,
                    query.from_user.id,
                    query.invoice_payload,
                    query.currency,
                    query.total_amount,
                )
                if order["status"] != "awaiting" or order["precheckout"] != query.id:
                    return False
            db.execute(
                """UPDATE shop_precheckout_admission
                SET state='reply-started',outcome='native-answer-pending',positive=? WHERE bot_id=? AND query_id=?""",
                (int(positive), self.store.bot_id, query.id),
            )
            return True

    def outcome(self, query_id: str, state: str, outcome: str, now: float) -> None:
        with connection(self.store.database, write=True) as db:
            db.execute(
                """UPDATE shop_precheckout_admission SET state=?,outcome=?,answered_at=?
                WHERE bot_id=? AND query_id=?""",
                (state, outcome, now, self.store.bot_id, query_id),
            )

    async def answer(
        self,
        query: PreCheckoutQuery,
        update_id: int,
        received_at: float,
        clock: Callable[[], float],
    ) -> bool:
        """True means terminal handled, False means quarantine. Never retry a native answer."""
        row = await io_call(self.get, query.id)
        if (
            not row
            or row["update_id"] != update_id
            or row["fingerprint"] != fingerprint(query)
            or row["received_at"] != received_at
        ):
            return False
        if row["state"] != "ready":
            if row["state"] == "reply-started":
                await io_call(
                    self.outcome,
                    query.id,
                    "unknown",
                    "interrupted-native-answer",
                    clock(),
                )
            return row["state"] == "answered"
        deadline = min(row["deadline"], received_at + self.budget)
        positive = False
        if deadline <= clock():
            await io_call(self.outcome, query.id, "expired", "local-deadline", clock())
            return False
        try:
            if (
                query.bot is None
                or query.bot.id != self.store.bot_id
                or query.from_user.is_bot
            ):
                raise ValueError("Untrusted query identity")
            async with asyncio.timeout(min(2, max(0, deadline - clock()))):
                await io_call(
                    self.store.precheckout,
                    self.store.bot_id,
                    query.from_user.id,
                    query.id,
                    query.invoice_payload,
                    query.currency,
                    query.total_amount,
                )
            positive = True
        except Exception:  # noqa: BLE001 -- every business/storage failure refuses positive approval
            positive = False
        if not await io_call(self.begin_answer, query, update_id, positive, clock()):
            await io_call(self.outcome, query.id, "expired", "local-deadline", clock())
            return False
        try:
            remaining = deadline - clock()
            if remaining <= 0:
                await io_call(
                    self.outcome,
                    query.id,
                    "expired",
                    "local-deadline-before-send",
                    clock(),
                )
                return False
            async with asyncio.timeout(min(2, remaining)):
                result = await query.answer(
                    ok=positive, error_message=None if positive else "Open /paysupport."
                )
            if result is not True:
                raise RuntimeError("Unconfirmed native answer")
        except BaseException as error:
            # reply-started was committed before any RPC. Cancellation/crash/replay cannot send True again.
            await io_call(
                self.outcome, query.id, "unknown", "native-answer-unknown", clock()
            )
            if isinstance(error, asyncio.CancelledError):
                raise
            return False
        await io_call(
            self.outcome, query.id, "answered", "native-answer-accepted", clock()
        )
        return True
