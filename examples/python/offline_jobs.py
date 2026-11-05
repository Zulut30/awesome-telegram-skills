"""Fake transport only: restart uncertainty, cancellation, opt-out and flood retry."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from telegram_patterns.jobs import SQLiteJobQueue


class FakeTransport:
    def __init__(self) -> None:
        self.calls = 0
        self.effects: list[int] = []

    def send(self, *, flood: bool = False) -> dict[str, int | str]:
        self.calls += 1
        if flood:
            return {"outcome": "flood", "retry_after": 5}
        message_id = len(self.effects) + 1
        self.effects.append(message_id)
        return {"outcome": "sent", "message_id": message_id}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="telegram-jobs-demo-") as temporary:
        database = Path(temporary) / "jobs.sqlite"
        queue = SQLiteJobQueue(database)
        queue.initialize()
        transport = FakeTransport()
        queue.set_recipient(100, 200, subscribed=True, reachable=True)
        queue.schedule(
            100,
            "reminder:1",
            200,
            {"text": "offline fixture"},
            due_at=100,
            deadline_at=1000,
            now=90,
        )
        first = queue.claim(100, "before-restart", lease_seconds=10, now=100)
        if first is None or queue.start(first, now=100).state != "sending":
            raise RuntimeError("Expected dispatch admission")
        response = transport.send()
        # Model a process losing its response/finish after the fake remote effect.
        cancellation = queue.cancel(100, "reminder:1")
        restarted = SQLiteJobQueue(database)
        no_automatic_retry = restarted.claim(100, "after-restart", now=110) is None
        unknown = restarted.get(100, "reminder:1")
        if unknown is None or unknown.state != "unknown":
            raise RuntimeError("Expected a durable unknown outcome")
        # This fixture can inspect its own fake transport; a real service needs actual evidence.
        reviewed = restarted.reconcile(
            100,
            "reminder:1",
            expected_revision=unknown.revision,
            evidence_ref="fixture-review:1",
            outcome="sent",
            message_id=int(response["message_id"]),
        )
        restarted.schedule(
            100,
            "reminder:2",
            200,
            {"text": "suppressed fixture"},
            due_at=120,
            deadline_at=1000,
            now=110,
        )
        restarted.set_recipient(100, 200, subscribed=False, reachable=True)
        if restarted.claim(100, "worker", now=120) is not None:
            raise RuntimeError("Opted-out work must not be issued")

        restarted.set_recipient(101, 201, subscribed=True, reachable=True)
        restarted.schedule(
            101,
            "flood:1",
            201,
            {"text": "flood fixture"},
            due_at=100,
            deadline_at=1000,
            max_attempts=2,
            now=90,
        )
        flood_claim = restarted.claim(101, "worker", now=100)
        if (
            flood_claim is None
            or restarted.start(flood_claim, now=100).state != "sending"
        ):
            raise RuntimeError("Expected dispatch admission")
        rejection = transport.send(flood=True)
        delayed = restarted.finish(
            flood_claim,
            outcome="flood",
            retry_after=int(rejection["retry_after"]),
            now=101,
        )
        waiting = restarted.claim(101, "worker", now=105.999) is None
        retry = restarted.claim(101, "worker", now=106)
        if retry is None or restarted.start(retry, now=106).state != "sending":
            raise RuntimeError("Expected bounded flood retry")
        success = transport.send()
        sent = restarted.finish(
            retry, outcome="sent", message_id=int(success["message_id"]), now=107
        )

        print(
            json.dumps(
                {
                    "cancel_after_start_state": cancellation.state,
                    "cancel_requested": cancellation.cancel_requested,
                    "restart_state_before_review": unknown.state,
                    "restart_automatic_retry_blocked": no_automatic_retry,
                    "reviewed_state": reviewed.state,
                    "opted_out_state": restarted.get(100, "reminder:2").state,
                    "flood_due_at": delayed.due_at,
                    "flood_wait_respected": waiting,
                    "flood_final_state": sent.state,
                    "flood_attempts": sent.attempts,
                    "transport_calls": transport.calls,
                    "remote_effects": len(transport.effects),
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
