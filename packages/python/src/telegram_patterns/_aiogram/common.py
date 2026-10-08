"""Internal helpers shared by the aiogram adapter modules; not part of the public API.

Modules import these names instead of each other's `_private` helpers; error messages are unchanged.
"""

from __future__ import annotations

import re
from typing import Protocol, Sequence, TypeVar

from aiogram import Dispatcher, Router
from aiogram.types import Message

from ..errors import InvalidType, ValidationFailure


class _Keyed(Protocol):
    @property
    def key(self) -> str: ...


KeyedT = TypeVar('KeyedT', bound=_Keyed)


def callback_data(key: str, prefix: str) -> str:
    if not isinstance(prefix, str) or not prefix or not re.fullmatch(r"[a-zA-Z0-9_-]+:", prefix):
        raise ValidationFailure("Use a bounded ASCII prefix ending in ':'")
    if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", key):
        raise ValidationFailure("Use an opaque ASCII action key")
    result = prefix + key
    if len(result.encode("utf-8")) > 64:
        raise ValidationFailure("Callback data exceeds 64 bytes")
    return result


def unique_items(values: Sequence[object], kind: type[KeyedT]) -> tuple[KeyedT, ...]:
    """Items of one button type with menu-unique keys, e.g. unique_items(buttons, ActionButton)."""
    items = tuple(values)
    checked = tuple(item for item in items if isinstance(item, kind))
    if len(checked) != len(items):
        raise InvalidType(f"Use {kind.__name__} items")
    if len({item.key for item in checked}) != len(checked):
        raise ValidationFailure("Action keys must be unique within a menu")
    return checked


def check_chat_context(chat_type: str, business: bool) -> None:
    if chat_type not in {'private', 'group', 'supergroup', 'channel'} or type(business) is not bool:
        raise ValidationFailure('Specify a supported chat_type and a bool business flag')


def fits_text(text: object, limit: int | None = None) -> bool:
    """Nonblank str within limit UTF-16 code units, the unit Telegram counts text in."""
    try:
        return (
            isinstance(text, str)
            and bool(text.strip())
            and (limit is None or len(text.encode('utf-16-le')) // 2 <= limit)
        )
    except UnicodeError:
        return False


def check_text(text: str, *, limit: int | None = None) -> None:
    if not fits_text(text, limit):
        raise ValidationFailure('Use nonempty valid text within the requested limit')


def message_bot_id(message: Message) -> int:
    bot = message.bot
    if bot is None:
        raise RuntimeError('Forms require a Message bound to the current Bot')
    return bot.id


def message_actor_id(message: Message) -> int:
    user = message.from_user
    if user is None:
        raise RuntimeError('Forms require a user author')
    return user.id


def owning_dispatcher(router: Router, injected: Dispatcher | None) -> Dispatcher:
    """The Dispatcher that includes router. aiogram 3.31+ injects it into every handler; older releases do it
    only in polling, so feed_update and webhooks reach the handler without it."""
    if isinstance(injected, Dispatcher):
        return injected
    node = router
    while node.parent_router is not None:
        node = node.parent_router
    if not isinstance(node, Dispatcher):
        raise RuntimeError('Include the router in the Dispatcher that receives the updates')
    return node
