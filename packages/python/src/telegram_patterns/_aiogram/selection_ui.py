"""Optional selection markup/router; host owns menus, effects and SDK resources."""

from __future__ import annotations

import asyncio
import weakref
from typing import Awaitable, Callable, Literal

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .._shared import SELECTION_PREFIX
from ..errors import ConflictFailure, InvalidCompletion, InvalidType, UnknownOutcome, ValidationFailure
from ..selection import SelectionContext, SelectionMenu, SelectionResult, SelectionSpec, SelectionState
from .common import check_text
from .keyboard_layouts import KeyboardCapabilities, KeyboardLayout, inline_layout


def selection_keyboard(
    state: SelectionState,
    *,
    layout: KeyboardLayout = KeyboardLayout((2,)),
    capabilities: KeyboardCapabilities = KeyboardCapabilities(),
) -> InlineKeyboardMarkup:
    """Render a server snapshot; all callback commands still require menu.apply."""
    if not isinstance(state, SelectionState):
        raise InvalidType('Use the server SelectionState')
    if (
        not isinstance(capabilities, KeyboardCapabilities)
        or capabilities.business
        or capabilities.chat_type == 'channel'
    ):
        raise ValidationFailure('Selection supports ordinary private/group/supergroup bot messages')
    if state.phase in {'confirmed', 'cancelled'}:
        return InlineKeyboardMarkup(inline_keyboard=[])

    def button(
        text: str, action: str, style: Literal['primary', 'success', 'danger'] | None = None
    ) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, callback_data=state.callback(action), style=style)

    rows = []
    if state.phase == 'confirming':
        if state.confirmation_id is None:
            raise ValidationFailure('Confirming view needs its server confirmation ID')
        rows = [
            [button('Да: ' + state.spec.confirm_text, 'y:' + state.confirmation_id, 'danger')],
            [button('Изменить выбор', 'back'), button('Отмена', 'cancel')],
        ]
    else:
        choices = [
            button(
                ('✓ ' if o.key in state.selected else '□ ') + o.label,
                's:' + o.key,
                'success' if o.key in state.selected else None,
            )
            for o in state.spec.options
            if o.enabled and (state.filter_key == 'all' or state.filter_key in o.filters)
        ]
        if choices:
            rows.extend(inline_layout(choices, layout, capabilities=capabilities).inline_keyboard)
        rows.extend(
            [[button(('✓ ' if value else '□ ') + state.spec.toggles[key], 't:' + key)] for key, value in state.toggles]
        )
        rows.append([button('−1', 'q:dec'), button(str(state.quantity) + ' ↻', 'refresh'), button('+1', 'q:inc')])
        filters = [
            button(('✓ ' if key == state.filter_key else '') + label, 'f:' + key)
            for key, label in state.spec.filters.items()
        ]
        rows.extend(inline_layout(filters, KeyboardLayout((2,)), capabilities=capabilities).inline_keyboard)
        rows.append([button(state.spec.confirm_text, 'ask', 'danger'), button('Отмена', 'cancel')])
    buttons = [b for row in rows for b in row]
    return inline_layout(buttons, KeyboardLayout(tuple(len(row) for row in rows)), capabilities=capabilities)


def selection_router(
    resolve: SelectionMenu | Callable[[CallbackQuery], SelectionMenu | None],
    *,
    prefix: str | None = None,
    capabilities: KeyboardCapabilities = KeyboardCapabilities(),
    load_spec: Callable[[CallbackQuery, SelectionMenu], Awaitable[SelectionSpec]] | None = None,
    on_result: Callable[[CallbackQuery, SelectionResult], Awaitable[None]] | None = None,
    render: Callable[[SelectionState], tuple[str, InlineKeyboardMarkup]] | None = None,
) -> Router:
    """ACK first; recheck after host load; commit local intent before host hook/edit.

    on_result runs before rendering. Its business transaction must recheck ACL,
    resource_version and operation_id itself. Hook/edit errors and cancellation
    propagate with the draft already committed: never roll back or auto retry.
    A single router/event loop serializes a menu's display. Host owns registry,
    expiry/removal, Bot/session/Dispatcher and any durable operation reconciliation.
    Optional synchronous render(state) composes calendar/custom views after the
    host hook. It cannot change the server guards; invalid output retains intent.
    """
    if prefix is None:
        prefix = resolve.state.prefix if isinstance(resolve, SelectionMenu) else 'sel:'
    if not isinstance(prefix, str) or not SELECTION_PREFIX.fullmatch(prefix):
        raise ValidationFailure('Use 1..8 ASCII prefix characters followed by colon')
    if not isinstance(resolve, SelectionMenu) and not callable(resolve):
        raise InvalidType('Use a SelectionMenu or synchronous menu resolver')
    if isinstance(resolve, SelectionMenu) and resolve.state.prefix != prefix:
        raise ValidationFailure('Router prefix must match its menu prefix')
    if any(hook is not None and not callable(hook) for hook in (load_spec, on_result)):
        raise InvalidType('Use async host hooks')
    if render is not None and not callable(render):
        raise InvalidType('Use a synchronous display renderer')
    if (
        not isinstance(capabilities, KeyboardCapabilities)
        or capabilities.business
        or capabilities.chat_type == 'channel'
    ):
        raise ValidationFailure('Use ordinary private/group/supergroup capabilities')
    router = Router()
    locks: weakref.WeakKeyDictionary[SelectionMenu, asyncio.Lock] = weakref.WeakKeyDictionary()
    bound_loop: asyncio.AbstractEventLoop | None = None

    @router.callback_query(F.data.startswith(prefix))
    async def handle(query: CallbackQuery) -> None:
        nonlocal bound_loop
        loop = asyncio.get_running_loop()
        if bound_loop is None:
            bound_loop = loop
        elif loop is not bound_loop:
            raise ConflictFailure('Use one event loop per selection router')
        bot = query.bot
        if bot is None:
            raise InvalidType('Bind CallbackQuery to Bot')
        await query.answer()
        message = query.message
        if (
            not isinstance(message, Message)
            or message.date.timestamp() <= 0
            or query.inline_message_id is not None
            or message.business_connection_id is not None
            or message.chat.type != capabilities.chat_type
            or message.from_user is None
            or not message.from_user.is_bot
            or message.from_user.id != bot.id
        ):
            if on_result is not None:
                await on_result(query, SelectionResult('stale', 'Это сообщение не поддерживает такой выбор.'))
            return
        menu = resolve if isinstance(resolve, SelectionMenu) else resolve(query)
        if menu is None:
            if on_result is not None:
                await on_result(query, SelectionResult('stale', 'Выбор уже закрыт.'))
            return
        if not isinstance(menu, SelectionMenu) or menu.state.prefix != prefix:
            raise InvalidType('Resolver must return a menu with the registered prefix or None')
        context = SelectionContext(
            bot.id, query.from_user.id, message.chat.id, message.message_id, message.message_thread_id
        )
        lock = locks.setdefault(menu, asyncio.Lock())
        async with lock:
            result = menu.check(query.data or '', context)
            if result is None:
                if load_spec is not None:
                    menu.replace_spec(await load_spec(query, menu))
                result = menu.apply(query.data or '', context)
            if on_result is not None:
                await on_result(query, result)
            if result.status not in {'accepted', 'confirming', 'confirmed', 'cancelled'}:
                return
            # Host hook may refresh rules; render the latest coherent snapshot.
            state = menu.state
            view = (
                render(state)
                if render is not None
                else (state.text(), selection_keyboard(state, capabilities=capabilities))
            )
            if not isinstance(view, tuple) or len(view) != 2 or not isinstance(view[1], InlineKeyboardMarkup):
                raise InvalidCompletion('Renderer must return (plain text, InlineKeyboardMarkup); intent retained')
            try:
                check_text(view[0], limit=4096)
            except ValidationFailure:
                raise InvalidCompletion('Renderer text is invalid; intent retained') from None
            edited = await bot.edit_message_text(
                view[0], chat_id=context.chat_id, message_id=context.message_id, parse_mode=None, reply_markup=view[1]
            )
            if (
                not isinstance(edited, Message)
                or edited.message_id != context.message_id
                or edited.chat.id != context.chat_id
                or edited.message_thread_id != context.message_thread_id
                or edited.date.timestamp() <= 0
                or edited.from_user is None
                or edited.from_user.id != bot.id
                or not edited.from_user.is_bot
                or edited.business_connection_id is not None
                or edited.chat.type != capabilities.chat_type
            ):
                raise UnknownOutcome('Selection display response was not confirmed; server draft retained')

    return router
