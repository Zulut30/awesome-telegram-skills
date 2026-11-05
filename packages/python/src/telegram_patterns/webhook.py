"""Bounded webhook admission: authenticate, preserve the Update, then acknowledge.

SDK decoding belongs to a worker after durable receipt. This module neither configures
Telegram delivery nor starts workers, and importing it does not require an HTTP framework.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

from ._shared import canonical_json, payload_digest
from .errors import UnsupportedCapability, ValidationFailure
from .inbox import InboxConflict

if TYPE_CHECKING:
    from aiohttp import web

    from .inbox import SQLiteInbox

WebhookCode = Literal[
    'accepted',
    'duplicate',
    'quarantined',
    'forbidden',
    'invalid-body',
    'payload-too-large',
    'payload-conflict',
    'storage-unavailable',
]

# Bot API 10.3 Update fields, checked against the official metadata snapshot.
# A new event is retained in quarantine; it is never silently treated as processed.
_UPDATE_TYPES = frozenset(
    {
        'message',
        'edited_message',
        'channel_post',
        'edited_channel_post',
        'business_connection',
        'business_message',
        'edited_business_message',
        'deleted_business_messages',
        'guest_message',
        'message_reaction',
        'message_reaction_count',
        'inline_query',
        'chosen_inline_result',
        'callback_query',
        'shipping_query',
        'pre_checkout_query',
        'purchased_paid_media',
        'poll',
        'poll_answer',
        'my_chat_member',
        'chat_member',
        'chat_join_request',
        'chat_boost',
        'removed_chat_boost',
        'managed_bot',
        'subscription',
        'stopped_message_generation',
    }
)


@dataclass(frozen=True, slots=True)
class WebhookResponse:
    status: int
    code: WebhookCode
    duplicate: bool = False

    @property
    def accepted(self) -> bool:
        return self.status == 200

    def as_dict(self) -> dict[str, str | bool]:
        """Safe HTTP body: no token, payload, arbitrary exception or personal identifier."""
        return {'status': self.code, 'accepted': self.accepted, 'duplicate': self.duplicate}


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON member')
        result[key] = value
    return result


def _constant(_value: str) -> Any:
    raise ValueError('Non-finite JSON constant')


class WebhookReceiver:
    """SDK-free admission to one bot's SQLiteInbox; initialize the inbox explicitly.

    Authenticated JSON must contain an integer update_id and an event envelope.
    Semantic SDK parsing is deliberately deferred until after durable receipt: decode
    failure/timeout must quarantine the original event, not lose it after HTTP ACK.
    Unknown/ambiguous event kinds are retained atomically in quarantine and acknowledged.
    """

    def __init__(
        self,
        inbox: SQLiteInbox,
        *,
        bot_id: int,
        secret_token: str,
        max_body_bytes: int = 1024 * 1024,
        payload_version: int = 1,
    ) -> None:
        if type(bot_id) is not int or not 1 <= bot_id <= 2**63 - 1:
            raise ValidationFailure('Use a positive bounded bot ID')
        if not isinstance(secret_token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', secret_token):
            raise ValidationFailure('Configure a Bot API webhook secret token')
        if type(max_body_bytes) is not int or not 128 <= max_body_bytes <= 8 * 1024 * 1024:
            raise ValidationFailure('Use a body limit between 128 bytes and 8 MiB')
        if type(payload_version) is not int or not 1 <= payload_version <= 2**31 - 1:
            raise ValidationFailure('Use a positive internal payload version')
        if not callable(getattr(inbox, 'receive', None)) or max_body_bytes > inbox.max_payload_bytes:
            raise ValidationFailure('Configure an inbox with a compatible payload limit')
        self._inbox = inbox
        self._bot_id = bot_id
        self._secret = secret_token.encode('ascii')
        self._max_body_bytes = max_body_bytes
        self._payload_version = payload_version

    @property
    def max_body_bytes(self) -> int:
        return self._max_body_bytes

    def authorized(self, supplied_secret: str | None) -> bool:
        if not isinstance(supplied_secret, str) or not 1 <= len(supplied_secret) <= 256:
            return False
        try:
            return hmac.compare_digest(self._secret, supplied_secret.encode('utf-8'))
        except UnicodeError:
            return False

    def receive(self, body: bytes, supplied_secret: str | None) -> WebhookResponse:
        """Return 200 only after receive() commits, including durable duplicate/quarantine."""
        if not self.authorized(supplied_secret):
            return WebhookResponse(403, 'forbidden')
        if not isinstance(body, bytes):
            return WebhookResponse(400, 'invalid-body')
        if len(body) > self._max_body_bytes:
            return WebhookResponse(413, 'payload-too-large')
        try:
            payload = json.loads(body.decode('utf-8'), object_pairs_hook=_object, parse_constant=_constant)
            if not isinstance(payload, dict):
                raise ValueError('An Update must be an object')
            update_id = payload.get('update_id')
            if type(update_id) is not int or not 0 <= update_id <= 2**63 - 1:
                raise ValueError('Invalid Update identity')
            events = set(payload) - {'update_id'}
            if not events:
                raise ValueError('Missing event envelope')
            for kind in events & _UPDATE_TYPES:
                if not isinstance(payload[kind], dict):
                    raise ValueError('Invalid event envelope')
            payload_digest(payload)  # finite JSON and bounded nesting before durable admission
            if len(canonical_json(payload).encode('utf-8')) > self._inbox.max_payload_bytes:
                return WebhookResponse(413, 'payload-too-large')
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return WebhookResponse(400, 'invalid-body')
        reason: Literal['unknown-update-kind'] | None = None
        if len(events) != 1 or not events.issubset(_UPDATE_TYPES):
            reason = 'unknown-update-kind'
        try:
            receipt = self._inbox.receive(
                self._bot_id,
                update_id,
                cast(dict[str, Any], payload),
                payload_version=self._payload_version,
                quarantine_reason=reason,
            )
            code: WebhookCode = (
                'quarantined' if receipt.state == 'quarantined' else 'duplicate' if receipt.duplicate else 'accepted'
            )
            return WebhookResponse(200, code, receipt.duplicate)
        except InboxConflict:
            return WebhookResponse(409, 'payload-conflict')
        except Exception:
            # No success ACK or reflection of a token/payload from a storage diagnostic.
            return WebhookResponse(503, 'storage-unavailable')


def create_aiohttp_webhook_app(
    receiver: WebhookReceiver, *, path: str = '/telegram/webhook', read_timeout_seconds: float = 10.0
) -> web.Application:
    """Optional aiohttp adapter; does not bind a socket, set webhook, drop updates or poll.

    aiohttp is supplied by the application (also present with the aiogram extra).
    The host owns TLS/reverse proxy, process lifecycle, inbox workers and observability.
    """
    if not isinstance(receiver, WebhookReceiver):
        raise ValidationFailure('Use a WebhookReceiver')
    if not isinstance(path, str) or not re.fullmatch(r'/[A-Za-z0-9_/-]{0,255}', path):
        raise ValidationFailure('Use a fixed HTTP route without credentials or query')
    if (
        type(read_timeout_seconds) not in {int, float}
        or not math.isfinite(read_timeout_seconds)
        or not 0 < read_timeout_seconds <= 300
    ):
        raise ValidationFailure('Use a finite positive HTTP body timeout')
    try:
        from aiohttp import web
    except ImportError:
        raise UnsupportedCapability('The HTTP adapter needs the application aiohttp dependency') from None

    async def handle(request: web.Request) -> web.Response:
        secrets = request.headers.getall('X-Telegram-Bot-Api-Secret-Token', [])
        if len(secrets) != 1 or not receiver.authorized(secrets[0]):
            return web.json_response(WebhookResponse(403, 'forbidden').as_dict(), status=403)
        if (
            request.content_type != 'application/json'
            or (request.charset or 'utf-8').lower() not in {'utf-8', 'utf8'}
            or request.headers.get('Content-Encoding', 'identity').lower() != 'identity'
        ):
            return web.json_response({'status': 'unsupported-content', 'accepted': False}, status=415)
        if request.content_length is not None and request.content_length > receiver.max_body_bytes:
            return web.json_response(WebhookResponse(413, 'payload-too-large').as_dict(), status=413)
        body = bytearray()
        try:
            async with asyncio.timeout(read_timeout_seconds):
                async for chunk in request.content.iter_chunked(min(16384, receiver.max_body_bytes + 1)):
                    if len(body) + len(chunk) > receiver.max_body_bytes:
                        return web.json_response(WebhookResponse(413, 'payload-too-large').as_dict(), status=413)
                    body.extend(chunk)
        except TimeoutError:
            return web.json_response({'status': 'body-timeout', 'accepted': False}, status=408)
        except (ConnectionError, OSError):
            return web.json_response({'status': 'body-incomplete', 'accepted': False}, status=400)
        # Cancellation can leave an already committed receive in the thread. Retry is deduplicated.
        result = await asyncio.to_thread(receiver.receive, bytes(body), secrets[0])
        return web.json_response(result.as_dict(), status=result.status)

    app = web.Application(client_max_size=receiver.max_body_bytes, handler_args={'auto_decompress': False})
    app.router.add_post(path, handle)
    return app
