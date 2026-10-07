"""Optional calendar/time markup, composed with the host's guarded controller."""

from __future__ import annotations

from datetime import date
from typing import Callable, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .._shared import resolve_zone
from ..calendar_core import CalendarMonth, TimeSlot
from ..errors import InvalidType, UnsupportedCapability, ValidationFailure
from ..texts import Texts
from .keyboard_layouts import KeyboardCapabilities, KeyboardLayout, inline_layout
from .native_keyboards import inline_keyboard


def calendar_keyboard(
    month: CalendarMonth,
    callback_for: Callable[[date], str],
    *,
    navigation: tuple[str, str] | None = None,
    disabled_buttons: bool = False,
    capabilities: KeyboardCapabilities = KeyboardCapabilities(),
    texts: Texts | None = None,
) -> InlineKeyboardMarkup:
    """Monday-first full grid only with host-verified DisabledButton support.

    Default fallback lists available dates with weekday labels; unavailable
    days have no callbacks. Full-grid empty/header/unavailable cells are truly
    disabled, never no-op callbacks. Host supplies owner/revision-bound data,
    checks availability again in the booking transaction and owns navigation.
    """
    if not isinstance(month, CalendarMonth) or not callable(callback_for):
        raise InvalidType('Use CalendarMonth and a synchronous callback factory')
    if type(disabled_buttons) is not bool or not isinstance(capabilities, KeyboardCapabilities):
        raise InvalidType('Use explicit capabilities and bool disabled_buttons')
    if capabilities.business or capabilities.chat_type == 'channel':
        raise ValidationFailure('Calendar supports ordinary bot chats')
    if texts is None:
        texts = Texts()
    elif not isinstance(texts, Texts):
        raise InvalidType('Use Texts or None')
    weekdays = texts.weekdays()
    rows: list[list[InlineKeyboardButton]] = []
    if disabled_buttons:
        try:
            from aiogram.types import DisabledButton  # Bot API 10.3
        except ImportError:
            raise UnsupportedCapability('Disabled calendar cells need aiogram 3.31+ (Bot API 10.3)') from None
        rows.append([InlineKeyboardButton(text=label, disabled=DisabledButton()) for label in weekdays])
        for week in month.weeks:
            rows.append(
                [
                    InlineKeyboardButton(text=str(day.day), callback_data=callback_for(day))
                    if day is not None and month.allows(day)
                    else InlineKeyboardButton(text=str(day.day) if day else '·', disabled=DisabledButton())
                    for day in week
                ]
            )
    else:
        buttons = [
            InlineKeyboardButton(text=f'{weekdays[day.weekday()]} {day.day}', callback_data=callback_for(day))
            for day in sorted(month.allowed_dates)
        ]
        if buttons:
            rows.extend(inline_layout(buttons, KeyboardLayout((3,)), capabilities=capabilities).inline_keyboard)
    if navigation is not None:
        if not isinstance(navigation, tuple) or len(navigation) != 2:
            raise InvalidType('Use (previous_callback, next_callback)')
        rows.append(
            [
                InlineKeyboardButton(text=texts('calendar.previous_month'), callback_data=navigation[0]),
                InlineKeyboardButton(text=texts('calendar.next_month'), callback_data=navigation[1]),
            ]
        )
    return inline_keyboard(rows, chat_type=capabilities.chat_type) if rows else InlineKeyboardMarkup(inline_keyboard=[])


def time_slot_keyboard(
    slots: Sequence[TimeSlot],
    time_zone: str,
    callback_for: Callable[[TimeSlot], str],
    *,
    layout: KeyboardLayout = KeyboardLayout((1,)),
    capabilities: KeyboardCapabilities = KeyboardCapabilities(),
) -> InlineKeyboardMarkup:
    """Available intervals only; offset labels distinguish ambiguous local times."""
    if not callable(callback_for) or isinstance(slots, (str, bytes)):
        raise InvalidType('Use TimeSlot objects and a synchronous callback factory')
    if (
        not isinstance(capabilities, KeyboardCapabilities)
        or capabilities.business
        or capabilities.chat_type == 'channel'
    ):
        raise ValidationFailure('Time slots support ordinary bot chats')
    if not isinstance(layout, KeyboardLayout):
        raise InvalidType('Use KeyboardLayout')
    resolve_zone(time_zone)
    items = tuple(slots)
    if (
        len(items) > 100
        or any(not isinstance(slot, TimeSlot) for slot in items)
        or len({slot.key for slot in items}) != len(items)
    ):
        raise ValidationFailure('Use at most 100 uniquely keyed slots (component limit)')
    buttons = [
        InlineKeyboardButton(text=slot.label(time_zone), callback_data=callback_for(slot))
        for slot in items
        if slot.enabled
    ]
    return (
        inline_layout(buttons, layout, capabilities=capabilities)
        if buttons
        else InlineKeyboardMarkup(inline_keyboard=[])
    )
