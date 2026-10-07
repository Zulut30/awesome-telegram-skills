"""Bounded media composition and explicit hosted download, using the host Bot.

No sending, polling, implicit URL fetch, filesystem access or automatic retry.
Uploads are byte snapshots, not codec/content validation. Telegram delivery,
file ownership, authorization and current chat permissions belong to the host.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import math
import re
from typing import Literal, Sequence, TypeAlias

from aiogram import Bot
from aiogram.methods import EditMessageMedia, SendAudio, SendDocument, SendMediaGroup, SendPhoto, SendVideo
from aiogram.types import BufferedInputFile, InputMediaAudio, InputMediaDocument, InputMediaPhoto, InputMediaVideo

from .errors import InvalidType, PatternError, TransportFailure, UnsupportedCapability, ValidationFailure
from .message_text import FormattedText, utf16_length

MediaKind: TypeAlias = Literal['photo', 'video', 'audio', 'document']
MediaSendRequest: TypeAlias = SendPhoto | SendVideo | SendAudio | SendDocument
_InputMedia: TypeAlias = InputMediaPhoto | InputMediaVideo | InputMediaAudio | InputMediaDocument
_KINDS = ('photo', 'video', 'audio', 'document')
_MB = 1_000_000  # Conservative decimal-byte policy, not inferred MiB.

__all__ = ['MediaKind', 'MediaSendRequest', 'MediaFile', 'MediaItem', 'DownloadedMedia',
           'media_request', 'media_album', 'media_edit', 'download_media']


def _positive(value: int, label: str) -> None:
    if type(value) is not int or not 0 < value < 2**52:
        raise ValidationFailure(f'{label} must be a positive integer below 2**52')


def _file_id(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,1024}', value):
        raise ValidationFailure('Use an opaque Telegram file_id, not a URL, path or attach reference')


def _chat(value: int | str) -> None:
    if type(value) is int and 0 < abs(value) < 2**52:
        return
    if isinstance(value, str) and re.fullmatch(r'@[A-Za-z][A-Za-z0-9_]{4,31}', value):
        return
    raise ValidationFailure('Use a nonzero integer chat ID or explicit @username')


@dataclass(frozen=True, slots=True)
class MediaFile:
    """One typed upload or a file_id bound to the bot that received it.

    reference=bytes: snapshot plus server-controlled basename; never reads a path.
    reference=str: host-observed file_id and bot_id; no file_unique_id conversion.
    width/height are optional host-verified photo dimensions, not a codec probe.
    """
    kind: MediaKind
    reference: str | bytes = field(repr=False)
    filename: str | None = None
    bot_id: int | None = None
    width: int | None = None
    height: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise UnsupportedCapability('Supported media kinds: photo, video, audio, document')
        if isinstance(self.reference, bytes):
            limit = (10 if self.kind == 'photo' else 50) * _MB
            if not 0 < len(self.reference) <= limit:
                raise ValidationFailure('Upload is empty or exceeds this media kind size limit')
            name = self.filename
            if not isinstance(name, str) or not name.strip() or utf16_length(name) > 128 or any(c in name for c in '/\\:\x00\r\n') or name in {'.','..'}:
                raise ValidationFailure('Upload filename must be a basename up to 128 UTF-16 units')
            if self.bot_id is not None:
                raise ValidationFailure('Bot scope belongs to reused file_id, not upload bytes')
        elif isinstance(self.reference, str):
            _file_id(self.reference)
            if self.bot_id is None:
                raise ValidationFailure('Reused file_id requires its original bot_id')
            _positive(self.bot_id, 'Bot ID')
            if self.filename is not None:
                raise ValidationFailure('A reused file_id has no upload filename')
        else:
            raise InvalidType('Use immutable bytes or a bot-scoped file_id')
        if self.width is not None or self.height is not None:
            if self.kind != 'photo' or not isinstance(self.reference, bytes) or self.width is None or self.height is None:
                raise ValidationFailure('Supply both dimensions only for a photo upload')
            _positive(self.width, 'Photo width'); _positive(self.height, 'Photo height')
            if self.width + self.height > 10000 or max(self.width,self.height) > 20 * min(self.width,self.height):
                raise ValidationFailure('Photo dimensions exceed sum/ratio limits')

    def as_input(self, bot_id: int) -> str | BufferedInputFile:
        """Fresh multipart object, or the ID after checking its declared bot scope."""
        _positive(bot_id, 'Bot ID')
        if isinstance(self.reference, str):
            if self.bot_id != bot_id:
                raise ValidationFailure('file_id cannot be reused by a different bot')
            return self.reference
        assert self.filename is not None
        return BufferedInputFile(self.reference, filename=self.filename)


@dataclass(frozen=True, slots=True)
class MediaItem:
    file: MediaFile
    caption: FormattedText | None = None
    spoiler: bool = False
    caption_above: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.file, MediaFile) or (self.caption is not None and not isinstance(self.caption, FormattedText)):
            raise InvalidType('Use MediaFile and an optional immutable FormattedText caption')
        if type(self.spoiler) is not bool or type(self.caption_above) is not bool:
            raise InvalidType('Media presentation flags must be bool')
        if (self.spoiler or self.caption_above) and self.file.kind not in ('photo','video'):
            raise UnsupportedCapability('Spoiler and caption-above apply only to photo/video here')
        if self.caption is not None and (utf16_length(self.caption.text) > 1024 or len(self.caption.entities) > 100):
            raise ValidationFailure('Caption exceeds 1024 UTF-16 units or 100 entities')

    def caption_kwargs(self, *, custom_emoji_entitlement_verified: bool = False) -> dict[str, object]:
        """Explicit parse_mode=None, including absent/empty/whitespace captions."""
        if type(custom_emoji_entitlement_verified) is not bool:
            raise InvalidType('Custom emoji capability must be an explicit bool')
        caption = self.caption
        entities = [] if caption is None else [e.as_dict() for e in caption.entities
            if e.kind != 'custom_emoji' or custom_emoji_entitlement_verified]
        return {'caption': None if caption is None else caption.text, 'caption_entities': entities, 'parse_mode': None}

    def as_input_media(self, bot_id: int, *, custom_emoji_entitlement_verified: bool = False) -> _InputMedia:
        """Native SDK input, freshly composed without reading/sending a file."""
        data = {'media': self.file.as_input(bot_id), **self.caption_kwargs(custom_emoji_entitlement_verified=custom_emoji_entitlement_verified)}
        if self.file.kind in ('photo','video'):
            data.update(has_spoiler=self.spoiler, show_caption_above_media=self.caption_above)
        models: dict[str, type[_InputMedia]] = {'photo': InputMediaPhoto, 'video': InputMediaVideo, 'audio': InputMediaAudio, 'document': InputMediaDocument}
        return models[self.file.kind].model_validate(data)


def media_request(item: MediaItem, *, bot_id: int, chat_id: int | str,
                  message_thread_id: int | None = None, custom_emoji_entitlement_verified: bool = False) -> MediaSendRequest:
    """Build one send request; host calls its Bot and retains delivery policy."""
    if not isinstance(item, MediaItem):
        raise InvalidType('Use a MediaItem')
    _chat(chat_id)
    if message_thread_id is not None:
        _positive(message_thread_id, 'Thread ID')
    data = {'chat_id': chat_id, 'message_thread_id': message_thread_id,
            item.file.kind: item.file.as_input(bot_id), **item.caption_kwargs(custom_emoji_entitlement_verified=custom_emoji_entitlement_verified)}
    if item.file.kind in ('photo','video'):
        data.update(has_spoiler=item.spoiler, show_caption_above_media=item.caption_above)
    models: dict[str, type[MediaSendRequest]] = {'photo': SendPhoto, 'video': SendVideo, 'audio': SendAudio, 'document': SendDocument}
    return models[item.file.kind].model_validate(data)


def media_album(items: Sequence[MediaItem], *, bot_id: int, chat_id: int | str,
                message_thread_id: int | None = None, custom_emoji_entitlement_verified: bool = False) -> SendMediaGroup:
    """One 2..10-item album; documents/audio remain homogeneous. No batching."""
    if not isinstance(items, (tuple,list)):
        raise InvalidType('Use a list or tuple of MediaItem')
    snapshot = tuple(items)
    if not 2 <= len(snapshot) <= 10 or any(not isinstance(item, MediaItem) for item in snapshot):
        raise ValidationFailure('Album requires 2..10 MediaItem values')
    kinds = {item.file.kind for item in snapshot}
    if kinds not in ({'photo'},{'video'},{'photo','video'},{'document'},{'audio'}):
        raise UnsupportedCapability('Album cannot mix documents/audio with another media kind')
    _chat(chat_id)
    if message_thread_id is not None:
        _positive(message_thread_id, 'Thread ID')
    return SendMediaGroup(chat_id=chat_id, message_thread_id=message_thread_id,
        media=[item.as_input_media(bot_id,custom_emoji_entitlement_verified=custom_emoji_entitlement_verified) for item in snapshot])


def media_edit(item: MediaItem, *, bot_id: int, chat_id: int | str | None = None,
               message_id: int | None = None, inline_message_id: str | None = None,
               album_kind: Literal['photo-video','document','audio'] | None = None,
               custom_emoji_entitlement_verified: bool = False) -> EditMessageMedia:
    """Exclusive normal/inline address and host-observed album type, no sending.

    Host verifies message ownership, current ACL, context and edit availability.
    Inline replacement accepts a same-bot file_id; uploads are rejected locally.
    """
    if not isinstance(item, MediaItem):
        raise InvalidType('Use a MediaItem')
    if inline_message_id is not None:
        if chat_id is not None or message_id is not None:
            raise ValidationFailure('Choose inline or chat/message address, never both')
        if not isinstance(inline_message_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,1024}',inline_message_id):
            raise ValidationFailure('Use an opaque inline message ID')
        if isinstance(item.file.reference,bytes):
            raise UnsupportedCapability('Inline media editing cannot upload a new file')
    else:
        if chat_id is None or message_id is None:
            raise ValidationFailure('Chat and message ID are both required')
        _chat(chat_id); _positive(message_id,'Message ID')
    if album_kind is not None:
        allowed = {'photo-video': ('photo','video'), 'document': ('document',), 'audio': ('audio',)}
        if not isinstance(album_kind,str) or album_kind not in allowed or item.file.kind not in allowed[album_kind]:
            raise UnsupportedCapability('Replacement does not match the host-observed album kind')
    return EditMessageMedia(chat_id=chat_id,message_id=message_id,inline_message_id=inline_message_id,
        media=item.as_input_media(bot_id,custom_emoji_entitlement_verified=custom_emoji_entitlement_verified))


@dataclass(frozen=True, slots=True)
class DownloadedMedia:
    """Bounded complete bytes and Telegram identifiers; no URL/path or filename."""
    data: bytes = field(repr=False)
    file_id: str = field(repr=False)
    file_unique_id: str = field(repr=False)
    bot_id: int

    def __post_init__(self) -> None:
        if not isinstance(self.data,bytes) or not 0 < len(self.data) <= 20*_MB:
            raise ValidationFailure('Downloaded bytes are empty or exceed the hosted limit')
        _file_id(self.file_id); _file_id(self.file_unique_id); _positive(self.bot_id,'Bot ID')


async def download_media(bot: Bot, file_id: str, *, max_bytes: int = 5*_MB,
                          timeout: float = 30) -> DownloadedMedia:
    """Explicit read: GetFile plus bounded hosted stream, no disk or retry.

    max_bytes <=20 MB, timeout covers metadata and content together. Stream closes
    on overflow, cancellation and errors. Stream HTTP/transport errors become
    TransportFailure or TimeoutError without the token-bearing URL or chained cause.
    Host decodes content in its own pipeline.
    Local Bot API paths require a separate explicit host adapter, never local read.
    """
    if not isinstance(bot,Bot):
        raise InvalidType('Use the existing host Bot')
    _file_id(file_id)
    if type(max_bytes) is not int or not 0 < max_bytes <= 20*_MB:
        raise ValidationFailure('Download bound must be an integer between 1 and 20000000 bytes')
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise ValidationFailure('Download timeout must be positive, finite and at most 300 seconds')
    if bot.session.api.is_local:
        raise UnsupportedCapability('Local Bot API filesystem download requires an explicit host adapter')
    async with asyncio.timeout(timeout):
        info = await bot.get_file(file_id)
        _file_id(info.file_id); _file_id(info.file_unique_id)
        if info.file_size is not None and (info.file_size < 0 or info.file_size > max_bytes):
            raise ValidationFailure('Telegram metadata exceeds the download bound')
        path = info.file_path
        if not isinstance(path,str) or len(path)>2048 or not re.fullmatch(r'[A-Za-z0-9_./-]+',path) or any(p in ('','.','..') for p in path.split('/')):
            raise ValidationFailure('Telegram did not return a supported relative file path')
        # This URL contains the token: never expose, persist or log it.
        stream = bot.session.stream_content(bot.session.api.file_url(bot.token,path),
            timeout=max(1,math.ceil(timeout)),chunk_size=min(65536,max_bytes),raise_for_status=True)
        data = bytearray()
        # Transport errors (HTTP status, connection timeout) carry the token URL in str()
        # and in chained tracebacks; replace them and raise outside the handler.
        failure: Exception | None = None
        try:
            async for chunk in stream:
                if not isinstance(chunk,bytes):
                    raise ValidationFailure('File stream returned unsupported chunks')
                if len(data)+len(chunk)>max_bytes:
                    raise ValidationFailure('Actual downloaded content exceeds the byte bound')
                data.extend(chunk)
        except PatternError:
            raise
        except TimeoutError:
            failure = TimeoutError('Telegram file download timed out')
        except Exception as error:
            status = getattr(error,'status',None)
            failure = TransportFailure(f'Telegram file endpoint returned HTTP {status}' if type(status) is int
                                       else 'Telegram file download failed')
        finally:
            await stream.aclose()
        if failure is not None:
            raise failure
        if info.file_size is not None and len(data)!=info.file_size:
            raise ValidationFailure('Downloaded content does not match the declared byte count')
        return DownloadedMedia(bytes(data),info.file_id,info.file_unique_id,bot.id)
