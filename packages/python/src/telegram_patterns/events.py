"""Observe received Bot API updates without copying their contents into logs."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable, Literal, Mapping, TypeAlias

from aiogram import BaseMiddleware, Router
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import Message, TelegramObject, Update

log = logging.getLogger(__name__)

UpdatePhase: TypeAlias = Literal['received', 'handled', 'unhandled', 'failed', 'cancelled']


@dataclass(frozen=True, slots=True)
class UpdateTrace:
    update_id: int
    kind: str
    phase: UpdatePhase
    detail: str | None = None
    actor_id: int | None = None
    chat_id: int | None = None


def update_kinds(update: Update) -> tuple[str, ...]:
    return tuple(name for name in Update.model_fields if name != 'update_id' and getattr(update, name) is not None)


def _trace(update: Update, phase: UpdatePhase, identifiers: bool) -> UpdateTrace:
    kinds = update_kinds(update)
    kind = kinds[0] if len(kinds) == 1 else ('ambiguous' if kinds else 'unknown')
    event = getattr(update, kind, None)
    detail = None
    if isinstance(event, Message):
        detail = next((name for name in ('contact', 'location', 'users_shared', 'chat_shared', 'web_app_data',
                                        'successful_payment', 'refunded_payment', 'photo', 'video', 'document')
                       if getattr(event, name, None) is not None), None)
        if detail is None and event.text is not None: detail = 'command' if event.text.startswith('/') else 'text'
    actor = getattr(event, 'from_user', None) or getattr(event, 'user', None)
    chat = getattr(event, 'chat', None)
    if chat is None: chat = getattr(getattr(event, 'message', None), 'chat', None)
    return UpdateTrace(update.update_id, kind, phase, detail,
                       getattr(actor, 'id', None) if identifiers else None,
                       getattr(chat, 'id', None) if identifiers else None)


class UpdateObserver(BaseMiddleware):
    """Outer middleware on dispatcher.update; no new Telegram subscriptions.

    Best-effort telemetry by default: recorder errors don't break bot handlers.
    No message text, callback data, contacts, initData or exception strings are
    recorded. IDs are opt-in. This is not durable audit/inbox/idempotence.
    """
    def __init__(self, record: Callable[[UpdateTrace], Awaitable[None]], *, include_ids: bool = False) -> None:
        if not callable(record) or type(include_ids) is not bool:
            raise TypeError('Use an async recorder and a bool include_ids flag')
        self.record, self.include_ids = record, include_ids

    async def emit(self, trace: UpdateTrace) -> None:
        try:
            await self.record(trace)
        except Exception as error:
            log.warning('Update recorder failed (%s)', type(error).__name__)

    async def __call__(self, handler: Callable[..., Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any:
        if not isinstance(event, Update):
            raise TypeError('Register UpdateObserver on dispatcher.update, not a message observer')
        await self.emit(_trace(event, 'received', self.include_ids))
        try:
            result = await handler(event, data)
        except asyncio.CancelledError:
            await self.emit(_trace(event, 'cancelled', self.include_ids))
            raise
        except Exception:
            await self.emit(_trace(event, 'failed', self.include_ids))
            raise
        await self.emit(_trace(event, 'unhandled' if result is UNHANDLED else 'handled', self.include_ids))
        return result


def event_router(handlers: Mapping[str, Callable[..., Awaitable[Any]]]) -> Router:
    """Register native update handlers by exact SDK event name; no payload adapter.

    Each handler still owns ACK/auth/validation/effect. Registration advertises
    these kinds to SDK resolve_used_update_types; Telegram rights remain separate.
    """
    router = Router()
    if not isinstance(handlers, Mapping) or not handlers:
        raise ValueError('Provide at least one native update handler')
    for kind, handler in handlers.items():
        if kind not in Update.model_fields or kind == 'update_id' or kind not in router.observers or not callable(handler):
            raise ValueError('Use a supported Update kind and a callable handler')
        router.observers[kind].register(handler)
    return router
