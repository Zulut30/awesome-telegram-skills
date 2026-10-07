"""Bounded shareable inline search, context-bound cursors and explicit cache policy."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import math
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Literal, Sequence, TypeAlias, cast

from aiogram import Bot, Router
from aiogram.methods import AnswerInlineQuery
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, MessageEntity

from .errors import ConflictFailure, InvalidCompletion, InvalidType, PermissionDenied, ValidationFailure
from .message_text import FormattedText, utf16_length

InlineChatType: TypeAlias = Literal['sender', 'private', 'group', 'supergroup', 'channel'] | None
InlineAuthorizer: TypeAlias = Callable[[int, 'InlineItem'], Awaitable[bool]]
InlineSearchProvider: TypeAlias = Callable[[InlineQuery], Awaitable['InlineSearch']]
_Context: TypeAlias = tuple[int, int, str, str, InlineChatType]
_CHAT_TYPES = ('sender', 'private', 'group', 'supergroup', 'channel', None)

__all__ = [
    'InlineChatType',
    'InlineAuthorizer',
    'InlineSearchProvider',
    'InlineCachePolicy',
    'InlineItem',
    'InlinePage',
    'InlineSearch',
    'inline_articles',
    'inline_query_router',
]


def _text(value: str, maximum: int, *, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise InvalidType('Inline text must be str')
    try:
        utf16_length(value)
    except ValueError:
        raise ValidationFailure('Inline text contains invalid Unicode') from None
    if not (0 if empty else 1) <= len(value) <= maximum:
        raise ValidationFailure('Inline text exceeds the declared character bound')
    return value


def _positive(value: int) -> None:
    if type(value) is not int or not 1 <= value < 2**52:
        raise ValidationFailure('Expected a positive 52-bit ID')


def _integer(value: int, low: int, high: int) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValidationFailure('Expected a bounded integer')


def _bool(value: bool) -> None:
    if type(value) is not bool:
        raise InvalidType('Expected bool')


def _query(value: InlineQuery, bot_id: int) -> _Context:
    if not isinstance(value, InlineQuery):
        raise InvalidType('Expected InlineQuery')
    _positive(bot_id)
    _positive(value.from_user.id)
    _text(value.id, 256)
    if value.chat_type not in _CHAT_TYPES:
        raise ValidationFailure('Unsupported inline chat type')
    return (
        bot_id,
        value.from_user.id,
        value.id,
        _text(value.query, 256, empty=True).strip().casefold(),
        cast(InlineChatType, value.chat_type),
    )


def _time(value: datetime | None) -> int:
    value = datetime.now(timezone.utc) if value is None else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationFailure('Cursor time must be timezone-aware')
    result = int(value.timestamp())
    _integer(result, 0, 2**32 - 86401)
    return result


def _entities(value: FormattedText, entitlement: bool) -> list[MessageEntity]:
    _bool(entitlement)
    return [
        MessageEntity.model_validate(entity.as_dict())
        for entity in value.entities
        if entity.kind != 'custom_emoji' or entitlement
    ]


@dataclass(frozen=True, slots=True)
class InlineCachePolicy:
    cache_time: int = 0
    is_personal: bool = True

    def __post_init__(self) -> None:
        _integer(self.cache_time, 0, 86400)  # Local policy, not a Telegram maximum.
        _bool(self.is_personal)


@dataclass(frozen=True, slots=True)
class InlineItem:
    id: str
    title: str = field(repr=False)
    content: FormattedText | str = field(repr=False)
    description: str = field(default='', repr=False)
    shareable: bool = False

    def __post_init__(self) -> None:
        _text(self.id, 64)
        if len(self.id.encode()) > 64:
            raise ValidationFailure('Inline result ID exceeds 64 bytes')
        _text(self.title, 256)  # Local display bound.
        _text(self.description, 512, empty=True)
        _bool(self.shareable)
        content = FormattedText(self.content) if isinstance(self.content, str) else self.content
        if not isinstance(content, FormattedText):
            raise InvalidType('Inline content must be literal text or FormattedText')
        _text(content.text, 4096)
        if len(content.entities) > 100:
            raise ValidationFailure('Inline content exceeds the local entity bound')
        object.__setattr__(self, 'content', content)


@dataclass(frozen=True, slots=True)
class InlinePage:
    items: tuple[InlineItem, ...] = field(repr=False)
    next_offset: str
    cache: InlineCachePolicy
    _context: _Context = field(repr=False)

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if len(items) > 50 or not all(isinstance(item, InlineItem) and item.shareable for item in items):
            raise ValidationFailure('Inline page accepts at most 50 explicitly shareable items')
        if len({item.id for item in items}) != len(items):
            raise ValidationFailure('Inline result IDs must be unique')
        _text(self.next_offset, 64, empty=True)
        if len(self.next_offset.encode()) > 64:
            raise ValidationFailure('Inline offset exceeds 64 bytes')
        if not isinstance(self.cache, InlineCachePolicy):
            raise InvalidType('Expected InlineCachePolicy')
        object.__setattr__(self, 'items', items)

    def answer_request(
        self, query: InlineQuery, *, bot_id: int, custom_emoji_entitlement_verified: bool = False
    ) -> AnswerInlineQuery:
        if _query(query, bot_id) != self._context:
            raise PermissionDenied('Inline page belongs to a different query context')
        return AnswerInlineQuery(
            inline_query_id=query.id,
            results=[
                item
                for item in inline_articles(self, custom_emoji_entitlement_verified=custom_emoji_entitlement_verified)
            ],
            next_offset=self.next_offset,
            cache_time=self.cache.cache_time,
            is_personal=self.cache.is_personal,
        )


def inline_articles(
    page: InlinePage, *, custom_emoji_entitlement_verified: bool = False
) -> list[InlineQueryResultArticle]:
    """Fresh native models with literal text; server cache never grants data privacy."""
    if not isinstance(page, InlinePage):
        raise InvalidType('Expected InlinePage')
    _bool(custom_emoji_entitlement_verified)
    results = []
    for item in page.items:
        assert isinstance(item.content, FormattedText)
        results.append(
            InlineQueryResultArticle(
                id=item.id,
                title=item.title,
                description=item.description or None,
                input_message_content=InputTextMessageContent(
                    message_text=item.content.text,
                    parse_mode=None,
                    entities=_entities(item.content, custom_emoji_entitlement_verified),
                ),
            )
        )
    return results


class InlineSearch:
    """Immutable bounded catalog snapshot; host persists/rotates its own cursor secret."""

    __slots__ = (
        '_items',
        '_secret',
        '_revision',
        '_fingerprint',
        '_page_size',
        '_cursor_ttl',
        '_cache',
        '_public_catalog',
        '_allowed_chat_types',
    )

    def __init__(
        self,
        items: Sequence[InlineItem],
        *,
        secret: bytes,
        revision: str,
        page_size: int = 20,
        cursor_ttl: int = 300,
        cache: InlineCachePolicy = InlineCachePolicy(),
        public_catalog: bool = False,
        allowed_chat_types: Sequence[InlineChatType] | None = None,
    ) -> None:
        if isinstance(items, (str, bytes)) or not isinstance(items, Sequence):
            raise InvalidType('Expected a bounded sequence of InlineItem')
        records = tuple(items)
        if len(records) > 10000 or not all(isinstance(item, InlineItem) for item in records):
            raise ValidationFailure('Inline catalog exceeds the local bound or contains invalid items')
        if len({item.id for item in records}) != len(records):
            raise ValidationFailure('Inline result IDs must be unique')
        if not isinstance(secret, bytes) or not 32 <= len(secret) <= 128:
            raise ValidationFailure('Supply a host-owned cursor secret of 32..128 bytes')
        _text(revision, 128)
        _integer(page_size, 1, 50)
        _integer(cursor_ttl, 1, 86400)
        _bool(public_catalog)
        if not isinstance(cache, InlineCachePolicy):
            raise InvalidType('Expected InlineCachePolicy')
        if not cache.is_personal and not public_catalog:
            raise ValidationFailure('Shared server cache requires an explicitly public catalog')
        if cache.cache_time > cursor_ttl:
            raise ValidationFailure('Cache lifetime must not exceed cursor lifetime')
        if allowed_chat_types is not None and (
            isinstance(allowed_chat_types, (str, bytes)) or not isinstance(allowed_chat_types, Sequence)
        ):
            raise InvalidType('Expected a sequence of inline chat types')
        contexts = (
            tuple(allowed_chat_types)
            if allowed_chat_types is not None
            else (_CHAT_TYPES if public_catalog else ('sender',))
        )
        if (
            not contexts
            or any(context not in _CHAT_TYPES for context in contexts)
            or len(set(contexts)) != len(contexts)
        ):
            raise ValidationFailure('Invalid or repeated inline chat contexts')
        if not cache.is_personal and set(contexts) != set(_CHAT_TYPES):
            raise ValidationFailure('Shared Telegram cache requires a public catalog allowed in every inline context')
        fingerprint = []
        for item in records:
            assert isinstance(item.content, FormattedText)
            fingerprint.append(
                [
                    item.id,
                    item.title,
                    item.description,
                    item.content.text,
                    [entity.as_dict() for entity in item.content.entities],
                    item.shareable,
                ]
            )
        self._items, self._secret, self._revision = records, secret, revision
        self._fingerprint = hashlib.sha256(
            json.dumps(fingerprint, ensure_ascii=False, separators=(',', ':')).encode()
        ).hexdigest()
        self._page_size, self._cursor_ttl, self._cache = page_size, cursor_ttl, cache
        self._public_catalog, self._allowed_chat_types = public_catalog, contexts

    @property
    def items(self) -> tuple[InlineItem, ...]:
        return self._items

    @property
    def revision(self) -> str:
        return self._revision

    def _mac(self, payload: bytes, context: _Context, permission_revision: str) -> bytes:
        bot_id, actor_id, _, query, chat_type = context
        # Telegram may replay a shared cached answer, including its cursor, to
        # another actor/context. Only a fully public catalog can omit this scope.
        actor_scope = actor_id if self._cache.is_personal else None
        chat_scope = chat_type if self._cache.is_personal else None
        scope = json.dumps(
            [
                bot_id,
                actor_scope,
                query,
                chat_scope,
                self._revision,
                self._fingerprint,
                permission_revision,
                self._page_size,
            ],
            ensure_ascii=False,
            separators=(',', ':'),
        ).encode()
        return hmac.new(self._secret, b'telegram-inline-v1\0' + payload + b'\0' + scope, hashlib.sha256).digest()[:16]

    def _seal(self, position: int, expires: int, context: _Context, revision: str) -> str:
        payload = struct.pack('>BII', 1, position, expires)
        return base64.urlsafe_b64encode(payload + self._mac(payload, context, revision)).decode().rstrip('=')

    def _open(self, token: str, now: int, context: _Context, revision: str) -> tuple[int, int]:
        try:
            if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{34}', token):
                raise ValueError
            raw = base64.urlsafe_b64decode(token + '==')
            payload, signature = raw[:9], raw[9:]
            version, position, expires = struct.unpack('>BII', payload)
            if (
                version != 1
                or position >= len(self._items)
                or now >= expires
                or base64.urlsafe_b64encode(raw).decode().rstrip('=') != token
                or not hmac.compare_digest(signature, self._mac(payload, context, revision))
            ):
                raise ValueError
            return position, expires
        except (ValueError, struct.error):
            raise ConflictFailure('Inline cursor is invalid, expired or belongs to a different context') from None

    async def page(
        self,
        query: InlineQuery,
        *,
        bot_id: int,
        authorize: InlineAuthorizer | None = None,
        permission_revision: str = '0',
        now: datetime | None = None,
    ) -> InlinePage:
        context = _query(query, bot_id)
        _text(permission_revision, 128)
        if context[-1] not in self._allowed_chat_types:
            raise PermissionDenied('Inline launch context is not allowed')
        if self._public_catalog and authorize is not None:
            raise ValidationFailure('Public cache must not use user-dependent authorization')
        if not self._cache.is_personal and permission_revision != '0':
            raise ValidationFailure('Shared public cache uses catalog revision, never user permission revision')
        if not self._public_catalog and not callable(authorize):
            raise PermissionDenied('Personal inline search requires current host authorization')
        clock = _time(now)
        start, expires = (
            self._open(query.offset, clock, context, permission_revision)
            if query.offset
            else (0, clock + self._cursor_ttl)
        )
        chosen: list[InlineItem] = []
        next_offset = ''
        for position in range(start, len(self._items)):
            item = self._items[position]
            assert isinstance(item.content, FormattedText)
            if (
                not item.shareable
                or context[3] not in (item.title + ' ' + item.description + ' ' + item.content.text).casefold()
            ):
                continue
            if authorize is not None and await authorize(context[1], item) is not True:
                continue
            if len(chosen) == self._page_size:
                next_offset = self._seal(position, expires, context, permission_revision)
                break
            chosen.append(item)
        return InlinePage(tuple(chosen), next_offset, self._cache, context)


def inline_query_router(
    search: InlineSearch | InlineSearchProvider,
    *,
    authorize: InlineAuthorizer | None = None,
    permission_revision: Callable[[int], Awaitable[str]] | None = None,
    search_timeout: float = 2.0,
    custom_emoji_entitlement_verified: bool = False,
) -> Router:
    """Attach to host Dispatcher; timeout covers provider/ACL, never retries native answer."""
    if not isinstance(search, InlineSearch) and not callable(search):
        raise InvalidType('Expected InlineSearch or an async host provider')
    if authorize is not None and not callable(authorize):
        raise InvalidType('Expected async inline authorizer')
    if permission_revision is not None and not callable(permission_revision):
        raise InvalidType('Expected async permission revision provider')
    if type(search_timeout) not in (int, float) or not math.isfinite(search_timeout) or not 0 < search_timeout <= 60:
        raise ValidationFailure('Search timeout must be finite and within 60 seconds')
    _bool(custom_emoji_entitlement_verified)
    router = Router(name='pattern-inline-search')

    @router.inline_query()
    async def handle(query: InlineQuery, bot: Bot) -> None:
        context = _query(query, bot.id)
        try:
            async with asyncio.timeout(search_timeout):
                catalog = search if isinstance(search, InlineSearch) else await search(query)
                if not isinstance(catalog, InlineSearch):
                    raise InvalidType('Inline provider returned an invalid catalog')
                if not catalog._cache.is_personal and permission_revision is not None:
                    raise ValidationFailure('Shared public cache cannot use actor-dependent permission revisions')
                revision = await permission_revision(query.from_user.id) if permission_revision else '0'
                page = await catalog.page(query, bot_id=bot.id, authorize=authorize, permission_revision=revision)
                if permission_revision and await permission_revision(query.from_user.id) != revision:
                    raise ConflictFailure('Inline permissions changed during search')
        except (ConflictFailure, PermissionDenied, TimeoutError):
            page = InlinePage((), '', InlineCachePolicy(), context)
        completed = await bot(
            page.answer_request(
                query, bot_id=bot.id, custom_emoji_entitlement_verified=custom_emoji_entitlement_verified
            )
        )
        if completed is not True:
            raise InvalidCompletion('Telegram did not confirm the inline answer')

    return router
