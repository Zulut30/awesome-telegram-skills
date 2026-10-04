"""Explicit row layouts using native aiogram button models and context checks."""
from __future__ import annotations

from typing import Literal, Sequence
from urllib.parse import urlsplit

from aiogram.types import (ForceReply, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove)

ChatType = Literal['private', 'group', 'supergroup', 'channel']
INLINE_ACTIONS = ('url', 'callback_data', 'web_app', 'login_url', 'switch_inline_query',
                  'switch_inline_query_current_chat', 'switch_inline_query_chosen_chat',
                  'copy_text', 'callback_game', 'pay', 'disabled')
REPLY_ACTIONS = ('request_users', 'request_chat', 'request_managed_bot', 'request_contact',
                 'request_location', 'request_poll', 'web_app')


def _context(chat_type: ChatType, business: bool) -> None:
    if chat_type not in {'private', 'group', 'supergroup', 'channel'} or type(business) is not bool:
        raise ValueError('Specify a supported chat_type and a bool business flag')


def _text(text: str, *, limit: int | None = None) -> None:
    try:
        valid = isinstance(text, str) and bool(text.strip())
        if valid:
            length = len(text.encode('utf-16-le')) // 2
            valid = limit is None or length <= limit
    except UnicodeError:
        valid = False
    if not valid:
        raise ValueError('Use nonempty valid text within the requested limit')


def _rows(rows: Sequence[Sequence[object]]) -> list[list[object]]:
    if isinstance(rows, (str, bytes)):
        raise TypeError('Use a sequence of button rows')
    result = []
    for row in rows:
        if isinstance(row, (str, bytes)):
            raise TypeError('Wrap each row in a list or tuple')
        copied = list(row)
        if not 1 <= len(copied) <= 8:
            raise ValueError('Use 1..8 buttons per row (component limit)')
        result.append(copied)
    if not result or sum(map(len, result)) > 100:
        raise ValueError('Use 1..100 buttons (component limit)')
    return result


def _presentation(button: InlineKeyboardButton | KeyboardButton, verified: bool) -> None:
    if button.model_extra:
        raise ValueError('Unknown button fields in the installed SDK')
    _text(button.text)
    if type(verified) is not bool:
        raise ValueError('Emoji entitlement flag must be bool')
    if button.style not in {None, 'primary', 'success', 'danger'}:
        raise ValueError('Choose primary, success, danger or the default style')
    if button.icon_custom_emoji_id is not None:
        if not button.icon_custom_emoji_id.isascii() or not button.icon_custom_emoji_id.isdecimal():
            raise ValueError('Custom emoji ID must be a decimal string')
        if not verified:
            button.icon_custom_emoji_id = None


def _https(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use a valid HTTPS app/login URL without embedded credentials')


def inline_keyboard(rows: Sequence[Sequence[InlineKeyboardButton]], *,
                    chat_type: ChatType = 'private', business: bool = False, invoice: bool = False,
                    force_reply: bool = False, emoji_entitlement_verified: bool = False) -> InlineKeyboardMarkup:
    """Snapshot explicit rows; caller supplies actual context and verified capability.

    URL/copy/switch-inline/disabled buttons do not emit callback_query. Login,
    invoice and object authorization remain with the host application.
    """
    _context(chat_type, business)
    if type(invoice) is not bool or type(force_reply) is not bool:
        raise ValueError('Invoice and force_reply flags must be bool')
    result = []
    for row_index, row in enumerate(_rows(rows)):
        buttons = []
        for column, source in enumerate(row):
            if not isinstance(source, InlineKeyboardButton):
                raise TypeError('Use aiogram InlineKeyboardButton models')
            button = source.model_copy(deep=True)
            _presentation(button, emoji_entitlement_verified)
            actions = [name for name in INLINE_ACTIONS if getattr(button, name) is not None]
            if len(actions) != 1:
                raise ValueError('Inline button must have exactly one action')
            action = actions[0]
            if action == 'pay' and button.pay is not True:
                raise ValueError('Pay action must be True')
            if action in {'pay', 'callback_game'} and (row_index, column) != (0, 0):
                raise ValueError('Pay/game button must be first in the first row')
            if action == 'pay' and not invoice:
                raise ValueError('Pay button is only valid on an invoice')
            if action == 'callback_data':
                if button.callback_data is None:
                    raise ValueError('Missing callback data')
                try: length = len(button.callback_data.encode('utf-8'))
                except UnicodeError: length = 0
                if not 1 <= length <= 64:
                    raise ValueError('Callback data must contain 1..64 UTF-8 bytes')
            if action == 'copy_text':
                if button.copy_text is None:
                    raise ValueError('Missing copy text action')
                _text(button.copy_text.text, limit=256)
            if action == 'url':
                parsed = urlsplit(button.url)
                if parsed.scheme not in {'http', 'https', 'tg'} or (parsed.scheme != 'tg' and not parsed.hostname):
                    raise ValueError('Use an HTTP(S) or tg:// button URL')
            if action == 'web_app':
                if chat_type != 'private' or business:
                    raise ValueError('Web App button requires an ordinary private bot chat')
                if button.web_app is None:
                    raise ValueError('Missing Web App action')
                _https(button.web_app.url)
            if action == 'login_url':
                if button.login_url is None:
                    raise ValueError('Missing login action')
                _https(button.login_url.url)
            if action in {'switch_inline_query', 'switch_inline_query_current_chat', 'switch_inline_query_chosen_chat'}:
                if business or (action == 'switch_inline_query_current_chat' and chat_type == 'channel'):
                    raise ValueError('Inline switch action is unavailable in this context')
            buttons.append(button)
        result.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=result, force_reply=True if force_reply else None)


def reply_keyboard(rows: Sequence[Sequence[str | KeyboardButton]], *,
                   chat_type: ChatType = 'private', business: bool = False,
                   resize: bool = True, one_time: bool = False, persistent: bool = False,
                   placeholder: str | None = None, selective: bool = False, force_reply: bool = False,
                   emoji_entitlement_verified: bool = False) -> ReplyKeyboardMarkup:
    """Reply buttons send text or requested service data, never callback_query."""
    _context(chat_type, business)
    if chat_type == 'channel' or business:
        raise ValueError('Reply keyboard is unavailable in channels/Business messages')
    if any(type(flag) is not bool for flag in (resize, one_time, persistent, selective, force_reply)):
        raise ValueError('Keyboard flags must be bool')
    if placeholder is not None: _text(placeholder, limit=64)
    result, request_ids = [], set()
    for row in _rows(rows):
        buttons = []
        for source in row:
            if isinstance(source, str): button = KeyboardButton(text=source)
            elif isinstance(source, KeyboardButton): button = source.model_copy(deep=True)
            else: raise TypeError('Use text or aiogram KeyboardButton models')
            _presentation(button, emoji_entitlement_verified)
            if button.request_user is not None:
                raise ValueError('Use modern request_users instead of deprecated request_user')
            actions = [name for name in REPLY_ACTIONS if getattr(button, name) not in (None, False)]
            if len(actions) > 1:
                raise ValueError('Reply button must have at most one request action')
            if actions and chat_type != 'private':
                raise ValueError('Request buttons require a private chat')
            for name in ('request_users', 'request_chat', 'request_managed_bot'):
                request = getattr(button, name)
                if request is not None:
                    if not -(2 ** 31) <= request.request_id < 2 ** 31 or request.request_id in request_ids:
                        raise ValueError('Request IDs must be unique signed 32-bit integers')
                    request_ids.add(request.request_id)
            if button.web_app is not None: _https(button.web_app.url)
            buttons.append(button)
        result.append(buttons)
    return ReplyKeyboardMarkup(keyboard=result, resize_keyboard=resize, one_time_keyboard=one_time,
        is_persistent=persistent, input_field_placeholder=placeholder, selective=selective,
        force_reply=True if force_reply else None)


def input_prompt(placeholder: str | None = None, *, selective: bool = False) -> ForceReply:
    """Request the client's reply UI; the host binds/validates the actual response."""
    if placeholder is not None: _text(placeholder, limit=64)
    if type(selective) is not bool: raise ValueError('Selective flag must be bool')
    return ForceReply(force_reply=True, input_field_placeholder=placeholder, selective=selective)


def remove_keyboard(*, selective: bool = False) -> ReplyKeyboardRemove:
    if type(selective) is not bool: raise ValueError('Selective flag must be bool')
    return ReplyKeyboardRemove(remove_keyboard=True, selective=selective)
