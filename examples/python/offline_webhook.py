"""Temporary loopback HTTP + SQLite fixture; never contacts Telegram or changes webhook."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from aiohttp.test_utils import TestClient, TestServer
from telegram_patterns.inbox import SQLiteInbox
from telegram_patterns.webhook import WebhookReceiver, create_aiohttp_webhook_app


async def main() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "receipt.sqlite"
        inbox = SQLiteInbox(path)
        inbox.initialize()
        secret = "local_fixture_only"
        receiver = WebhookReceiver(inbox, bot_id=100, secret_token=secret)
        headers = {"X-Telegram-Bot-Api-Secret-Token": secret}
        async with TestClient(
            TestServer(create_aiohttp_webhook_app(receiver))
        ) as client:
            payload = {"update_id": 1, "message": {"text": "offline fixture"}}
            first = await client.post(
                "/telegram/webhook", json=payload, headers=headers
            )
            assert first.status == 200 and (await first.json())["status"] == "accepted"
            reopened = SQLiteInbox(path)
            assert reopened.get(100, 1) is not None
            duplicate = await client.post(
                "/telegram/webhook", json=payload, headers=headers
            )
            assert duplicate.status == 200 and (await duplicate.json())["duplicate"]
            forbidden = await client.post("/telegram/webhook", json=payload)
            assert forbidden.status == 403
            future = await client.post(
                "/telegram/webhook",
                json={"update_id": 2, "future_event": {}},
                headers=headers,
            )
            assert (
                future.status == 200
                and (await future.json())["status"] == "quarantined"
            )
        print(
            json.dumps(
                {
                    "passed": True,
                    "telegram_network": False,
                    "scope": "loopback-http",
                    "pending": inbox.counts(100)["pending"],
                    "quarantined": inbox.counts(100)["quarantined"],
                }
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
