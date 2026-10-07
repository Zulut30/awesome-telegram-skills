"""SDK-free rich message blocks for sendRichMessage (Bot API 10.1+) with a plain-text fallback.

RichMessageBuilder composes the common blocks: headings, paragraphs, lists and checklists, tables,
button rows, plain and expandable quotations, details, documents, code, dividers and footers. build()
checks Telegram's published limits and returns a RichMessage: as_input() is the InputRichMessage JSON,
fallback() and fallback_keyboard() describe the same content for an ordinary sendMessage.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Literal, Sequence, TypeAlias, Union

from .message_text import EntityKind, FormattedText, MessageBuilder, utf16_length

RichButtonStyle = Literal['danger', 'success', 'primary', 'link']
RichAlign = Literal['left', 'center', 'right']
RichListLabel = Literal['1', 'a', 'A', 'i', 'I']
SpanKind = Literal['bold', 'italic', 'code', 'url']

# Published limits (core.telegram.org/bots/api#rich-message-formatting-options).
MAX_TEXT_CHARACTERS = 32768
MAX_BLOCKS = 500
MAX_DEPTH = 16
MAX_MEDIA = 50
MAX_COLUMNS = 20
MAX_ROW_BUTTONS = 8


@dataclass(frozen=True, slots=True)
class RichSpan:
    """Inline formatting inside rich text: bold, italic, code or an HTTP(S) link."""
    kind: SpanKind
    text: str
    url: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ('bold', 'italic', 'code', 'url'):
            raise ValueError('Expected bold, italic, code or url')
        _text(self.text)
        if (self.kind == 'url') != (self.url is not None):
            raise ValueError('Only a url span has a URL')
        if self.url is not None:
            # Same rule as a text_link entity, so the fallback can keep the link.
            MessageBuilder().style(self.text, 'text_link', url=self.url)

    def as_dict(self) -> dict[str, str]:
        value = {'type': self.kind, 'text': self.text}
        if self.url is not None:
            value['url'] = self.url
        return value


RichText: TypeAlias = Union[str, RichSpan, Sequence[Union[str, RichSpan]]]


@dataclass(frozen=True, slots=True)
class RichButton:
    """One rich message button: exactly one of url and callback_data; 'link' style only for callbacks."""
    text: str
    url: str | None = None
    callback_data: str | None = None
    style: RichButtonStyle | None = None

    def __post_init__(self) -> None:
        _text(self.text)
        if (self.url is None) == (self.callback_data is None):
            raise ValueError('A button has exactly one action: url or callback_data')
        if self.callback_data is not None and (not isinstance(self.callback_data, str)
                                               or not 1 <= len(self.callback_data.encode('utf-8')) <= 64):
            raise ValueError('callback_data must be 1-64 bytes')
        if self.url is not None:
            MessageBuilder().style(self.text, 'text_link', url=self.url)
        if self.style is not None and self.style not in ('danger', 'success', 'primary', 'link'):
            raise ValueError('Expected danger, success, primary or link')
        if self.style == 'link' and self.callback_data is None:
            raise ValueError("Style 'link' is allowed only for callback buttons")

    def as_dict(self) -> dict[str, str]:
        value = {'text': self.text}
        if self.url is not None:
            value['url'] = self.url
        elif self.callback_data is not None:
            value['callback_data'] = self.callback_data
        if self.style is not None:
            value['style'] = self.style
        return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Expected non-empty text')
    utf16_length(value)
    return value


def _parts(text: RichText) -> tuple[str | RichSpan, ...]:
    parts = (text,) if isinstance(text, (str, RichSpan)) else tuple(text)
    if not parts or any(not isinstance(part, (str, RichSpan)) for part in parts):
        raise ValueError('Expected text, RichSpan or a sequence of them')
    for part in parts:
        if isinstance(part, str):
            utf16_length(part)
    if not ''.join(part if isinstance(part, str) else part.text for part in parts).strip():
        raise ValueError('Expected non-empty text')
    return parts


def _json(parts: tuple[str | RichSpan, ...]) -> Any:
    items = [part if isinstance(part, str) else part.as_dict() for part in parts]
    return items[0] if len(items) == 1 else items


def _plain(parts: tuple[str | RichSpan, ...]) -> str:
    return ''.join(part if isinstance(part, str) else part.text for part in parts)


def _styled(builder: MessageBuilder, parts: tuple[str | RichSpan, ...]) -> MessageBuilder:
    for part in parts:
        if isinstance(part, str):
            builder = builder.text(part)
        elif part.kind == 'url':
            builder = builder.style(part.text, 'text_link', url=part.url)
        else:
            builder = builder.style(part.text, part.kind)
    return builder


@dataclass(frozen=True, slots=True)
class _Block:
    data: str            # canonical JSON of one InputRichBlock
    blocks: int          # blocks Telegram counts here, nested ones included
    depth: int           # nesting levels below the message
    media: int
    characters: int
    fallback: FormattedText
    buttons: tuple[tuple[RichButton, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class RichMessage:
    """Immutable result of RichMessageBuilder.build(); every limit is already checked."""
    blocks: tuple[_Block, ...]
    is_rtl: bool = False
    skip_entity_detection: bool = False

    def as_input(self) -> dict[str, Any]:
        """InputRichMessage JSON for sendRichMessage(rich_message=...); a fresh copy each time."""
        value: dict[str, Any] = {'blocks': [json.loads(block.data) for block in self.blocks]}
        if self.is_rtl:
            value['is_rtl'] = True
        if self.skip_entity_detection:
            value['skip_entity_detection'] = True
        return value

    @property
    def block_count(self) -> int:
        return sum(block.blocks for block in self.blocks)

    @property
    def media_count(self) -> int:
        return sum(block.media for block in self.blocks)

    def fallback(self) -> FormattedText:
        """The same content as ordinary text and entities; split it with .split() before sendMessage."""
        builder = MessageBuilder()
        for index, part in enumerate(block.fallback for block in self.blocks if block.fallback.text):
            builder = builder.append(part) if index == 0 else builder.text('\n').append(part)
        text = builder.build()
        # Every block ends with a line break outside its entities, so trailing breaks can go.
        return FormattedText(text.text.rstrip('\n'), text.entities)

    def fallback_keyboard(self) -> list[list[dict[str, str]]]:
        """Inline keyboard rows for the fallback message; style 'link' has no plain-keyboard equivalent."""
        rows = []
        for block in self.blocks:
            for row in block.buttons:
                rows.append([{key: value for key, value in button.as_dict().items() if not (key == 'style' and value == 'link')}
                             for button in row])
        return rows


class RichMessageBuilder:
    """Collects blocks in order; nested content (list items, details) comes from another builder."""

    def __init__(self, *, rtl: bool = False, skip_entity_detection: bool = False) -> None:
        if type(rtl) is not bool or type(skip_entity_detection) is not bool:
            raise TypeError('Expected boolean flags')
        self._blocks: list[_Block] = []
        self._rtl, self._skip = rtl, skip_entity_detection

    def _add(self, data: dict[str, Any], fallback: FormattedText, *, blocks: int = 1, depth: int = 1, media: int = 0,
             characters: int = 0, buttons: tuple[tuple[RichButton, ...], ...] = ()) -> RichMessageBuilder:
        self._blocks.append(_Block(json.dumps(data, ensure_ascii=False, sort_keys=True), blocks, depth, media, characters,
                                   fallback, buttons))
        return self

    def heading(self, text: RichText, *, size: int = 2) -> RichMessageBuilder:
        if type(size) is not int or not 1 <= size <= 6:
            raise ValueError('Heading size is 1-6, 1 is the largest')
        parts = _parts(text)
        return self._add({'type': 'heading', 'text': _json(parts), 'size': size},
                         MessageBuilder().style(_plain(parts), 'bold').text('\n').build(), characters=len(_plain(parts)))

    def paragraph(self, text: RichText) -> RichMessageBuilder:
        parts = _parts(text)
        return self._add({'type': 'paragraph', 'text': _json(parts)}, _styled(MessageBuilder(), parts).text('\n').build(),
                         characters=len(_plain(parts)))

    def _list(self, items: Sequence[tuple[RichText, bool | None]], label: RichListLabel | None) -> RichMessageBuilder:
        if isinstance(items, (str, RichSpan)) or not items:
            raise ValueError('Expected at least one list item')
        entries, fallback, characters = [], MessageBuilder(), 0
        for number, (text, checked) in enumerate(items, 1):
            parts = _parts(text)
            item: dict[str, Any] = {'blocks': [{'type': 'paragraph', 'text': _json(parts)}]}
            if checked is not None:
                item.update(has_checkbox=True, **({'is_checked': True} if checked else {}))
                marker = '☑ ' if checked else '☐ '
            elif label is not None:
                item.update(type=label, value=number)
                marker = f'{_label(label, number)}. '
            else:
                marker = '• '
            entries.append(item)
            fallback = _styled(fallback.text(marker), parts).text('\n')
            characters += len(_plain(parts))
        # The list, each item and each item paragraph are blocks.
        return self._add({'type': 'list', 'items': entries}, fallback.build(), blocks=1 + 2 * len(entries), depth=3,
                         characters=characters)

    def bullets(self, items: Sequence[RichText]) -> RichMessageBuilder:
        return self._list([(item, None) for item in _sequence(items)], None)

    def numbered(self, items: Sequence[RichText], *, label: RichListLabel = '1') -> RichMessageBuilder:
        if label not in ('1', 'a', 'A', 'i', 'I'):
            raise ValueError("Expected label '1', 'a', 'A', 'i' or 'I'")
        return self._list([(item, None) for item in _sequence(items)], label)

    def checklist(self, items: Sequence[tuple[RichText, bool]]) -> RichMessageBuilder:
        pairs = _sequence(items)
        if any(not isinstance(pair, tuple) or len(pair) != 2 or type(pair[1]) is not bool for pair in pairs):
            raise ValueError('Expected (text, checked) pairs')
        return self._list(list(pairs), None)

    def table(self, rows: Sequence[Sequence[RichText]], *, header: bool = True, compact: bool = False,
              bordered: bool = True, striped: bool = False, caption: RichText | None = None,
              align: RichAlign = 'left') -> RichMessageBuilder:
        table_rows = [list(_sequence(row)) for row in _sequence(rows)]
        width = max(len(row) for row in table_rows)
        if width > MAX_COLUMNS:
            raise ValueError(f'A table has at most {MAX_COLUMNS} columns')
        if align not in ('left', 'center', 'right'):
            raise ValueError('Expected left, center or right')
        cells, fallback, characters = [], MessageBuilder(), 0
        for index, row in enumerate(table_rows):
            line = []
            for cell in row:
                parts = _parts(cell)
                line.append({'text': _json(parts), 'align': align, 'valign': 'top', **({'is_header': True} if header and index == 0 else {})})
                characters += len(_plain(parts))
            cells.append(line)
            text = ' | '.join(_plain(_parts(cell)) for cell in row) + '\n'
            fallback = fallback.style(text[:-1], 'bold').text('\n') if header and index == 0 else fallback.text(text)
        data: dict[str, Any] = {'type': 'table', 'cells': cells}
        for name, flag in (('is_bordered', bordered), ('is_striped', striped), ('is_compact', compact)):
            if type(flag) is not bool:
                raise TypeError('Expected boolean table flags')
            if flag:
                data[name] = True
        if caption is not None:
            parts = _parts(caption)
            data['caption'] = _json(parts)
            fallback = fallback.style(_plain(parts), 'italic').text('\n')
            characters += len(_plain(parts))
        return self._add(data, fallback.build(), blocks=1 + len(table_rows), characters=characters)

    def buttons(self, buttons: Sequence[RichButton], *, align: RichAlign | None = None) -> RichMessageBuilder:
        row = tuple(_sequence(buttons))
        if not 1 <= len(row) <= MAX_ROW_BUTTONS or any(not isinstance(button, RichButton) for button in row):
            raise ValueError(f'A button row has 1-{MAX_ROW_BUTTONS} RichButton values')
        data: dict[str, Any] = {'type': 'buttons', 'buttons': [button.as_dict() for button in row]}
        if align is not None:
            if align not in ('left', 'center', 'right'):
                raise ValueError('Expected left, center or right')
            data['align'] = align
        # Buttons move to an inline keyboard in the fallback; the text gets no line for them.
        return self._add(data, FormattedText(''), characters=sum(len(button.text) for button in row), buttons=(row,))

    def quote(self, text: RichText, *, credit: RichText | None = None, expandable: bool = False) -> RichMessageBuilder:
        if type(expandable) is not bool:
            raise TypeError('Expected a boolean expandable flag')
        parts = _parts(text)
        body = _plain(parts) + (f'\n— {_plain(_parts(credit))}' if credit is not None else '')
        if expandable:
            data: dict[str, Any] = {'type': 'expandable_blockquote', 'text': _json(parts)}
        else:
            data = {'type': 'blockquote', 'blocks': [{'type': 'paragraph', 'text': _json(parts)}]}
        if credit is not None:
            data['credit'] = _json(_parts(credit))
        kind: EntityKind = 'expandable_blockquote' if expandable else 'blockquote'
        return self._add(data, MessageBuilder().style(body, kind).text('\n').build(), blocks=1 if expandable else 2,
                         depth=1 if expandable else 2, characters=len(body))

    def details(self, summary: RichText, content: RichMessageBuilder, *, open: bool = False) -> RichMessageBuilder:
        if not isinstance(content, RichMessageBuilder) or content is self or not content._blocks:
            raise ValueError('Details need another non-empty RichMessageBuilder as content')
        if type(open) is not bool:
            raise TypeError('Expected a boolean open flag')
        parts = _parts(summary)
        inner = content.build()
        data: dict[str, Any] = {'type': 'details', 'summary': _json(parts), 'blocks': inner.as_input()['blocks']}
        if open:
            data['is_open'] = True
        hidden = inner.fallback().text.strip()
        fallback = MessageBuilder().style(_plain(parts), 'bold').text('\n')
        if hidden:
            fallback = fallback.style(hidden, 'expandable_blockquote').text('\n')
        return self._add(data, fallback.build(), blocks=1 + inner.block_count,
                         depth=1 + max(block.depth for block in inner.blocks), media=inner.media_count,
                         characters=len(_plain(parts)) + sum(block.characters for block in inner.blocks),
                         buttons=tuple(row for block in inner.blocks for row in block.buttons))

    def document(self, media: str, *, caption: RichText | None = None) -> RichMessageBuilder:
        """A file by file_id or HTTP(S) URL; uploading new bytes belongs to the SDK request."""
        _text(media)
        data: dict[str, Any] = {'type': 'document', 'document': {'type': 'document', 'media': media}}
        characters = 0
        label = 'Документ'
        if caption is not None:
            parts = _parts(caption)
            data['caption'] = {'text': _json(parts)}
            label, characters = _plain(parts), len(_plain(parts))
        return self._add(data, MessageBuilder().text(f'📎 {label}\n').build(), media=1, characters=characters)

    def code(self, text: str, *, language: str | None = None) -> RichMessageBuilder:
        _text(text)
        data: dict[str, Any] = {'type': 'pre', 'text': text}
        if language is not None:
            _text(language)
            data['language'] = language
        return self._add(data, MessageBuilder().style(text, 'pre', language=language).text('\n').build(), characters=len(text))

    def divider(self) -> RichMessageBuilder:
        return self._add({'type': 'divider'}, MessageBuilder().text('———\n').build())

    def footer(self, text: RichText) -> RichMessageBuilder:
        parts = _parts(text)
        return self._add({'type': 'footer', 'text': _json(parts)}, MessageBuilder().style(_plain(parts), 'italic').text('\n').build(),
                         characters=len(_plain(parts)))

    def build(self) -> RichMessage:
        """Check Telegram's limits and freeze the blocks."""
        if not self._blocks:
            raise ValueError('A rich message needs at least one block')
        message = RichMessage(tuple(self._blocks), self._rtl, self._skip)
        if message.block_count > MAX_BLOCKS:
            raise ValueError(f'A rich message has at most {MAX_BLOCKS} blocks, nested ones included')
        if max(block.depth for block in self._blocks) > MAX_DEPTH:
            raise ValueError(f'A rich message nests at most {MAX_DEPTH} levels')
        if message.media_count > MAX_MEDIA:
            raise ValueError(f'A rich message has at most {MAX_MEDIA} media attachments')
        if sum(block.characters for block in self._blocks) > MAX_TEXT_CHARACTERS:
            raise ValueError(f'A rich message has at most {MAX_TEXT_CHARACTERS} characters of text')
        return message


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise ValueError('Expected a non-empty sequence')
    return value


def _label(kind: str, number: int) -> str:
    if kind in ('a', 'A'):
        text, value = '', number
        while value:
            value, rest = divmod(value - 1, 26)
            text = chr(ord('a') + rest) + text
        return text if kind == 'a' else text.upper()
    if kind in ('i', 'I'):
        numerals = ((1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'), (100, 'c'), (90, 'xc'), (50, 'l'), (40, 'xl'),
                    (10, 'x'), (9, 'ix'), (5, 'v'), (4, 'iv'), (1, 'i'))
        text, value = '', number
        for amount, symbol in numerals:
            count, value = divmod(value, amount)
            text += symbol * count
        return text if kind == 'i' else text.upper()
    return str(number)
