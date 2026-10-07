"""Immutable profile observations and explicitly authorized own-bot edits."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Awaitable, Callable, Literal, Mapping, TypeAlias

from aiogram import Bot
from aiogram.types import ChatFullInfo, InputProfilePhotoAnimated, InputProfilePhotoStatic, User

from .errors import InvalidType, PermissionDenied, UnknownOutcome, ValidationFailure
from .media_aiogram import MediaFile
from .message_text import utf16_length

ProfileSource: TypeAlias = Literal['update', 'getMe']
ProfileAuthorizer: TypeAlias = Callable[[int, int, str], Awaitable[bool]]

__all__ = [
    'ProfileSource',
    'ProfileAuthorizer',
    'UserProfile',
    'ChatProfile',
    'ProfilePhotoSize',
    'ProfilePhotos',
    'BotProfile',
    'BotProfilePatch',
    'ProfileEditIncomplete',
    'user_profile',
    'chat_profile',
    'read_profile_photos',
    'read_bot_profile',
    'update_bot_profile',
]

_USER_FLAGS = (
    'added_to_attachment_menu',
    'can_join_groups',
    'can_read_all_group_messages',
    'supports_guest_queries',
    'supports_inline_queries',
    'can_connect_to_business',
    'has_main_web_app',
    'has_topics_enabled',
    'allows_users_to_create_topics',
    'can_manage_bots',
    'supports_join_request_queries',
)
_CHAT_FLAGS = (
    'is_forum',
    'is_direct_messages',
    'has_private_forwards',
    'has_restricted_voice_and_video_messages',
    'has_protected_content',
    'has_hidden_members',
    'has_aggressive_anti_spam_enabled',
    'has_visible_history',
    'join_by_request',
    'join_to_send_messages',
    'can_set_sticker_set',
    'can_send_paid_media',
    'can_send_gift',
)


def _id(value: int, *, signed: bool = False) -> None:
    if type(value) is not int or value == 0 or abs(value) > 2**52 - 1 or (not signed and value < 0):
        raise ValidationFailure('Use a nonzero 52-bit numeric ID in the required scope')


def _text(value: str | None) -> None:
    if value is not None:
        if not isinstance(value, str):
            raise InvalidType('Profile text must be str or None')
        try:
            utf16_length(value)
        except ValueError:
            raise ValidationFailure('Profile text contains invalid Unicode') from None


def _observed(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationFailure('Profile observation needs an aware datetime')
    return value.astimezone(timezone.utc)


def _flags(value: Mapping[str, bool | None]) -> Mapping[str, bool | None]:
    if not isinstance(value, Mapping) or any(
        not isinstance(k, str) or (v is not None and type(v) is not bool) for k, v in value.items()
    ):
        raise InvalidType('Observed flags must preserve bool or None')
    return MappingProxyType(dict(value))


def _locale(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r'(?:[a-z]{2})?', value):
        raise ValidationFailure('Use an empty default locale or two lowercase ASCII letters')


@dataclass(frozen=True, slots=True)
class UserProfile:
    id: int
    is_bot: bool
    first_name: str = field(repr=False)
    last_name: str | None = field(repr=False)
    username: str | None = field(repr=False)
    language_code: str | None = field(repr=False)
    is_premium: bool | None
    capabilities: Mapping[str, bool | None] = field(repr=False)
    source: ProfileSource
    observed_at: datetime

    def __post_init__(self) -> None:
        _id(self.id)
        if type(self.is_bot) is not bool or (self.is_premium is not None and type(self.is_premium) is not bool):
            raise InvalidType('Profile flags must be explicit bool or unknown None')
        if not isinstance(self.first_name, str) or self.source not in ('update', 'getMe'):
            raise ValidationFailure('Use a first name and a declared observation source')
        for value in (self.first_name, self.last_name, self.username, self.language_code):
            _text(value)
        object.__setattr__(self, 'capabilities', _flags(self.capabilities))
        object.__setattr__(self, 'observed_at', _observed(self.observed_at))


def user_profile(user: User, *, source: ProfileSource = 'update', observed_at: datetime | None = None) -> UserProfile:
    """Copy selected SDK facts. Neither the source tag nor Premium is authorization."""
    if not isinstance(user, User):
        raise InvalidType('Use an aiogram User observation')
    return UserProfile(
        user.id,
        user.is_bot,
        user.first_name,
        user.last_name,
        user.username,
        user.language_code,
        user.is_premium,
        {k: getattr(user, k) for k in _USER_FLAGS},
        source,
        datetime.now(timezone.utc) if observed_at is None else observed_at,
    )


@dataclass(frozen=True, slots=True)
class ChatProfile:
    id: int
    type: str
    title: str | None = field(repr=False)
    first_name: str | None = field(repr=False)
    last_name: str | None = field(repr=False)
    username: str | None = field(repr=False)
    bio: str | None = field(repr=False)
    description: str | None = field(repr=False)
    birthdate: tuple[int, int, int | None] | None = field(repr=False)
    emoji_status_custom_emoji_id: str | None = field(repr=False)
    emoji_status_expiration_date: datetime | None = field(repr=False)
    personal_chat_id: int | None
    photo: Mapping[str, str] | None = field(repr=False)
    permissions: Mapping[str, bool | None] | None = field(repr=False)
    facts: Mapping[str, bool | None] = field(repr=False)
    observed_at: datetime
    source: Literal['getChat'] = 'getChat'

    def __post_init__(self) -> None:
        _id(self.id, signed=True)
        if self.type not in ('private', 'group', 'supergroup', 'channel') or self.source != 'getChat':
            raise ValidationFailure('Use a native chat type and getChat observation')
        for value in (
            self.title,
            self.first_name,
            self.last_name,
            self.username,
            self.bio,
            self.description,
            self.emoji_status_custom_emoji_id,
        ):
            _text(value)
        if self.birthdate is not None:
            day, month, year = self.birthdate
            if (
                type(day) is not int
                or type(month) is not int
                or not 1 <= day <= 31
                or not 1 <= month <= 12
                or (year is not None and (type(year) is not int or not 1 <= year <= 9999))
            ):
                raise ValidationFailure('Invalid birthdate observation')
            object.__setattr__(self, 'birthdate', (day, month, year))
        if self.personal_chat_id is not None:
            _id(self.personal_chat_id, signed=True)
        if self.emoji_status_expiration_date is not None:
            object.__setattr__(self, 'emoji_status_expiration_date', _observed(self.emoji_status_expiration_date))
        if self.photo is not None:
            if not isinstance(self.photo, Mapping) or any(
                not isinstance(k, str) or not isinstance(v, str) for k, v in self.photo.items()
            ):
                raise InvalidType('Chat photo identifiers need a string mapping')
            object.__setattr__(self, 'photo', MappingProxyType(dict(self.photo)))
        if self.permissions is not None:
            object.__setattr__(self, 'permissions', _flags(self.permissions))
        object.__setattr__(self, 'facts', _flags(self.facts))
        object.__setattr__(self, 'observed_at', _observed(self.observed_at))


def chat_profile(chat: ChatFullInfo, *, observed_at: datetime | None = None) -> ChatProfile:
    """Selected getChat facts; default chat permissions are not an actor's role."""
    if not isinstance(chat, ChatFullInfo):
        raise InvalidType('Use aiogram ChatFullInfo from an explicit getChat')
    date = chat.birthdate
    return ChatProfile(
        chat.id,
        chat.type,
        chat.title,
        chat.first_name,
        chat.last_name,
        chat.username,
        chat.bio,
        chat.description,
        None if date is None else (date.day, date.month, date.year),
        chat.emoji_status_custom_emoji_id,
        chat.emoji_status_expiration_date,
        None if chat.personal_chat is None else chat.personal_chat.id,
        None if chat.photo is None else chat.photo.model_dump(),
        None if chat.permissions is None else chat.permissions.model_dump(),
        {k: getattr(chat, k) for k in _CHAT_FLAGS},
        datetime.now(timezone.utc) if observed_at is None else observed_at,
    )


@dataclass(frozen=True, slots=True)
class ProfilePhotoSize:
    bot_id: int
    user_id: int
    file_id: str = field(repr=False)
    file_unique_id: str = field(repr=False)
    width: int
    height: int
    file_size: int | None = None

    def __post_init__(self) -> None:
        _id(self.bot_id)
        _id(self.user_id)
        if any(type(n) is not int or n <= 0 for n in (self.width, self.height)) or (
            self.file_size is not None and (type(self.file_size) is not int or self.file_size < 0)
        ):
            raise ValidationFailure('Invalid profile photo dimensions or size')
        if (
            not isinstance(self.file_id, str)
            or not self.file_id
            or not isinstance(self.file_unique_id, str)
            or not self.file_unique_id
        ):
            raise ValidationFailure('Use observed file identifiers')

    def as_media(self) -> MediaFile:
        """Bot-scoped photo descriptor for message reuse; never a new avatar upload."""
        return MediaFile('photo', self.file_id, bot_id=self.bot_id)


@dataclass(frozen=True, slots=True)
class ProfilePhotos:
    bot_id: int
    user_id: int
    total_count: int
    offset: int
    limit: int
    photos: tuple[tuple[ProfilePhotoSize, ...], ...] = field(repr=False)
    observed_at: datetime

    def __post_init__(self) -> None:
        _id(self.bot_id)
        _id(self.user_id)
        if (
            type(self.total_count) is not int
            or self.total_count < 0
            or type(self.offset) is not int
            or self.offset < 0
            or type(self.limit) is not int
            or not 1 <= self.limit <= 100
        ):
            raise ValidationFailure('Use nonnegative counts/offset and 1..100 photo limit')
        photos = tuple(tuple(group) for group in self.photos)
        if (
            len(photos) > self.limit
            or len(photos) > max(0, self.total_count - self.offset)
            or any(
                not group
                or any(
                    not isinstance(p, ProfilePhotoSize) or p.bot_id != self.bot_id or p.user_id != self.user_id
                    for p in group
                )
                for group in photos
            )
        ):
            raise ValidationFailure('Profile photo page contradicts its observed scope/count')
        object.__setattr__(self, 'photos', photos)
        object.__setattr__(self, 'observed_at', _observed(self.observed_at))


async def read_profile_photos(bot: Bot, user_id: int, *, offset: int = 0, limit: int = 1) -> ProfilePhotos:
    """One explicit native read. Empty visible results do not prove absence of a private avatar."""
    _id(user_id)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationFailure('Use a nonnegative offset and 1..100 limit')
    result = await bot.get_user_profile_photos(user_id=user_id, offset=offset, limit=limit)
    photos = tuple(
        tuple(
            ProfilePhotoSize(bot.id, user_id, p.file_id, p.file_unique_id, p.width, p.height, p.file_size)
            for p in group
        )
        for group in result.photos
    )
    return ProfilePhotos(bot.id, user_id, result.total_count, offset, limit, photos, datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class BotProfile:
    user: UserProfile
    language_code: str
    name: str = field(repr=False)
    description: str = field(repr=False)
    short_description: str = field(repr=False)
    observed_at: datetime
    photos: ProfilePhotos | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.user, UserProfile) or not self.user.is_bot or self.user.source != 'getMe':
            raise ValidationFailure('Use a getMe bot observation')
        _locale(self.language_code)
        if self.photos is not None and (
            not isinstance(self.photos, ProfilePhotos)
            or self.photos.bot_id != self.user.id
            or self.photos.user_id != self.user.id
        ):
            raise ValidationFailure('Bot photo observation must belong to this own-bot scope')
        for value in (self.name, self.description, self.short_description):
            if not isinstance(value, str):
                raise InvalidType('Bot profile text must be str')
            _text(value)
        object.__setattr__(self, 'observed_at', _observed(self.observed_at))


async def read_bot_profile(bot: Bot, *, language_code: str = '', include_photos: bool = False) -> BotProfile:
    """Fresh getMe and three locale reads; no atomic snapshot or override-existence guarantee."""
    _locale(language_code)
    if type(include_photos) is not bool:
        raise InvalidType('Photo observation needs an explicit bool')
    user = user_profile(await bot.get_me(), source='getMe')
    if not user.is_bot or user.id != bot.id:
        raise PermissionDenied('Authenticated profile does not match the bot target')
    name = await bot.get_my_name(language_code=language_code)
    description = await bot.get_my_description(language_code=language_code)
    short = await bot.get_my_short_description(language_code=language_code)
    photos = await read_profile_photos(bot, user.id) if include_photos else None
    return BotProfile(
        user,
        language_code,
        name.name,
        description.description,
        short.short_description,
        datetime.now(timezone.utc),
        photos,
    )


@dataclass(frozen=True, slots=True)
class BotProfilePatch:
    name: str | None = field(default=None, repr=False)
    description: str | None = field(default=None, repr=False)
    short_description: str | None = field(default=None, repr=False)
    photo: MediaFile | None = field(default=None, repr=False)
    remove_photo: bool = False
    main_frame_timestamp: float | None = None

    def __post_init__(self) -> None:
        for value, maximum in ((self.name, 64), (self.description, 512), (self.short_description, 120)):
            _text(value)
            if value is not None and len(value) > maximum:
                raise ValidationFailure('Bot profile text exceeds the method character limit')
        if type(self.remove_photo) is not bool:
            raise InvalidType('Photo removal needs an explicit bool')
        if self.photo is not None:
            if (
                not isinstance(self.photo, MediaFile)
                or not isinstance(self.photo.reference, bytes)
                or self.photo.kind not in ('photo', 'video')
            ):
                raise ValidationFailure('New avatars require explicit uploaded photo/video bytes, never file_id')
            filename = self.photo.filename or ''
            if self.photo.kind == 'photo':
                if (
                    not filename.lower().endswith(('.jpg', '.jpeg'))
                    or not self.photo.reference.startswith(b'\xff\xd8\xff')
                    or not self.photo.reference.endswith(b'\xff\xd9')
                ):
                    raise ValidationFailure(
                        'Static avatar needs JPG bytes/filename; host still validates actual codec/content'
                    )
            elif not filename.lower().endswith('.mp4'):
                raise ValidationFailure(
                    'Animated avatar needs MPEG4 bytes/filename; host validates actual codec/content'
                )
        if self.remove_photo and self.photo is not None:
            raise ValidationFailure('Choose upload or removal, not both')
        if self.main_frame_timestamp is not None and (
            self.photo is None
            or self.photo.kind != 'video'
            or type(self.main_frame_timestamp) not in (int, float)
            or not math.isfinite(self.main_frame_timestamp)
            or self.main_frame_timestamp < 0
        ):
            raise ValidationFailure('Frame timestamp needs a finite nonnegative animated-video offset')
        if (
            all(value is None for value in (self.name, self.description, self.short_description, self.photo))
            and not self.remove_photo
        ):
            raise ValidationFailure('Select at least one field; None omits and empty string explicitly clears')


class ProfileEditIncomplete(UnknownOutcome):
    """Safe successful prefix and unconfirmed phase; no raw exception/profile payload."""

    def __init__(self, completed_methods: tuple[str, ...], pending_method: str) -> None:
        super().__init__('Profile edit needs an explicit read and reconciliation before another write')
        self.completed_methods = tuple(completed_methods)
        self.pending_method = pending_method


async def update_bot_profile(
    bot: Bot, patch: BotProfilePatch, *, actor_id: int, authorize: ProfileAuthorizer, language_code: str = ''
) -> BotProfile:
    """Own bot only, current host ACL per method, no automatic retries/rollback.

    Host owns serialization, authorization policy, caches and reconciliation.
    Cancellation propagates; cancelling a wait cannot undo a possible write.
    """
    if not isinstance(patch, BotProfilePatch) or not callable(authorize):
        raise InvalidType('Use BotProfilePatch and an async host authorizer')
    _id(actor_id)
    _locale(language_code)

    async def allowed(method: str) -> None:
        if await authorize(actor_id, bot.id, method) is not True:
            raise PermissionDenied('Current host permissions do not allow this profile operation')

    await allowed('read')
    identity = user_profile(await bot.get_me(), source='getMe')
    if not identity.is_bot or identity.id != bot.id:
        raise PermissionDenied('Authenticated profile does not match the own-bot target')
    completed: list[str] = []
    phase = 'prepare'
    try:
        for method, value in (
            ('setMyName', patch.name),
            ('setMyDescription', patch.description),
            ('setMyShortDescription', patch.short_description),
        ):
            if value is None:
                continue
            phase = 'authorize:' + method
            await allowed(method)
            phase = method
            if method == 'setMyName':
                success = await bot.set_my_name(name=value, language_code=language_code)
            elif method == 'setMyDescription':
                success = await bot.set_my_description(description=value, language_code=language_code)
            else:
                success = await bot.set_my_short_description(short_description=value, language_code=language_code)
            if success is not True:
                raise UnknownOutcome('Native profile write did not confirm success')
            completed.append(method)
        if patch.photo is not None or patch.remove_photo:
            method = 'removeMyProfilePhoto' if patch.remove_photo else 'setMyProfilePhoto'
            phase = 'authorize:' + method
            await allowed(method)
            phase = method
            if patch.photo is None:
                success = await bot.remove_my_profile_photo()
            elif patch.photo.kind == 'photo':
                success = await bot.set_my_profile_photo(
                    photo=InputProfilePhotoStatic(photo=patch.photo.as_input(bot.id))
                )
            else:
                success = await bot.set_my_profile_photo(
                    photo=InputProfilePhotoAnimated(
                        animation=patch.photo.as_input(bot.id), main_frame_timestamp=patch.main_frame_timestamp
                    )
                )
            if success is not True:
                raise UnknownOutcome('Native profile write did not confirm success')
            completed.append(method)
        phase = 'authorize:read-back'
        await allowed('read')
        phase = 'read-back'
        return await read_bot_profile(
            bot, language_code=language_code, include_photos=patch.photo is not None or patch.remove_photo
        )
    except Exception:
        if not completed and phase.startswith('authorize:'):
            raise
        raise ProfileEditIncomplete(tuple(completed), phase) from None
