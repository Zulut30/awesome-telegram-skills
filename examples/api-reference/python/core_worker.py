"""Owned worker drain and safe correlation; no Telegram, external sender or background service."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from telegram_patterns import (
    InboxWorker, WorkerOutcome, settled_to_thread, SQLiteInbox,
    Telemetry, TelemetryContext, TelemetryMetric, TelemetryOutcome, TelemetrySnapshot, TelemetryStage,
)


async def main() -> None:
    events: list[str] = []
    telemetry = Telemetry(b'local-fixture-key-with-32-bytes!!x', events.append)
    stage: TelemetryStage = 'operation'
    outcome: TelemetryOutcome = 'replayed'
    with telemetry.bind(bot_id=100, update_id=1, operation_id='server-intent') as context:
        observed: TelemetryContext = context
        assert observed.update_ref is not None and observed.operation_ref is not None
        telemetry.emit(stage, outcome, duration_ms=1, attempt=2)
    assert telemetry.current() is None and 'server-intent' not in events[0]
    snapshot: TelemetrySnapshot = telemetry.snapshot()
    metric: TelemetryMetric = snapshot.metrics[0]
    assert metric.count == 1 and metric.retries == 1
    with TemporaryDirectory() as directory:
        inbox = SQLiteInbox(Path(directory) / 'worker.sqlite')
        inbox.initialize()
        inbox.receive(100, 1, {'update_id': 1, 'message': {}})
        handled: list[int] = []
        def decode(payload: dict[str, Any]) -> int:
            return int(payload['update_id'])
        async def handle(update_id: int, claim: Any) -> bool:
            # Host normally commits an idempotent operation/outbox before returning exactly True.
            handled.append(update_id)
            return True
        worker = InboxWorker(inbox, 100, 'fixture-worker', decode, handle, telemetry=telemetry)
        result: WorkerOutcome = await worker.run_one()
        assert result == 'done' and handled == [1]
        stored = await settled_to_thread(inbox.get, 100, 1)
        assert stored is not None and stored.state == 'done'
        stop = asyncio.Event()
        stop.set()
        await worker.serve(stop)  # An already stopped owner does not admit work.
    print(json.dumps({'passed': True, 'case': 'core_worker', 'network': False}))


if __name__ == '__main__':
    asyncio.run(main())
