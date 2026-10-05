"""Attach shareable-note search; host supplies catalog, ACL and a persistent secret."""
from __future__ import annotations
from typing import Awaitable, Callable, Sequence
from aiogram import Router
from aiogram.types import ChosenInlineResult, InlineQuery
from telegram_patterns.aiogram import InlineAuthorizer, InlineItem, InlineSearch, inline_query_router

CatalogLoader = Callable[[int], Awaitable[tuple[str, Sequence[InlineItem]]]]
PermissionRevision = Callable[[int], Awaitable[str]]
FeedbackObserver = Callable[[ChosenInlineResult], Awaitable[None]]


def inline_search_router(load_catalog: CatalogLoader, authorize: InlineAuthorizer,
                         permission_revision: PermissionRevision, *, cursor_secret: bytes,
                         page_size: int = 20, feedback: FeedbackObserver | None = None) -> Router:
    async def provider(query: InlineQuery) -> InlineSearch:
        revision, items = await load_catalog(query.from_user.id)
        # Items are explicitly shareable. A chosen item is sent to a chat partner,
        # even with is_personal=True; private notes must retain shareable=False.
        # cache_time=0 keeps restricted results from Telegram's reusable cache.
        return InlineSearch(items, secret=cursor_secret, revision=revision, page_size=page_size,
                            allowed_chat_types=('sender', 'private', 'group', 'supergroup', 'channel'))

    router = inline_query_router(provider, authorize=authorize, permission_revision=permission_revision)
    if feedback is not None:
        @router.chosen_inline_result()
        async def chosen(result: ChosenInlineResult) -> None:
            # Optional observation only. Absence of feedback never proves that
            # nothing was sent; this callback must not grant access or charge.
            await feedback(result)
    return router
