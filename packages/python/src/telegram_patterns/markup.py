"""Keyboards as Bot API JSON without an SDK: the same rules for aiogram, python-telegram-bot or a raw HTTP client.

Every builder returns a plain dict exactly as Telegram expects it in reply_markup. An SDK turns it into its own
object (aiogram: InlineKeyboardMarkup.model_validate, python-telegram-bot: telegram_patterns.ptb.ptb_markup).
The checks mirror telegram_patterns.aiogram.inline_keyboard/reply_keyboard: one action per inline button,
callback_data of 1..64 UTF-8 bytes, HTTPS Mini App URLs only in private chats, 1..8 buttons per row and at most
100 buttons, custom emoji icons only with a verified entitlement. Rights and callback authorization stay with the host.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from .errors import InvalidType, ValidationFailure
from .texts import Texts

ChatType = Literal['private', 'group', 'supergroup', 'channel']
ButtonStyle = Literal['primary', 'success', 'danger']
Button = dict[str, Any]
_CHATS = ('private', 'group', 'supergroup', 'channel')
_INLINE_ACTIONS = (
    'url',
    'callback_data',
    'web_app',
    'copy_text',
    'switch_inline_query',
    'switch_inline_query_current_chat',
    'disabled',
)


def _text(value: object, *, limit: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationFailure('Use nonempty text')
    try:
        length = len(value.encode('utf-16-le')) // 2
    except UnicodeError:
        raise ValidationFailure('Use valid Unicode text') from None
    if limit is not None and length > limit:
        raise ValidationFailure(f'Use at most {limit} characters')
    return value


def _flag(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise InvalidType(f'{name} must be bool')
    return value


def _presentation(button: Button, style: object, icon: object) -> None:
    if style is not None:
        if style not in ('primary', 'success', 'danger'):
            raise ValidationFailure('Choose primary, success, danger or the default style')
        button['style'] = style
    if icon is not None:
        if not isinstance(icon, str) or not icon.isascii() or not icon.isdecimal():
            raise ValidationFailure('Custom emoji ID must be a decimal string')
        button['icon_custom_emoji_id'] = icon


def _https(url: object) -> str:
    parsed = urlsplit(url) if isinstance(url, str) else None
    if parsed is None or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValidationFailure('Use a valid HTTPS app URL without embedded credentials')
    return str(url)


def inline_button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    web_app: str | None = None,
    copy_text: str | None = None,
    switch_inline_query: str | None = None,
    switch_inline_query_current_chat: str | None = None,
    disabled: bool = False,
    style: ButtonStyle | None = None,
    icon_custom_emoji_id: str | None = None,
) -> Button:
    """One inline button with exactly one action; web_app is the HTTPS URL of the Mini App."""
    button: Button = {'text': _text(text)}
    _presentation(button, style, icon_custom_emoji_id)
    actions = {
        'callback_data': callback_data,
        'url': url,
        'web_app': web_app,
        'copy_text': copy_text,
        'switch_inline_query': switch_inline_query,
        'switch_inline_query_current_chat': switch_inline_query_current_chat,
    }
    chosen = [name for name, value in actions.items() if value is not None] + (
        ['disabled'] if _flag(disabled, 'disabled') else []
    )
    if len(chosen) != 1:
        raise ValidationFailure('Inline button must have exactly one action')
    action = chosen[0]
    if action == 'callback_data':
        try:
            size = len(str(callback_data).encode('utf-8')) if isinstance(callback_data, str) else 0
        except UnicodeError:
            size = 0
        if not 1 <= size <= 64:
            raise ValidationFailure('Callback data must contain 1..64 UTF-8 bytes')
        button['callback_data'] = callback_data
    elif action == 'url':
        parsed = urlsplit(url) if isinstance(url, str) else None
        if (
            parsed is None
            or parsed.scheme not in ('http', 'https', 'tg')
            or (parsed.scheme != 'tg' and not parsed.hostname)
        ):
            raise ValidationFailure('Use an HTTP(S) or tg:// button URL')
        button['url'] = url
    elif action == 'web_app':
        button['web_app'] = {'url': _https(web_app)}
    elif action == 'copy_text':
        button['copy_text'] = {'text': _text(copy_text, limit=256)}
    elif action == 'disabled':
        button['disabled'] = {}  # Bot API 10.3 DisabledButton: shown, never pressed
    else:
        if not isinstance(actions[action], str):
            raise InvalidType('Inline query text must be a string')
        button[action] = actions[action]
    return button


def reply_button(
    text: str,
    *,
    request_contact: bool = False,
    request_location: bool = False,
    web_app: str | None = None,
    style: ButtonStyle | None = None,
    icon_custom_emoji_id: str | None = None,
) -> Button:
    """A reply keyboard button: plain text or one request (contact, location, Mini App)."""
    button: Button = {'text': _text(text)}
    _presentation(button, style, icon_custom_emoji_id)
    requests = [
        name
        for name, value in (
            ('request_contact', _flag(request_contact, 'request_contact')),
            ('request_location', _flag(request_location, 'request_location')),
            ('web_app', web_app is not None),
        )
        if value
    ]
    if len(requests) > 1:
        raise ValidationFailure('A reply button requests at most one thing')
    if requests == ['web_app']:
        button['web_app'] = {'url': _https(web_app)}
    elif requests:
        button[requests[0]] = True
    return button


def layout_rows(items: Sequence[Any], widths: Sequence[int] = (2,), *, repeat: bool = False) -> list[list[Any]]:
    """Rows from a flat list: widths 1..8 in order; repeat cycles them, otherwise the last width fills the tail."""
    if isinstance(items, (str, bytes)) or isinstance(widths, (str, bytes)):
        raise InvalidType('Use sequences of buttons and widths')
    values, sizes = list(items), tuple(widths)
    if not 1 <= len(values) <= 100:
        raise ValidationFailure('Use 1..100 buttons (component limit)')
    if not sizes or any(type(size) is not int or not 1 <= size <= 8 for size in sizes):
        raise ValidationFailure('Use widths in 1..8')
    _flag(repeat, 'repeat')
    rows, offset, index = [], 0, 0
    while offset < len(values):
        width = sizes[index % len(sizes) if repeat else min(index, len(sizes) - 1)]
        rows.append(values[offset : offset + width])
        offset, index = offset + width, index + 1
    return rows


def _rows(rows: Sequence[Sequence[Any]]) -> list[list[Any]]:
    if isinstance(rows, (str, bytes)):
        raise InvalidType('Use a sequence of button rows')
    result = []
    for row in rows:
        if isinstance(row, (str, bytes)):
            raise InvalidType('Wrap each row in a list or tuple')
        copied = list(row)
        if not 1 <= len(copied) <= 8:
            raise ValidationFailure('Use 1..8 buttons per row (component limit)')
        result.append(copied)
    if not result or sum(map(len, result)) > 100:
        raise ValidationFailure('Use 1..100 buttons (component limit)')
    return result


def _context(chat_type: object, business: object) -> None:
    if chat_type not in _CHATS:
        raise ValidationFailure('Specify a supported chat_type')
    _flag(business, 'business')


def _finish(button: Button, verified: bool) -> Button:
    copied = {key: (dict(value) if isinstance(value, dict) else value) for key, value in button.items()}
    if not verified:
        copied.pop('icon_custom_emoji_id', None)  # unverified premium icons fall back to the text
    return copied


def inline_markup(
    rows: Sequence[Sequence[Button]],
    *,
    chat_type: ChatType = 'private',
    business: bool = False,
    emoji_entitlement_verified: bool = False,
) -> dict[str, Any]:
    """InlineKeyboardMarkup JSON from rows of inline_button results, checked against the chat context."""
    _context(chat_type, business)
    verified = _flag(emoji_entitlement_verified, 'emoji_entitlement_verified')
    result = []
    for row in _rows(rows):
        buttons = []
        for button in row:
            if not isinstance(button, dict) or 'text' not in button:
                raise InvalidType('Use inline_button results')
            actions = [name for name in _INLINE_ACTIONS if name in button]
            if len(actions) != 1:
                raise ValidationFailure('Inline button must have exactly one action')
            if actions[0] == 'web_app' and (chat_type != 'private' or business):
                raise ValidationFailure('Web App button requires an ordinary private bot chat')
            if actions[0] in ('switch_inline_query', 'switch_inline_query_current_chat') and (
                business or (actions[0] == 'switch_inline_query_current_chat' and chat_type == 'channel')
            ):
                raise ValidationFailure('Inline switch action is unavailable in this context')
            buttons.append(_finish(button, verified))
        result.append(buttons)
    return {'inline_keyboard': result}


def reply_markup(
    rows: Sequence[Sequence[str | Button]],
    *,
    chat_type: ChatType = 'private',
    business: bool = False,
    resize: bool = True,
    one_time: bool = False,
    persistent: bool = False,
    placeholder: str | None = None,
    selective: bool = False,
    emoji_entitlement_verified: bool = False,
) -> dict[str, Any]:
    """ReplyKeyboardMarkup JSON; strings become text buttons. Requests and Mini Apps need a private chat."""
    _context(chat_type, business)
    verified = _flag(emoji_entitlement_verified, 'emoji_entitlement_verified')
    result = []
    for row in _rows(rows):
        buttons = []
        for button in row:
            if isinstance(button, str):
                button = reply_button(button)
            if not isinstance(button, dict) or 'text' not in button:
                raise InvalidType('Use strings or reply_button results')
            if any(name in button for name in ('request_contact', 'request_location', 'web_app')) and (
                chat_type != 'private' or business
            ):
                raise ValidationFailure('Contact, location and Mini App requests need an ordinary private chat')
            buttons.append(_finish(button, verified))
        result.append(buttons)
    markup: dict[str, Any] = {
        'keyboard': result,
        'is_persistent': _flag(persistent, 'persistent'),
        'resize_keyboard': _flag(resize, 'resize'),
        'one_time_keyboard': _flag(one_time, 'one_time'),
    }
    if placeholder is not None:
        markup['input_field_placeholder'] = _text(placeholder, limit=64)
    markup['selective'] = _flag(selective, 'selective')
    return markup


def force_reply_markup(placeholder: str | None = None, *, selective: bool = False) -> dict[str, Any]:
    """ForceReply JSON: the client opens a reply to the bot's message; the host checks reply_to_message."""
    markup: dict[str, Any] = {'force_reply': True}
    if placeholder is not None:
        markup['input_field_placeholder'] = _text(placeholder, limit=64)
    markup['selective'] = _flag(selective, 'selective')
    return markup


def remove_markup(*, selective: bool = False) -> dict[str, Any]:
    """ReplyKeyboardRemove JSON."""
    return {'remove_keyboard': True, 'selective': _flag(selective, 'selective')}


def _callback(prefix: str, key: str) -> str:
    if not isinstance(prefix, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+:', prefix):
        raise ValidationFailure("Use a bounded ASCII prefix ending in ':'")
    if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}', key):
        raise ValidationFailure('Use an opaque ASCII action key')
    if len((prefix + key).encode('utf-8')) > 64:
        raise ValidationFailure('Callback data exceeds 64 bytes')
    return prefix + key


@dataclass(frozen=True, slots=True)
class MarkupPage:
    """One page of a long menu: markup JSON and where the page is."""

    markup: dict[str, Any]
    page: int
    page_count: int
    total_items: int


def paginated_markup(
    items: Sequence[tuple[str, str]],
    *,
    page: int = 0,
    page_size: int = 6,
    columns: int = 2,
    action_prefix: str = 'act:',
    page_prefix: str = 'page:',
    style: ButtonStyle | None = None,
    texts: Texts | None = None,
) -> MarkupPage:
    """(text, key) items as pages of callback buttons with previous/next buttons; a page past the end shows the last.

    The same layout and callback data as telegram_patterns.aiogram.paginated_menu; texts names the navigation
    buttons ('page.previous', 'page.next'), Russian by default.
    """
    if texts is None:
        texts = Texts()
    elif not isinstance(texts, Texts):
        raise InvalidType('Use Texts or None')
    if action_prefix == page_prefix:
        raise ValidationFailure('Action and pagination prefixes must differ')
    if type(page) is not int or page < 0:
        raise ValidationFailure('Page must be a nonnegative integer')
    if type(page_size) is not int or not 1 <= page_size <= 98:
        raise ValidationFailure('Use page_size 1..98, leaving room for navigation')
    if type(columns) is not int or not 1 <= columns <= 8:
        raise ValidationFailure('Use 1..8 columns')
    _callback(page_prefix, '0')
    if isinstance(items, (str, bytes)):
        raise InvalidType('Use a sequence of (text, key) items')
    values = list(items)
    if any(not isinstance(item, tuple) or len(item) != 2 for item in values):
        raise InvalidType('Use (text, key) items')
    buttons = [inline_button(text, callback_data=_callback(action_prefix, key), style=style) for text, key in values]
    if len({key for _, key in values}) != len(values):
        raise ValidationFailure('Action keys must be unique within a menu')
    count = max(1, (len(buttons) + page_size - 1) // page_size)
    current = min(page, count - 1)
    shown = buttons[current * page_size : (current + 1) * page_size]
    rows = [shown[offset : offset + columns] for offset in range(0, len(shown), columns)]
    navigation = []
    if current > 0:
        navigation.append(inline_button(texts('page.previous'), callback_data=_callback(page_prefix, str(current - 1))))
    if current + 1 < count:
        navigation.append(inline_button(texts('page.next'), callback_data=_callback(page_prefix, str(current + 1))))
    if navigation:
        rows.append(navigation)
    return MarkupPage({'inline_keyboard': rows}, current, count, len(buttons))


def markup_page_number(data: str | None, *, prefix: str = 'page:') -> int | None:
    """The page of a canonical pagination callback, or None for anything else (untrusted input)."""
    _callback(prefix, '0')
    if not isinstance(data, str) or not data.startswith(prefix):
        return None
    key = data[len(prefix) :]
    if not re.fullmatch(r'0|[1-9][0-9]{0,47}', key) or len(data) > 64:  # ASCII: characters are bytes
        return None
    return int(key)
