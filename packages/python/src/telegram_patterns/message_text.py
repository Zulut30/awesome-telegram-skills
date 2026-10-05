"""SDK-free composition of plain text and validated outgoing entity ranges."""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, replace
import html
import re
from typing import Literal, Sequence, TypedDict
import unicodedata
from urllib.parse import urlsplit

EntityKind = Literal['bold', 'italic', 'underline', 'strikethrough', 'spoiler', 'code', 'pre',
                     'text_link', 'custom_emoji', 'blockquote', 'expandable_blockquote']
_STYLES = frozenset({'bold', 'italic', 'underline', 'strikethrough', 'spoiler'})
_KINDS = _STYLES | {'code', 'pre', 'text_link', 'custom_emoji', 'blockquote', 'expandable_blockquote'}
_ATOMIC = frozenset({'text_link', 'custom_emoji', 'blockquote', 'expandable_blockquote'})
_MAX_UNITS = 262144
_MAX_ENTITIES = 512


def utf16_length(text: str) -> int:
    """Count UTF-16 code units; reject malformed scalar text and local size abuse."""
    if not isinstance(text, str):
        raise TypeError('Expected text')
    if len(text) > _MAX_UNITS:
        raise ValueError('Text exceeds the local composition bound')
    try:
        size = len(text.encode('utf-16-le')) // 2
    except UnicodeEncodeError:
        raise ValueError('Unpaired surrogate in text') from None
    if size > _MAX_UNITS or any(ord(c) < 32 and c not in '\t\r\n' for c in text):
        raise ValueError('Text exceeds the local bound or contains a control character')
    return size


def escape_html(text: str) -> str:
    """Escape a literal insertion, including quotes; this does not sanitize markup/URLs."""
    utf16_length(text)
    return html.escape(text, quote=True)


def escape_markdown_v2(text: str, *, context: Literal['text', 'code', 'link'] = 'text') -> str:
    """Escape a literal in ordinary text, code/pre, or a link destination."""
    utf16_length(text)
    if not isinstance(context, str) or context not in {'text', 'code', 'link'}:
        raise ValueError('Expected text, code or link context')
    reserved = '\\`' if context == 'code' else '\\)' if context == 'link' else '\\_*[]()~`>#+-=|{}.!'
    return ''.join('\\' + c if c in reserved else c for c in text)


def _integer(value: int, *, positive: bool = False) -> None:
    if type(value) is not int or not (1 if positive else 0) <= value <= _MAX_UNITS:
        raise ValueError('Expected a bounded integer UTF-16 range')


def _url(value: str) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValueError('Expected an absolute HTTP(S) URL')
    utf16_length(value)
    if any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
        raise ValueError('Invalid link destination')
    try:
        parts = urlsplit(value)
        if (parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username is not None
                or parts.password is not None or parts.port is not None and not 1 <= parts.port <= 65535):
            raise ValueError
    except ValueError:
        raise ValueError('Expected an absolute HTTP(S) URL without credentials') from None


@dataclass(frozen=True, slots=True)
class TextEntity:
    kind: EntityKind
    offset: int
    length: int
    url: str | None = None
    language: str | None = None
    custom_emoji_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind not in _KINDS:
            raise ValueError('Unsupported outgoing entity kind')
        _integer(self.offset)
        _integer(self.length, positive=True)
        if self.offset + self.length > _MAX_UNITS:
            raise ValueError('Entity exceeds the local composition bound')
        if self.kind == 'text_link':
            _url(self.url)  # type: ignore[arg-type]
        elif self.url is not None:
            raise ValueError('url is only valid for text_link')
        if self.language is not None:
            if self.kind != 'pre' or not isinstance(self.language, str) or not re.fullmatch(r'[a-zA-Z0-9_+.-]{1,64}', self.language):
                raise ValueError('language is only valid for pre')
        if self.kind == 'custom_emoji':
            if (not isinstance(self.custom_emoji_id, str) or not re.fullmatch(r'[1-9][0-9]{0,31}', self.custom_emoji_id)
                    or self.length > 32):
                raise ValueError('Expected a custom emoji identifier and bounded fallback')
        elif self.custom_emoji_id is not None:
            raise ValueError('custom_emoji_id is only valid for custom_emoji')

    def as_dict(self) -> dict[str, str | int]:
        """Fresh Bot API JSON mapping, independent from the immutable descriptor."""
        result: dict[str, str | int] = {'type': self.kind, 'offset': self.offset, 'length': self.length}
        for key, value in (('url', self.url), ('language', self.language), ('custom_emoji_id', self.custom_emoji_id)):
            if value is not None:
                result[key] = value
        return result


class TextPayload(TypedDict):
    text: str
    entities: list[dict[str, str | int]]
    parse_mode: None


def _positions(text: str) -> list[int]:
    positions = [0]
    for char in text:
        positions.append(positions[-1] + (2 if ord(char) > 0xFFFF else 1))
    return positions


@dataclass(frozen=True, slots=True)
class FormattedText:
    text: str
    entities: tuple[TextEntity, ...] = ()

    def __post_init__(self) -> None:
        size = utf16_length(self.text)
        if not isinstance(self.entities, (tuple, list)) or len(self.entities) > _MAX_ENTITIES:
            raise ValueError('Expected at most 512 outgoing entities')
        if any(not isinstance(e, TextEntity) for e in self.entities):
            raise TypeError('Expected TextEntity descriptors')
        entities = tuple(sorted(self.entities, key=lambda e: (e.offset, -e.length, e.kind)))
        positions = set(_positions(self.text))
        if len(set(entities)) != len(entities):
            raise ValueError('Duplicate entity')
        for index, entity in enumerate(entities):
            end = entity.offset + entity.length
            if end > size or entity.offset not in positions or end not in positions:
                raise ValueError('Entity must cover whole Unicode scalars within the text')
            for other in entities[:index]:
                other_end = other.offset + other.length
                if entity.offset >= other_end:
                    continue
                if end > other_end:
                    raise ValueError('Crossing entity ranges')
                if entity.kind in {'pre', 'code'} or other.kind in {'pre', 'code'}:
                    raise ValueError('Code and pre cannot overlap another entity')
                if entity.kind not in _STYLES and other.kind not in _STYLES:
                    raise ValueError('These entities cannot be nested')
        object.__setattr__(self, 'entities', entities)

    def as_kwargs(self, *, limit: int = 4096, custom_emoji_entitlement_verified: bool = False) -> TextPayload:
        """One outgoing text payload; explicit None overrides a host default parse mode."""
        _limit(limit)
        if type(custom_emoji_entitlement_verified) is not bool:
            raise TypeError('Expected a verified capability flag')
        if not self.text.strip() or utf16_length(self.text) > limit:
            raise ValueError('Split before creating a single-message payload')
        if len(self.entities) > 100:
            raise ValueError('Single payload exceeds the local 100-entity bound')
        return {'text': self.text, 'parse_mode': None, 'entities': [e.as_dict() for e in self.entities
                if e.kind != 'custom_emoji' or custom_emoji_entitlement_verified]}

    def split(self, *, limit: int = 4096) -> tuple[FormattedText, ...]:
        return split_formatted(self, limit=limit)


@dataclass(frozen=True, slots=True)
class MessageBuilder:
    value: FormattedText = FormattedText('')

    def __post_init__(self) -> None:
        if not isinstance(self.value, FormattedText):
            raise TypeError('Expected FormattedText')

    def append(self, value: FormattedText) -> MessageBuilder:
        if not isinstance(value, FormattedText):
            raise TypeError('Expected FormattedText')
        shift = utf16_length(self.value.text)
        joined = FormattedText(self.value.text + value.text,
            self.value.entities + tuple(replace(e, offset=e.offset + shift) for e in value.entities))
        return MessageBuilder(joined)

    def text(self, value: str) -> MessageBuilder:
        return self.append(FormattedText(value))

    def style(self, value: str, kind: EntityKind, *, url: str | None = None,
              language: str | None = None, custom_emoji_id: str | None = None) -> MessageBuilder:
        entity = TextEntity(kind, 0, utf16_length(value), url=url, language=language, custom_emoji_id=custom_emoji_id)
        return self.append(FormattedText(value, (entity,)))

    def custom_emoji(self, fallback: str, custom_emoji_id: str) -> MessageBuilder:
        """Host supplies one valid emoji from the inspected custom sticker metadata."""
        return self.style(fallback, 'custom_emoji', custom_emoji_id=custom_emoji_id)

    def build(self) -> FormattedText:
        return self.value


def _limit(value: int) -> None:
    if type(value) is not int or not 1 <= value <= 4096:
        raise ValueError('Expected a conservative UTF-16 chunk limit from 1 to 4096')


def _cuts(text: str, positions: Sequence[int]) -> list[int]:
    """Scalar boundaries retaining combining runs and common emoji sequences; not full UAX29."""
    cuts = [0]
    regional_run = 0
    for index in range(1, len(text)):
        before, after = text[index-1], text[index]
        previous, following = ord(before), ord(after)
        regional_run = regional_run + 1 if 0x1F1E6 <= previous <= 0x1F1FF else 0
        forbidden = (unicodedata.category(after).startswith('M') or following in {0xFE0E,0xFE0F,0x200D,0x200C}
            or previous in {0x200D,0x200C} or unicodedata.combining(before) == 9
            or 0x1F3FB <= following <= 0x1F3FF or 0xE0020 <= following <= 0xE007F
            or before == '\r' and after == '\n'
            or regional_run % 2 == 1 and 0x1F1E6 <= following <= 0x1F1FF)
        if not forbidden:
            cuts.append(positions[index])
    if text:
        cuts.append(positions[-1])
    return cuts


def split_formatted(value: FormattedText, *, limit: int = 4096) -> tuple[FormattedText, ...]:
    """Lossless text partition; clip styles/code and retain whole links/quotes/custom emoji."""
    if not isinstance(value, FormattedText):
        raise TypeError('Expected FormattedText')
    _limit(limit)
    positions = _positions(value.text)
    indices = {position: index for index, position in enumerate(positions)}
    cuts = _cuts(value.text, positions)
    atomic = [e for e in value.entities if e.kind in _ATOMIC]
    if any(e.length > limit for e in atomic):
        raise ValueError('An atomic link, quote or emoji exceeds the chunk limit')
    starts = [e.offset for e in atomic]
    chunks: list[FormattedText] = []
    start = 0
    while start < positions[-1]:
        end = cuts[bisect_right(cuts, start + limit)-1]
        while end > start:
            index = bisect_right(starts, end-1)-1
            if index < 0 or end >= atomic[index].offset + atomic[index].length:
                break
            end = cuts[bisect_right(cuts, atomic[index].offset)-1]
        if end <= start:
            raise ValueError('A preserved Unicode sequence exceeds the chunk limit')
        entities = tuple(replace(e, offset=max(e.offset,start)-start,
            length=min(e.offset+e.length,end)-max(e.offset,start)) for e in value.entities
            if e.offset < end and e.offset+e.length > start)
        chunk = FormattedText(value.text[indices[start]:indices[end]], entities)
        if len(chunk.entities) > 100:
            raise ValueError('A chunk exceeds the local 100-entity bound; compose smaller sections')
        if len(chunks) >= 256:
            raise ValueError('Composition exceeds the local 256-chunk bound')
        chunks.append(chunk)
        start = end
    return tuple(chunks)
