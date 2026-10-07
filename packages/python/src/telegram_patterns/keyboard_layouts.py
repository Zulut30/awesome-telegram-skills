"""Flat button compositions with explicit width patterns and presentation fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, TypeVar

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from .errors import InvalidType, ValidationFailure
from .keyboards import ActionButton, _callback_data, _items
from .native_keyboards import ChatType, _context, inline_keyboard, reply_keyboard

T = TypeVar('T')


@dataclass(frozen=True, slots=True)
class KeyboardLayout:
    """Widths 1..8; repeat cycles, otherwise the final width fills the tail.

    Values are component limits, not a statement of Telegram client limits.
    """

    widths: Sequence[int] = (2,)
    repeat: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.widths, (str, bytes)) or not isinstance(self.widths, Sequence):
            raise InvalidType('Use a tuple of row widths')
        try:
            widths = tuple(self.widths)
        except TypeError:
            raise InvalidType('Use a tuple of row widths') from None
        if not 1 <= len(widths) <= 100 or any(type(n) is not int or not 1 <= n <= 8 for n in widths):
            raise ValidationFailure('Use 1..100 widths in 1..8 (component limits)')
        if type(self.repeat) is not bool:
            raise InvalidType('Repeat must be bool')
        object.__setattr__(self, 'widths', widths)


@dataclass(frozen=True, slots=True)
class KeyboardCapabilities:
    """Host-supplied context/capabilities, never inferred from a pressing user's Premium.

    Unknown presentation defaults to text-only standard styling. Verified emoji
    entitlement is scoped by the host to this chat/message route; construction
    does not query Telegram, prove entitlement or check callback authorization.
    """

    chat_type: ChatType = 'private'
    business: bool = False
    styles: bool = False
    custom_emoji: bool = False
    emoji_entitlement_verified: bool = False

    def __post_init__(self) -> None:
        _context(self.chat_type, self.business)
        if any(type(flag) is not bool for flag in (self.styles, self.custom_emoji, self.emoji_entitlement_verified)):
            raise InvalidType('Presentation capabilities must be bool')


def _rows(buttons: Sequence[T], layout: KeyboardLayout, capabilities: KeyboardCapabilities) -> list[list[T]]:
    if not isinstance(layout, KeyboardLayout) or not isinstance(capabilities, KeyboardCapabilities):
        raise InvalidType('Use KeyboardLayout and KeyboardCapabilities')
    if isinstance(buttons, (str, bytes)):
        raise InvalidType('Use a sequence of buttons')
    items = list(buttons)
    if not 1 <= len(items) <= 100:
        raise ValidationFailure('Use 1..100 buttons (component limit)')
    rows, offset, index = [], 0, 0
    while offset < len(items):
        width = layout.widths[index % len(layout.widths) if layout.repeat else min(index, len(layout.widths) - 1)]
        rows.append(items[offset : offset + width])
        offset += width
        index += 1
    return rows


def inline_layout(
    buttons: Sequence[InlineKeyboardButton],
    layout: KeyboardLayout = KeyboardLayout(),
    *,
    capabilities: KeyboardCapabilities = KeyboardCapabilities(),
    invoice: bool = False,
    force_reply: bool = False,
) -> InlineKeyboardMarkup:
    """Snapshot ordered native buttons; reject invalid data before applying fallback."""
    rows = _rows(buttons, layout, capabilities)
    markup = inline_keyboard(
        rows,
        chat_type=capabilities.chat_type,
        business=capabilities.business,
        invoice=invoice,
        force_reply=force_reply,
        emoji_entitlement_verified=capabilities.custom_emoji and capabilities.emoji_entitlement_verified,
    )
    if not capabilities.styles:
        for row in markup.inline_keyboard:
            for button in row:
                button.style = None
    return markup


def reply_layout(
    buttons: Sequence[str | KeyboardButton],
    layout: KeyboardLayout = KeyboardLayout(),
    *,
    capabilities: KeyboardCapabilities = KeyboardCapabilities(),
    resize: bool = True,
    one_time: bool = False,
    persistent: bool = False,
    placeholder: str | None = None,
    selective: bool = False,
    force_reply: bool = False,
) -> ReplyKeyboardMarkup:
    """Flat reply buttons with the same request/context validation as reply_keyboard."""
    rows = _rows(buttons, layout, capabilities)
    markup = reply_keyboard(
        rows,
        chat_type=capabilities.chat_type,
        business=capabilities.business,
        resize=resize,
        one_time=one_time,
        persistent=persistent,
        placeholder=placeholder,
        selective=selective,
        force_reply=force_reply,
        emoji_entitlement_verified=capabilities.custom_emoji and capabilities.emoji_entitlement_verified,
    )
    if not capabilities.styles:
        for row in markup.keyboard:
            for button in row:
                button.style = None
    return markup


def action_layout(
    buttons: Sequence[ActionButton],
    layout: KeyboardLayout = KeyboardLayout(),
    *,
    prefix: str = 'act:',
    capabilities: KeyboardCapabilities = KeyboardCapabilities(),
    force_reply: bool = False,
) -> InlineKeyboardMarkup:
    """Unique opaque callback keys and mixed rows; callback ACL remains at the host."""
    # Snapshot descriptors once. The native builder validates all fields before
    # a presentation enhancement is stripped.
    if isinstance(buttons, (str, bytes)):
        raise InvalidType('Use ActionButton items')
    items = _items(buttons)
    _rows(items, layout, capabilities)
    native = [
        InlineKeyboardButton(
            text=item.text,
            callback_data=_callback_data(item.key, prefix),
            style=item.style,
            icon_custom_emoji_id=item.custom_emoji_id,
        )
        for item in items
    ]
    return inline_layout(native, layout, capabilities=capabilities, force_reply=force_reply)
