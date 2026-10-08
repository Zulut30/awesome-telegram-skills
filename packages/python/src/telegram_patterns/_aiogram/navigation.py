"""Owner-bound, revisioned screens in one bot message (single-process state)."""

from __future__ import annotations

import asyncio
import math
import re
import secrets
import time
from dataclasses import dataclass, field, replace
from typing import Awaitable, Callable, Literal, Sequence

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..errors import ConflictFailure, InvalidType, UnknownOutcome, ValidationFailure
from ..texts import Texts
from .common import unique_items
from .keyboard_layouts import KeyboardCapabilities, KeyboardLayout, inline_layout
from .keyboards import ActionButton

_KEY = re.compile(r'[A-Za-z0-9_-]{1,24}')
_RESERVED = {'_back', '_refresh'}
_MAX_REVISION = 9_999_999_999


def _key(value: str) -> None:
    if not isinstance(value, str) or not _KEY.fullmatch(value) or value in _RESERVED:
        raise ValidationFailure('Screen keys must be 1..24 ASCII letters/digits/_/-, excluding reserved keys')


def _text(value: str, maximum: int) -> None:
    try:
        valid = isinstance(value, str) and bool(value.strip()) and len(value.encode('utf-16-le')) // 2 <= maximum
    except UnicodeError:
        valid = False
    if not valid:
        raise ValidationFailure(f'Use nonempty plain text up to {maximum} UTF-16 units')


def _identity(bot_id: int, owner_id: int, chat_id: int, thread_id: int | None) -> None:
    if type(bot_id) is not int or bot_id <= 0 or type(owner_id) is not int or owner_id <= 0:
        raise ValidationFailure('Bot and owner IDs must be positive integers')
    if type(chat_id) is not int or chat_id == 0:
        raise ValidationFailure('Chat ID must be a nonzero integer')
    if thread_id is not None and (type(thread_id) is not int or thread_id <= 0):
        raise ValidationFailure('Thread ID must be a positive integer or None')


@dataclass(frozen=True, slots=True)
class NavigationScreen:
    """Plain-text screen; ActionButton.key points to another declared screen."""

    key: str
    text: str
    buttons: Sequence[ActionButton] = ()
    layout: KeyboardLayout = KeyboardLayout()

    def __post_init__(self) -> None:
        _key(self.key)
        _text(self.text, 4096)
        if isinstance(self.buttons, (str, bytes)) or not isinstance(self.buttons, Sequence):
            raise InvalidType('Use ActionButton sequences for screen links')
        buttons = unique_items(self.buttons, ActionButton)
        if len(buttons) > 98:
            raise ValidationFailure('Use up to 98 links (room for back and refresh; component limit)')
        for button in buttons:
            _key(button.key)
        if not isinstance(self.layout, KeyboardLayout):
            raise InvalidType('Use KeyboardLayout')
        object.__setattr__(self, 'buttons', buttons)


@dataclass(frozen=True, slots=True)
class NavigationState:
    """Immutable snapshot; expires_at is process monotonic time, not persistence."""

    session_id: str
    bot_id: int
    owner_id: int
    chat_id: int
    message_thread_id: int | None
    message_id: int | None
    screen: str
    history: tuple[str, ...]
    revision: int
    expires_at: float
    phase: Literal['opening', 'ready', 'unknown'] = 'ready'


@dataclass(frozen=True, slots=True)
class NavigationResult:
    """Safe feedback; denied/foreign scope never exposes another owner's state."""

    status: Literal['accepted', 'denied', 'stale', 'unavailable', 'unknown']
    text: str
    state: NavigationState | None = None


@dataclass(slots=True)
class _Entry:
    state: NavigationState
    issued_revision: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class MessageNavigation:
    """A bounded local menu, not a business FSM or a cross-worker store.

    open() is an explicit authenticated host action (e.g. /menu). Reopening an
    owned active scope edits its same message and resets history to the selected
    screen. It also recovers an uncertain edit. An uncertain initial send has
    no known message ID and is NEVER resent automatically; discard() requires
    the host's separate deliberate decision. The engine never owns Bot/session.
    """

    def __init__(
        self,
        screens: Sequence[NavigationScreen],
        *,
        prefix: str = 'nav:',
        capabilities: KeyboardCapabilities = KeyboardCapabilities(),
        ttl_seconds: float = 1800,
        max_sessions: int = 1000,
        max_history: int = 50,
        back_text: str | None = None,
        refresh_text: str | None = None,
        texts: Texts | None = None,
    ) -> None:
        """texts names the buttons and every NavigationResult text (Russian by default); back_text and
        refresh_text, when given, win over 'navigation.back' and 'navigation.refresh'."""
        if isinstance(screens, (str, bytes)) or not isinstance(screens, Sequence):
            raise InvalidType('Use NavigationScreen sequences')
        items = tuple(screens)
        if not 1 <= len(items) <= 100 or any(not isinstance(s, NavigationScreen) for s in items):
            raise ValidationFailure('Use 1..100 NavigationScreen items')
        self._screens = {s.key: s for s in items}
        if len(self._screens) != len(items):
            raise ValidationFailure('Screen keys must be unique')
        if any(b.key not in self._screens for s in items for b in s.buttons):
            raise ValidationFailure('Each link must target a declared screen')
        if not isinstance(prefix, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,8}:', prefix):
            raise ValidationFailure('Use a 1..8 ASCII letter/digit/_/- prefix followed by colon')
        if not isinstance(capabilities, KeyboardCapabilities):
            raise InvalidType('Use KeyboardCapabilities')
        if capabilities.business or capabilities.chat_type == 'channel':
            raise ValidationFailure('Navigation supports ordinary bot messages in private/group/supergroup')
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, (int, float))
            or not math.isfinite(ttl_seconds)
            or ttl_seconds <= 0
        ):
            raise ValidationFailure('TTL must be finite and positive')
        if type(max_sessions) is not int or not 1 <= max_sessions <= 100_000:
            raise ValidationFailure('Use max_sessions in 1..100000')
        if type(max_history) is not int or not 1 <= max_history <= 1000:
            raise ValidationFailure('Use max_history in 1..1000')
        if texts is None:
            texts = Texts()
        elif not isinstance(texts, Texts):
            raise InvalidType('Use Texts or None')
        back_text = texts('navigation.back') if back_text is None else back_text
        refresh_text = texts('navigation.refresh') if refresh_text is None else refresh_text
        _text(back_text, 64)
        _text(refresh_text, 64)
        self._texts = texts
        self._prefix, self._capabilities = prefix, capabilities
        self._ttl, self._capacity, self._history_limit = float(ttl_seconds), max_sessions, max_history
        self._back_text, self._refresh_text = back_text, refresh_text
        self._entries: dict[tuple[int, int, int, int | None], _Entry] = {}
        self._tokens: dict[str, _Entry] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pattern = re.compile(re.escape(prefix) + r'([0-9a-f]{16}):(0|[1-9][0-9]{0,9}):([A-Za-z0-9_-]{1,24})')
        # Validate native presentation before any send, including fallback.
        for screen in items:
            self._markup(screen, '0' * 16, 0, False)

    @property
    def prefix(self) -> str:
        return self._prefix

    def _event_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise ConflictFailure('Use one event loop per MessageNavigation instance')

    def _markup(self, screen: NavigationScreen, token: str, revision: int, back: bool) -> InlineKeyboardMarkup:
        def data(key: str) -> str:
            return f'{self.prefix}{token}:{revision}:{key}'

        buttons = [
            InlineKeyboardButton(
                text=b.text, callback_data=data(b.key), style=b.style, icon_custom_emoji_id=b.custom_emoji_id
            )
            for b in screen.buttons
        ]
        # Screen links keep the declared layout. Navigation controls have their own row.
        markup = (
            inline_layout(buttons, screen.layout, capabilities=self._capabilities)
            if buttons
            else InlineKeyboardMarkup(inline_keyboard=[])
        )
        controls = []
        if back:
            controls.append(InlineKeyboardButton(text=self._back_text, callback_data=data('_back')))
        controls.append(InlineKeyboardButton(text=self._refresh_text, callback_data=data('_refresh')))
        control_markup = inline_layout(controls, KeyboardLayout((2,)), capabilities=self._capabilities)
        markup.inline_keyboard.extend(control_markup.inline_keyboard)
        return markup

    def get_state(
        self, bot_id: int, owner_id: int, chat_id: int, *, message_thread_id: int | None = None
    ) -> NavigationState | None:
        """Host-side scoped snapshot; authenticate caller before exposing it."""
        _identity(bot_id, owner_id, chat_id, message_thread_id)
        entry = self._entries.get((bot_id, owner_id, chat_id, message_thread_id))
        return entry.state if entry is not None else None

    def _remove(self, scope: tuple[int, int, int, int | None], entry: _Entry) -> None:
        if self._entries.get(scope) is entry:
            del self._entries[scope]
            self._tokens.pop(entry.state.session_id, None)

    def _prune(self) -> None:
        now = time.monotonic()
        for scope, entry in tuple(self._entries.items()):
            # Unknown send/edit requires explicit recovery/reset, even after TTL.
            if not entry.lock.locked() and entry.state.phase == 'ready' and now >= entry.state.expires_at:
                self._remove(scope, entry)

    async def discard(self, bot_id: int, owner_id: int, chat_id: int, *, message_thread_id: int | None = None) -> bool:
        """Explicit host reset; waits for in-flight edit, no remote delete/send.

        Discarding an uncertain initial send allows a NEW future message. The
        host must make that choice explicitly; it can leave an orphan message.
        """
        self._event_loop()
        _identity(bot_id, owner_id, chat_id, message_thread_id)
        scope = (bot_id, owner_id, chat_id, message_thread_id)
        entry = self._entries.get(scope)
        if entry is None:
            return False
        async with entry.lock:
            if self._entries.get(scope) is not entry:
                return False
            self._remove(scope, entry)
            return True

    async def open(
        self, bot: Bot, owner_id: int, chat_id: int, *, screen: str | None = None, message_thread_id: int | None = None
    ) -> NavigationState:
        """First send or explicit reopen/recovery by the authenticated owner."""
        self._event_loop()
        _identity(bot.id, owner_id, chat_id, message_thread_id)
        key = next(iter(self._screens)) if screen is None else screen
        if not isinstance(key, str) or key not in self._screens:
            raise ValidationFailure('Unknown screen')
        scope = (bot.id, owner_id, chat_id, message_thread_id)
        self._prune()
        entry = self._entries.get(scope)
        created = entry is None
        if entry is None:
            if len(self._entries) >= self._capacity:
                raise ConflictFailure('Navigation capacity reached; expire or discard an owned menu')
            token = secrets.token_hex(8)
            while token in self._tokens:
                token = secrets.token_hex(8)
            entry = _Entry(
                NavigationState(
                    token,
                    bot.id,
                    owner_id,
                    chat_id,
                    message_thread_id,
                    None,
                    key,
                    (),
                    0,
                    time.monotonic() + self._ttl,
                    'opening',
                )
            )
            self._entries[scope] = entry
            self._tokens[token] = entry
        async with entry.lock:
            if self._entries.get(scope) is not entry:
                raise ConflictFailure('Menu was discarded; open again explicitly')
            if created:
                try:
                    sent = await bot.send_message(
                        chat_id,
                        self._screens[key].text,
                        parse_mode=None,
                        message_thread_id=message_thread_id,
                        reply_markup=self._markup(self._screens[key], entry.state.session_id, 0, False),
                    )
                    self._verify_message(sent, entry.state, initial=True)
                except TelegramBadRequest:
                    self._remove(scope, entry)
                    raise
                except BaseException:
                    entry.state = replace(entry.state, phase='unknown')
                    raise
                entry.state = replace(
                    entry.state, message_id=sent.message_id, phase='ready', expires_at=time.monotonic() + self._ttl
                )
                return entry.state
            if entry.state.message_id is None:
                raise UnknownOutcome('Initial message send is uncertain; no automatic resend')
            return await self._edit(bot, entry, key, ())

    def _verify_message(self, message: Message | bool, state: NavigationState, *, initial: bool = False) -> None:
        if (
            not isinstance(message, Message)
            or message.message_id <= 0
            or message.date.timestamp() <= 0
            or message.chat.id != state.chat_id
            or message.message_thread_id != state.message_thread_id
            or message.chat.type != self._capabilities.chat_type
        ):
            raise UnknownOutcome('Unexpected navigation response context')
        if not initial and message.message_id != state.message_id:
            raise UnknownOutcome('Unexpected navigation response target')
        if (
            message.from_user is None
            or not message.from_user.is_bot
            or message.from_user.id != state.bot_id
            or message.business_connection_id is not None
        ):
            raise UnknownOutcome('Unexpected navigation response sender')

    async def _edit(self, bot: Bot, entry: _Entry, key: str, history: tuple[str, ...]) -> NavigationState:
        if entry.issued_revision >= _MAX_REVISION:
            raise ConflictFailure('Navigation revision limit reached; explicitly discard and reopen')
        entry.issued_revision += 1  # Never reuse a revision whose markup may have reached Telegram.
        candidate = replace(entry.state, screen=key, history=history, revision=entry.issued_revision, phase='ready')
        try:
            edited = await bot.edit_message_text(
                self._screens[key].text,
                chat_id=candidate.chat_id,
                message_id=candidate.message_id,
                parse_mode=None,
                reply_markup=self._markup(self._screens[key], candidate.session_id, candidate.revision, bool(history)),
            )
            self._verify_message(edited, candidate)
        except TelegramBadRequest:
            # Explicit API rejection leaves the prior confirmed state, including unknown.
            raise
        except BaseException:
            entry.state = replace(entry.state, phase='unknown')
            raise
        entry.state = replace(candidate, expires_at=time.monotonic() + self._ttl)
        return entry.state

    def _check(self, bot: Bot, query: CallbackQuery, entry: _Entry, revision: int) -> NavigationResult | None:
        state = entry.state
        if query.from_user.id != state.owner_id:
            return NavigationResult('denied', self._texts('navigation.foreign'))
        message = query.message
        if (
            bot.id != state.bot_id
            or not isinstance(message, Message)
            or query.inline_message_id is not None
            or message.date.timestamp() == 0
            or message.chat.id != state.chat_id
            or message.message_thread_id != state.message_thread_id
            or message.message_id != state.message_id
            or message.business_connection_id is not None
            or message.from_user is None
            or not message.from_user.is_bot
            or message.from_user.id != state.bot_id
            or message.chat.type != self._capabilities.chat_type
        ):
            return NavigationResult('stale', self._texts('navigation.other_message'))
        if (
            self._tokens.get(state.session_id) is not entry
            or time.monotonic() >= state.expires_at
            or revision != state.revision
        ):
            return NavigationResult('stale', self._texts('navigation.stale'))
        if state.phase != 'ready':
            return NavigationResult('unknown', self._texts('navigation.recover'), state)
        return None

    async def handle(self, query: CallbackQuery) -> NavigationResult:
        """ACK before waiting for a menu lock/edit; checks all guards again inside."""
        self._event_loop()
        bot = query.bot
        if bot is None:
            raise InvalidType('Bind the native CallbackQuery to a Bot before handling')
        await query.answer()
        match = self._pattern.fullmatch(query.data or '')
        if match is None:
            return NavigationResult('stale', self._texts('navigation.invalid'))
        token, revision_text, target = match.groups()
        entry = self._tokens.get(token)
        if entry is None:
            return NavigationResult('stale', self._texts('navigation.closed'))
        revision = int(revision_text)
        refused = self._check(bot, query, entry, revision)
        if refused is not None:
            return refused
        async with entry.lock:
            refused = self._check(bot, query, entry, revision)
            if refused is not None:
                return refused
            state = entry.state
            history = state.history
            if target == '_back':
                if not history:
                    return NavigationResult('stale', self._texts('navigation.no_previous'), state)
                target, history = history[-1], history[:-1]
            elif target == '_refresh':
                target = state.screen
            elif target not in {b.key for b in self._screens[state.screen].buttons}:
                return NavigationResult('stale', self._texts('navigation.no_transition'), state)
            elif target != state.screen:
                if len(history) >= self._history_limit:
                    return NavigationResult('unavailable', self._texts('navigation.history_full'), state)
                history = (*history, state.screen)
            try:
                current = await self._edit(bot, entry, target, history)
            except asyncio.CancelledError:
                raise
            except TelegramBadRequest:
                return NavigationResult('unavailable', self._texts('navigation.edit_rejected'), entry.state)
            except ConflictFailure:
                return NavigationResult('unavailable', self._texts('navigation.unavailable'), entry.state)
            except Exception:
                return NavigationResult('unknown', self._texts('navigation.unconfirmed'), entry.state)
            return NavigationResult('accepted', self._texts('navigation.updated'), current)


def navigation_router(
    navigation: MessageNavigation,
    *,
    on_result: Callable[[CallbackQuery, NavigationResult], Awaitable[None]] | None = None,
) -> Router:
    """Attach to an existing Dispatcher; host chooses safe feedback/error hooks."""
    if not isinstance(navigation, MessageNavigation):
        raise InvalidType('Use MessageNavigation')
    if on_result is not None and not callable(on_result):
        raise InvalidType('Use an async result callback')
    router = Router()

    @router.callback_query(F.data.startswith(navigation.prefix))
    async def handle(query: CallbackQuery) -> None:
        result = await navigation.handle(query)
        if on_result is not None:
            await on_result(query, result)

    return router
