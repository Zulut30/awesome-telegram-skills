"""Optional aiogram action keyboards and local pagination builders."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .errors import InvalidType, ValidationFailure

ButtonStyle = Literal["primary", "success", "danger"]


def _callback_data(key: str, prefix: str) -> str:
    if not isinstance(prefix, str) or not prefix or not re.fullmatch(r"[a-zA-Z0-9_-]+:", prefix):
        raise ValidationFailure("Use a bounded ASCII prefix ending in ':'")
    if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", key):
        raise ValidationFailure("Use an opaque ASCII action key")
    result = prefix + key
    if len(result.encode("utf-8")) > 64:
        raise ValidationFailure("Callback data exceeds 64 bytes")
    return result


@dataclass(frozen=True, slots=True)
class ActionButton:
    text: str
    key: str
    style: ButtonStyle | None = None
    custom_emoji_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValidationFailure("Button label required")
        if self.style not in {None, "primary", "success", "danger"}:
            raise ValidationFailure("Unknown button style")
        if self.custom_emoji_id is not None and (
            not isinstance(self.custom_emoji_id, str) or not re.fullmatch(r"[0-9]+", self.custom_emoji_id)
        ):
            raise ValidationFailure("Custom emoji ID must be a decimal string")
        _callback_data(self.key, "act:")


def _button(button: ActionButton, prefix: str, verified: bool) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=button.text,
        callback_data=_callback_data(button.key, prefix),
        style=button.style,
        icon_custom_emoji_id=button.custom_emoji_id if verified else None,
    )


def action_keyboard(
    text: str,
    key: str,
    *,
    prefix: str = "act:",
    style: ButtonStyle | None = None,
    custom_emoji_id: str | None = None,
    emoji_entitlement_verified: bool = False,
) -> InlineKeyboardMarkup:
    """Entitlement is a server-verified capability for the target chat/context."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button(ActionButton(text, key, style, custom_emoji_id), prefix, emoji_entitlement_verified)]]
    )


def _columns(columns: int) -> None:
    if type(columns) is not int or not 1 <= columns <= 8:
        raise ValidationFailure("Use 1..8 columns")


def _items(buttons: Sequence[ActionButton]) -> tuple[ActionButton, ...]:
    items = tuple(buttons)
    if any(not isinstance(item, ActionButton) for item in items):
        raise InvalidType("Use ActionButton items")
    if len({item.key for item in items}) != len(items):
        raise ValidationFailure("Action keys must be unique within a menu")
    return items


def action_menu(
    buttons: Sequence[ActionButton], *, columns: int = 2, prefix: str = "act:", emoji_entitlement_verified: bool = False
) -> InlineKeyboardMarkup:
    """Build up to 100 buttons; empty input produces an empty keyboard."""
    _columns(columns)
    _callback_data("k", prefix)
    items = _items(buttons)
    if len(items) > 100:
        raise ValidationFailure("Use pagination for more than 100 buttons")
    rows = [
        [_button(item, prefix, emoji_entitlement_verified) for item in items[offset : offset + columns]]
        for offset in range(0, len(items), columns)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dataclass(frozen=True, slots=True)
class MenuPage:
    markup: InlineKeyboardMarkup
    page: int
    page_count: int
    total_items: int


def paginated_menu(
    buttons: Sequence[ActionButton],
    *,
    page: int = 0,
    page_size: int = 6,
    columns: int = 2,
    action_prefix: str = "act:",
    page_prefix: str = "page:",
    emoji_entitlement_verified: bool = False,
) -> MenuPage:
    """Zero-based local view, clamped after list shrink; never grants object access."""
    _columns(columns)
    _callback_data("k", action_prefix)
    _callback_data("0", page_prefix)
    if action_prefix == page_prefix:
        raise ValidationFailure("Action and pagination prefixes must differ")
    if type(page) is not int or page < 0:
        raise ValidationFailure("Page must be a nonnegative integer")
    if type(page_size) is not int or not 1 <= page_size <= 98:
        raise ValidationFailure("Use page_size 1..98, leaving room for navigation")
    items = _items(buttons)
    # Validate the entire data set before producing any partially usable page.
    for item in items:
        _callback_data(item.key, action_prefix)
    count = max(1, (len(items) + page_size - 1) // page_size)
    current = min(page, count - 1)
    markup = action_menu(
        items[current * page_size : (current + 1) * page_size],
        columns=columns,
        prefix=action_prefix,
        emoji_entitlement_verified=emoji_entitlement_verified,
    )
    navigation = []
    if current > 0:
        navigation.append(_button(ActionButton("← Назад", str(current - 1)), page_prefix, False))
    if current + 1 < count:
        navigation.append(_button(ActionButton("Далее →", str(current + 1)), page_prefix, False))
    if navigation:
        markup.inline_keyboard.append(navigation)
    return MenuPage(markup=markup, page=current, page_count=count, total_items=len(items))


def page_number(data: str | None, *, prefix: str = "page:") -> int | None:
    """Parse only a canonical page callback; return None for untrusted malformed data."""
    _callback_data("0", prefix)
    if not isinstance(data, str) or not data.startswith(prefix):
        return None
    key = data[len(prefix) :]
    try:
        _callback_data(key, prefix)
    except ValueError:
        return None
    if not re.fullmatch(r"0|[1-9][0-9]*", key):
        return None
    return int(key)
