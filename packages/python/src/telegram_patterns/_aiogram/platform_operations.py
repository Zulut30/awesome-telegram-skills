"""Scoped Bot API operations. Host policy and durable receipts are mandatory."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal, Protocol, cast
from urllib.parse import urlencode, urlsplit

from aiogram import Bot, F, Router
from aiogram.client.default import Default
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import TelegramMethod
from aiogram.types import (
    BufferedInputFile,
    ChatMemberRestricted,
    FSInputFile,
    InputFile,
    InputStoryContentPhoto,
    InputStoryContentVideo,
    ReactionTypeCustomEmoji,
    ReactionTypeEmoji,
    Update,
)
from pydantic import BaseModel

from ..errors import ConflictFailure, InvalidType, PermissionDenied, UnknownOutcome, ValidationFailure

__all__ = [
    'PlatformContract',
    'PlatformScope',
    'PlatformPermit',
    'PlatformAction',
    'PlatformReceipt',
    'PlatformResult',
    'PlatformHooks',
    'SecretToken',
    'PlatformEvent',
    'PlatformLookup',
    'PlatformObserver',
    'platform_contracts',
    'execute_platform_action',
    'managed_bot_link',
    'platform_event',
    'platform_events_router',
    'StoryPhotoUpload',
    'StoryVideoUpload',
]


class StoryPhotoUpload(InputStoryContentPhoto):
    """Validated multipart bridge for aiogram 3.31's string-only story field.

    The SDK's session.prepare_value supports InputFile in nested models. Its
    generated story type declares only the eventual attach:// string. This
    reviewed subclass validates an actual new upload before native serialization.
    """

    photo: BufferedInputFile | FSInputFile  # type: ignore[assignment]

    def __init__(self, *, photo: BufferedInputFile | FSInputFile) -> None:
        super().__init__(photo=cast(Any, photo))


class StoryVideoUpload(InputStoryContentVideo):
    """Validated fresh video multipart bridge; host still verifies native codec/dimensions."""

    video: BufferedInputFile | FSInputFile  # type: ignore[assignment]

    def __init__(
        self,
        *,
        video: BufferedInputFile | FSInputFile,
        duration: float | None = None,
        cover_frame_timestamp: float | None = None,
        is_animation: bool | None = None,
    ) -> None:
        super().__init__(
            video=cast(Any, video),
            duration=duration,
            cover_frame_timestamp=cover_frame_timestamp,
            is_animation=is_animation,
        )


def _integer(value: int, *, signed: bool = False, zero: bool = False) -> None:
    if (
        type(value) is not int
        or abs(value) > 2**52 - 1
        or value < (-(2**52 - 1) if signed else 0)
        or (not zero and value == 0)
    ):
        raise ValidationFailure('Use an integer in the declared ID/count scope')


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationFailure('Use an aware UTC observation/deadline')
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class PlatformContract:
    method: str
    family: Literal['topics', 'reactions', 'join', 'business', 'stories', 'gifts', 'managed']
    right: str | None = None
    write: bool = True
    financial: bool = False
    secret: bool = False
    source: str = ''
    checked_date: str = '2026-10-05'
    bot_api: str = '10.3'
    sdk: str = 'aiogram 3.31.0'
    verification: Literal['sdk'] = 'sdk'


_CONTRACTS: dict[str, PlatformContract] = {}


def _add(
    family: Any,
    names: str,
    right: str | None = None,
    *,
    write: bool = True,
    financial: bool = False,
    secret: bool = False,
) -> None:
    for name in names.split():
        _CONTRACTS[name] = PlatformContract(
            name, family, right, write, financial, secret, 'https://core.telegram.org/bots/api#' + name.lower()
        )


_add(
    'topics',
    'createForumTopic editForumTopic closeForumTopic reopenForumTopic editGeneralForumTopic closeGeneralForumTopic '
    'reopenGeneralForumTopic hideGeneralForumTopic unhideGeneralForumTopic',
    'can_manage_topics',
)
_add('topics', 'deleteForumTopic', 'can_delete_messages')
_add('topics', 'unpinAllForumTopicMessages unpinAllGeneralForumTopicMessages', 'can_pin_messages')
_add('topics', 'getForumTopicIconStickers', write=False)
_add('reactions', 'setMessageReaction')
_add('reactions', 'deleteMessageReaction deleteAllMessageReactions', 'can_delete_messages')
_add('join', 'approveChatJoinRequest declineChatJoinRequest', 'can_invite_users')
_add('join', 'answerChatJoinRequestQuery sendChatJoinRequestWebApp')
_add('business', 'getBusinessConnection', write=False)
_add('business', 'sendMessage sendPhoto editMessageText', 'can_reply')
_add('business', 'readBusinessMessage', 'can_read_messages')
_add('business', 'deleteBusinessMessages', 'can_delete_all_messages')
_add('business', 'setBusinessAccountName', 'can_edit_name')
_add('business', 'setBusinessAccountBio', 'can_edit_bio')
_add('business', 'setBusinessAccountUsername', 'can_edit_username')
_add('business', 'setBusinessAccountProfilePhoto removeBusinessAccountProfilePhoto', 'can_edit_profile_photo')
_add('business', 'setBusinessAccountGiftSettings', 'can_change_gift_settings')
_add('stories', 'postStory editStory deleteStory repostStory', 'can_manage_stories')
_add('gifts', 'getAvailableGifts getUserGifts getChatGifts', write=False)
_add('gifts', 'getBusinessAccountStarBalance getBusinessAccountGifts', 'can_view_gifts_and_stars', write=False)
_add('gifts', 'sendGift giftPremiumSubscription', financial=True)
_add('gifts', 'convertGiftToStars', 'can_convert_gifts_to_stars', financial=True)
_add('gifts', 'upgradeGift transferGift', 'can_transfer_and_upgrade_gifts', financial=True)
_add('gifts', 'transferBusinessAccountStars', 'can_transfer_stars', financial=True)
_add('managed', 'getManagedBotToken', write=False, secret=True)
_add('managed', 'replaceManagedBotToken', secret=True)
_add('managed', 'getManagedBotAccessSettings', write=False)
_add('managed', 'setManagedBotAccessSettings')


def platform_contracts() -> tuple[PlatformContract, ...]:
    """Closed native allowlist; SDK evidence is not proof of live permissions."""
    return tuple(_CONTRACTS.values())


@dataclass(frozen=True, slots=True)
class PlatformScope:
    bot_id: int
    actor_id: int
    operation_id: str = field(repr=False)
    revision: int = 0
    chat_id: int | None = None
    message_thread_id: int | None = None
    message_id: int | None = None
    business_connection_id: str | None = field(default=None, repr=False)
    owner_id: int | None = None
    child_bot_id: int | None = None
    subject_user_id: int | None = None
    join_query_id: str | None = field(default=None, repr=False)
    source_business_connection_id: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        value: Any
        for value in (self.bot_id, self.actor_id):
            _integer(value)
        _integer(self.revision, zero=True)
        for value in (self.owner_id, self.child_bot_id, self.subject_user_id, self.message_thread_id, self.message_id):
            if value is not None:
                _integer(value)
        if self.chat_id is not None:
            _integer(self.chat_id, signed=True)
        if not isinstance(self.operation_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', self.operation_id):
            raise ValidationFailure('Use a stable opaque operation ID, not a payload or token')
        for value in (self.business_connection_id, self.join_query_id, self.source_business_connection_id):
            if value is not None and (not isinstance(value, str) or not value or len(value) > 512):
                raise ValidationFailure('Use a bounded nonempty native scope identifier')
        if (self.business_connection_id is not None or self.child_bot_id is not None) and self.owner_id is None:
            raise ValidationFailure('Business and managed operations need a current owner binding')


@dataclass(frozen=True, slots=True)
class PlatformPermit:
    """Facts from current host policy, not claims supplied by a Telegram client."""

    allowed: bool = False
    topic_created_by_bot: bool = False
    existing_custom_reactions: tuple[str, ...] = field(default=(), repr=False)
    business_chat_eligible: bool = False
    messages_sent_by_bot: bool = False
    join_request_active: bool = False
    join_received_at: datetime | None = None
    financial_authorized: bool = False
    star_cost: int | None = None
    max_stars: int | None = None
    managed_bot_bound: bool = False
    source_story_posted_by_bot: bool = False
    story_media_verified: bool = False
    transfer_destination_active: bool = False

    def __post_init__(self) -> None:
        for name in (
            'allowed',
            'topic_created_by_bot',
            'business_chat_eligible',
            'messages_sent_by_bot',
            'join_request_active',
            'financial_authorized',
            'managed_bot_bound',
            'source_story_posted_by_bot',
            'story_media_verified',
            'transfer_destination_active',
        ):
            if type(getattr(self, name)) is not bool:
                raise InvalidType('Policy facts need explicit bool values')
        if self.join_received_at is not None:
            object.__setattr__(self, 'join_received_at', _aware(self.join_received_at))
        for value in (self.star_cost, self.max_stars):
            if value is not None:
                _integer(value, zero=True)
        values = tuple(self.existing_custom_reactions)
        if any(not isinstance(v, str) or not v.isascii() or not v.isdigit() for v in values):
            raise ValidationFailure('Use verified native custom reaction IDs')
        object.__setattr__(self, 'existing_custom_reactions', values)


def _canonical(value: Any) -> Any:
    if isinstance(value, BufferedInputFile):
        return {'upload_sha256': hashlib.sha256(value.data).hexdigest(), 'filename': value.filename}
    if isinstance(value, FSInputFile):
        return {'file_locator_sha256': hashlib.sha256(str(value.path).encode()).hexdigest(), 'filename': value.filename}
    if isinstance(value, InputFile):
        raise ValidationFailure('Use a host-verified buffered or stable filesystem upload')
    if isinstance(value, Default):
        return {'default': value.name}
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode='python', warnings=False))
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, str):
        try:
            value.encode('utf-8')
        except UnicodeError:
            raise ValidationFailure('Use valid Unicode scalars in the native action') from None
        return value
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise InvalidType('Unsupported value in native operation fingerprint')


@dataclass(frozen=True, slots=True, init=False)
class PlatformAction:
    scope: PlatformScope
    _request: TelegramMethod[Any] = field(repr=False)
    contract: PlatformContract = field(init=False)
    fingerprint: str = field(init=False, repr=False)

    def __init__(self, scope: PlatformScope, request: TelegramMethod[Any]) -> None:
        object.__setattr__(self, 'scope', scope)
        object.__setattr__(self, '_request', request)
        self.__post_init__()

    def __post_init__(self) -> None:
        if not isinstance(self.scope, PlatformScope) or not isinstance(self._request, TelegramMethod):
            raise InvalidType('Use a server scope and typed native aiogram request')
        request = self._request.model_copy(deep=True)
        if request.model_extra:
            raise ValidationFailure('Unknown SDK request extras require a reviewed contract update')
        contract = _CONTRACTS.get(request.__api_method__)
        if contract is None:
            raise ValidationFailure('Operation is outside the reviewed platform allowlist')
        # Reject arbitrary subclasses that replace make-request behavior or native return schemas.
        from aiogram import methods

        native = getattr(methods, type(request).__name__, None)
        if native is not type(request):
            raise InvalidType('Use the exact installed SDK method class')
        _binding(self.scope, request, contract)
        _parameters(request, contract)
        data = {
            'scope': {k: getattr(self.scope, k) for k in self.scope.__dataclass_fields__},
            'method': contract.method,
            'request': _canonical(request),
        }
        fingerprint = hashlib.sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest()
        object.__setattr__(self, '_request', request)
        object.__setattr__(self, 'contract', contract)
        object.__setattr__(self, 'fingerprint', fingerprint)

    @property
    def request(self) -> TelegramMethod[Any]:
        """A new native snapshot; modifying it does not change the authorized action."""
        return self._request.model_copy(deep=True)


def _binding(scope: PlatformScope, request: TelegramMethod[Any], contract: PlatformContract) -> None:
    for name, scoped in (
        ('chat_id', scope.chat_id),
        ('message_thread_id', scope.message_thread_id),
        ('message_id', scope.message_id),
        ('business_connection_id', scope.business_connection_id),
        ('chat_join_request_query_id', scope.join_query_id),
    ):
        value = getattr(request, name, None)
        if name in type(request).model_fields and value != scoped:
            raise PermissionDenied('Native target does not match the server operation scope')
    value = getattr(request, 'user_id', None)
    if value is not None and value != (scope.child_bot_id if contract.family == 'managed' else scope.subject_user_id):
        raise PermissionDenied('Native user/child ID does not match the server binding')
    if contract.family == 'managed' and (scope.child_bot_id is None or scope.child_bot_id == scope.bot_id):
        raise ValidationFailure('Use a separately bound child bot ID, not its human owner')
    if (
        contract.family == 'business'
        or contract.family == 'stories'
        or getattr(request, 'business_connection_id', None) is not None
    ):
        if scope.business_connection_id is None or scope.owner_id is None:
            raise ValidationFailure('Business operation needs connection and owner')
    if contract.family == 'join' and (scope.chat_id is None or scope.subject_user_id is None):
        raise ValidationFailure('Bind a join request to its actual chat and applicant')
    if contract.method == 'deleteBusinessMessages' and scope.chat_id is None:
        raise ValidationFailure('Bind message IDs to one known business chat')
    if contract.method == 'repostStory' and scope.source_business_connection_id is None:
        raise ValidationFailure('Repost needs the current source business connection')
    if contract.method in ('sendMessage', 'sendPhoto', 'editMessageText'):
        if scope.chat_id is None:
            raise ValidationFailure('Business send/edit needs an exact private chat binding')
        if any(
            getattr(request, name, None) is not None
            for name in (
                'inline_message_id',
                'direct_messages_topic_id',
                'ephemeral_message_parameters',
                'guest_query_id',
                'suggested_post_parameters',
            )
        ):
            raise ValidationFailure('Special launch/receiver modes need a separate reviewed operation contract')


def _parameters(request: TelegramMethod[Any], contract: PlatformContract) -> None:
    name = contract.method
    for key in ('message_id', 'message_thread_id', 'story_id', 'from_story_id'):
        value = getattr(request, key, None)
        if value is not None:
            _integer(value)
    if name in ('createForumTopic', 'editForumTopic', 'editGeneralForumTopic'):
        text = getattr(request, 'name', None)
        if text is not None and not (0 if name == 'editForumTopic' else 1) <= len(text) <= 128:
            raise ValidationFailure('Topic name is outside the native length contract')
        color = getattr(request, 'icon_color', None)
        if color is not None and color not in (7322096, 16766590, 13338331, 9367192, 16749490, 16478047):
            raise ValidationFailure('Unsupported native topic icon color')
    if name == 'setMessageReaction':
        reactions = getattr(request, 'reaction') or []
        if len(reactions) > 1 or any(r.type == 'paid' for r in reactions):
            raise ValidationFailure('Bots may set at most one non-paid reaction')
    if name in ('deleteMessageReaction', 'deleteAllMessageReactions'):
        if (getattr(request, 'user_id', None) is None) == (getattr(request, 'actor_chat_id', None) is None):
            raise ValidationFailure('Specify exactly one known user or actor chat')
        actor_chat = getattr(request, 'actor_chat_id', None)
        if actor_chat is not None:
            _integer(actor_chat, signed=True)
    if name == 'answerChatJoinRequestQuery' and getattr(request, 'result') not in ('approve', 'decline', 'queue'):
        raise ValidationFailure('Use a native join query decision')
    if name == 'sendChatJoinRequestWebApp':
        url = urlsplit(getattr(request, 'web_app_url'))
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
            raise ValidationFailure('Use a trusted HTTPS Mini App URL without embedded credentials')
    if name == 'deleteBusinessMessages':
        ids = getattr(request, 'message_ids')
        if not 1 <= len(ids) <= 100 or len(set(ids)) != len(ids):
            raise ValidationFailure('Delete 1..100 distinct messages from one verified chat')
        for value in ids:
            _integer(value)
    if name in ('postStory', 'repostStory') and getattr(request, 'active_period') not in (21600, 43200, 86400, 172800):
        raise ValidationFailure('Unsupported native story active period')
    if name in ('postStory', 'editStory'):
        content = getattr(request, 'content')
        media = getattr(content, 'photo', None) if content.type == 'photo' else getattr(content, 'video', None)
        if not isinstance(media, (BufferedInputFile, FSInputFile)):
            raise ValidationFailure('Story content must be a new upload, not a URL or reusable file_id')
        if (
            isinstance(media, BufferedInputFile)
            and len(media.data) > (10 if content.type == 'photo' else 30) * 1_000_000
        ):
            raise ValidationFailure('Story upload exceeds the native byte bound')
        duration = getattr(content, 'duration', None)
        if duration is not None and (not math.isfinite(duration) or not 0 <= duration <= 60):
            raise ValidationFailure('Story video duration must be finite and within 0..60 seconds')
        caption = getattr(request, 'caption') or ''
        if getattr(request, 'parse_mode') is not None:
            raise ValidationFailure('Use literal story captions and explicit caption_entities')
        if len(caption) > 2048:
            raise ValidationFailure('Story caption exceeds the native character bound')
    if name in ('sendMessage', 'sendPhoto', 'editMessageText') and getattr(request, 'parse_mode') is not None:
        raise ValidationFailure('Use literal business text/captions and explicit entities')
    if name in ('sendGift', 'giftPremiumSubscription'):
        if len(getattr(request, 'text', None) or '') > 128 or getattr(request, 'text_parse_mode') is not None:
            raise ValidationFailure('Use bounded literal gift text and explicit entities')
    if name == 'sendGift' and ((getattr(request, 'user_id') is None) == (getattr(request, 'chat_id') is None)):
        raise ValidationFailure('Send a gift to exactly one user or channel')
    if name == 'giftPremiumSubscription':
        costs = {3: 1000, 6: 1500, 12: 2500}
        if costs.get(getattr(request, 'month_count')) != getattr(request, 'star_count'):
            raise ValidationFailure('Premium duration and native Stars price do not match')
    if name in ('upgradeGift', 'transferGift', 'transferBusinessAccountStars'):
        cost = getattr(request, 'star_count', None)
        if cost is None:
            raise ValidationFailure('Declare a verified explicit gift charge, including zero')
        _integer(cost, zero=name != 'transferBusinessAccountStars')
        if name == 'transferBusinessAccountStars' and cost > 10000:
            raise ValidationFailure('Transfer at most 10000 Stars in one native operation')
    if name == 'setManagedBotAccessSettings':
        ids = getattr(request, 'added_user_ids') or []
        if len(ids) > 10 or len(set(ids)) != len(ids):
            raise ValidationFailure('Use at most 10 distinct additional users')
        for value in ids:
            _integer(value)


@dataclass(frozen=True, slots=True)
class PlatformReceipt:
    operation_id: str = field(repr=False)
    fingerprint: str = field(repr=False)
    method: str
    outcome: Literal['succeeded', 'rejected', 'unknown']
    result_id: int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.operation_id, str)
            or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', self.operation_id)
            or not isinstance(self.fingerprint, str)
            or not re.fullmatch(r'[a-f0-9]{64}', self.fingerprint)
            or self.method not in _CONTRACTS
            or self.outcome not in ('succeeded', 'rejected', 'unknown')
        ):
            raise ValidationFailure('Use an exact reviewed method and immutable operation receipt')
        if self.result_id is not None:
            _integer(self.result_id)


@dataclass(frozen=True, slots=True)
class SecretToken:
    """Repr-hidden native secret. Explicit reveal is only for the host secret store."""

    _value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self._value, str) or not re.fullmatch(r'[1-9][0-9]*:[A-Za-z0-9_-]{20,}', self._value):
            raise ValidationFailure('Invalid native managed bot token')

    def reveal(self) -> str:
        return self._value


@dataclass(frozen=True, slots=True)
class PlatformResult:
    receipt: PlatformReceipt
    value: object = field(repr=False)


class PlatformHooks(Protocol):
    async def authorize(self, action: PlatformAction) -> PlatformPermit:
        """Current actor ACL, exact target/message ownership, revision, consent and quote."""
        ...

    async def claim(self, action: PlatformAction, permit: PlatformPermit) -> bool:
        """Atomically recheck policy/budget and persist one sending intent before SDK I/O."""
        ...

    async def record(self, action: PlatformAction, receipt: PlatformReceipt) -> None:
        """Persist the receipt; a prior sending row remains unknown if the process dies."""
        ...


def _admin(member: Any, right: str) -> bool:
    return member.status == 'creator' or (member.status == 'administrator' and getattr(member, right, None) is True)


async def _membership(bot: Bot, chat_id: int) -> Any:
    member = await bot.get_chat_member(chat_id, bot.id)
    if member.user.id != bot.id:
        raise PermissionDenied('Membership response belongs to another bot')
    return member


async def _business(bot: Bot, connection_id: str, owner_id: int | None, right: str | None) -> Any:
    connection = await bot.get_business_connection(connection_id)
    if connection.id != connection_id or connection.user.id != owner_id or connection.is_enabled is not True:
        raise PermissionDenied('Business connection is revoked or belongs to another owner')
    if right is not None and (connection.rights is None or getattr(connection.rights, right, None) is not True):
        raise PermissionDenied('Required current business right is unavailable')
    return connection


def _join_time(permit: PlatformPermit, now: datetime) -> float:
    if not permit.join_request_active or permit.join_received_at is None:
        raise PermissionDenied('Join request needs a current host binding and native receive time')
    age = (now - permit.join_received_at).total_seconds()
    if age < 0 or age >= 10:
        raise PermissionDenied('Join query deadline expired or receive time is in the future')
    return 10 - age


async def _rights(
    bot: Bot, action: PlatformAction, request: TelegramMethod[Any], permit: PlatformPermit, now: datetime
) -> None:
    scope, contract = action.scope, action.contract
    name = contract.method
    if contract.family == 'topics' and name != 'getForumTopicIconStickers':
        chat = await bot.get_chat(scope.chat_id)  # type: ignore[arg-type]
        if chat.id != scope.chat_id:
            raise PermissionDenied('Telegram chat does not match the target')
        if chat.type == 'private':
            if name not in ('createForumTopic', 'editForumTopic', 'deleteForumTopic', 'unpinAllForumTopicMessages'):
                raise PermissionDenied('This topic method requires a forum supergroup')
            me = await bot.get_me()
            if me.id != bot.id or me.has_topics_enabled is not True:
                raise PermissionDenied('Private bot topics are not currently enabled')
        elif chat.type == 'supergroup' and chat.is_forum is True:
            member = await _membership(bot, chat.id)
            own = name in ('editForumTopic', 'closeForumTopic', 'reopenForumTopic') and permit.topic_created_by_bot
            if not _admin(member, contract.right or '') and not (
                own and member.status in ('member', 'administrator', 'creator')
            ):
                raise PermissionDenied('Required current forum right is unavailable')
        else:
            raise PermissionDenied('Use a forum supergroup or supported private topic operation')
        icon = getattr(request, 'icon_custom_emoji_id', None)
        if icon:
            stickers = await bot.get_forum_topic_icon_stickers()
            if not any(s.custom_emoji_id == icon for s in stickers):
                raise PermissionDenied('Topic icon is not in the current allowed sticker catalog')
    if contract.family == 'reactions':
        chat = await bot.get_chat(scope.chat_id)  # type: ignore[arg-type]
        if chat.id != scope.chat_id:
            raise PermissionDenied('Reaction chat mismatch')
        if name != 'setMessageReaction' and chat.type not in ('group', 'supergroup'):
            raise PermissionDenied('Reaction moderation requires a group or supergroup')
        if chat.type != 'private':
            member = await _membership(bot, chat.id)
            if contract.right:
                if not _admin(member, contract.right):
                    raise PermissionDenied('Reaction deletion right is unavailable')
            elif member.status not in ('creator', 'administrator'):
                allowed = (
                    member.can_react_to_messages
                    if isinstance(member, ChatMemberRestricted) and member.is_member
                    else getattr(chat.permissions, 'can_react_to_messages', None)
                    if member.status == 'member'
                    else False
                )
                if allowed is not True:
                    raise PermissionDenied('Current membership does not allow reactions')
        if name == 'setMessageReaction':
            for reaction in getattr(request, 'reaction') or []:
                available = chat.available_reactions
                if reaction.type == 'custom_emoji':
                    known = any(
                        isinstance(r, ReactionTypeCustomEmoji) and r.custom_emoji_id == reaction.custom_emoji_id
                        for r in available or []
                    )
                    if not known and reaction.custom_emoji_id not in permit.existing_custom_reactions:
                        raise PermissionDenied('Custom reaction needs current chat or message evidence')
                elif available is not None and not any(
                    isinstance(r, ReactionTypeEmoji) and r.emoji == reaction.emoji for r in available
                ):
                    raise PermissionDenied('Reaction is not available in the current chat')
    if contract.family == 'join':
        if not permit.join_request_active:
            raise PermissionDenied('Join request is no longer current')
        if scope.join_query_id is not None:
            if name not in ('answerChatJoinRequestQuery', 'sendChatJoinRequestWebApp'):
                raise ValidationFailure('Resolve an assigned query through its native query method')
            _join_time(permit, now)
            me = await bot.get_me()
            if me.id != bot.id or me.supports_join_request_queries is not True:
                raise PermissionDenied('Join request query support is not enabled')
        else:
            if name in ('answerChatJoinRequestQuery', 'sendChatJoinRequestWebApp'):
                raise ValidationFailure('Query operation requires the received query ID')
            member = await _membership(bot, scope.chat_id)  # type: ignore[arg-type]
            if not _admin(member, 'can_invite_users'):
                raise PermissionDenied('Join approval right is unavailable')
    if scope.business_connection_id is not None:
        right = contract.right
        if name == 'deleteBusinessMessages' and permit.messages_sent_by_bot:
            right = 'can_delete_sent_messages'
        await _business(bot, scope.business_connection_id, scope.owner_id, right)
        if (
            name in ('sendMessage', 'sendPhoto', 'editMessageText', 'readBusinessMessage')
            and not permit.business_chat_eligible
        ):
            raise PermissionDenied('Business chat must have current eligible recent activity')
        if name in ('sendMessage', 'sendPhoto', 'editMessageText', 'readBusinessMessage'):
            chat = await bot.get_chat(scope.chat_id)  # type: ignore[arg-type]
            if chat.id != scope.chat_id or chat.type != 'private':
                raise PermissionDenied('Eligible business messaging needs the exact private chat')
        if name == 'repostStory':
            source = await bot.get_business_connection(scope.source_business_connection_id)  # type: ignore[arg-type]
            if (
                source.id != scope.source_business_connection_id
                or not source.is_enabled
                or source.rights is None
                or source.rights.can_manage_stories is not True
                or source.user_chat_id != getattr(request, 'from_chat_id')
                or not permit.source_story_posted_by_bot
            ):
                raise PermissionDenied('Repost needs a managed source account and own confirmed story')
        if name in ('postStory', 'editStory') and not permit.story_media_verified:
            raise PermissionDenied('Host must verify story dimensions, codec, stable content and access')
        if name == 'transferGift' and not permit.transfer_destination_active:
            raise PermissionDenied('Gift destination must have verified recent activity')
        if name in ('upgradeGift', 'transferGift') and getattr(request, 'star_count') > 0:
            await _business(bot, scope.business_connection_id, scope.owner_id, 'can_transfer_stars')
    if contract.financial:
        if (
            not permit.financial_authorized
            or permit.star_cost is None
            or permit.max_stars is None
            or permit.star_cost > permit.max_stars
        ):
            raise PermissionDenied('Financial action needs current consent, quote and atomic host budget')
        cost = getattr(request, 'star_count', None)
        if cost is not None and cost != permit.star_cost:
            raise PermissionDenied('Native charge does not match the authorized quote')
        if name == 'convertGiftToStars' and permit.star_cost != 0:
            raise ValidationFailure('Gift conversion is irreversible but is not a Stars debit')
        if name == 'sendGift':
            gifts = await bot.get_available_gifts()
            gift = next((g for g in gifts.gifts if g.id == getattr(request, 'gift_id')), None)
            if gift is None or gift.remaining_count == 0 or gift.personal_remaining_count == 0:
                raise PermissionDenied('Gift is currently unavailable')
            if scope.chat_id is not None:
                chat = await bot.get_chat(scope.chat_id)
                if chat.id != scope.chat_id or chat.type != 'channel' or gift.total_count is not None:
                    raise PermissionDenied('Only an available unlimited gift can be sent to a channel')
            upgrade = gift.upgrade_star_count if getattr(request, 'pay_for_upgrade') else 0
            if upgrade is None or gift.star_count + upgrade != permit.star_cost:
                raise PermissionDenied('Current gift price does not match the authorized quote')
    if contract.family == 'managed':
        me = await bot.get_me()
        if me.id != bot.id or me.can_manage_bots is not True or not permit.managed_bot_bound:
            raise PermissionDenied('Manager capability and current owner/child binding are required')


async def execute_platform_action(
    bot: Bot, action: PlatformAction, hooks: PlatformHooks, *, timeout: float = 10.0
) -> PlatformResult:
    """Authorize/read rights/claim once/execute/record. Never retries a native effect."""
    if not isinstance(bot, Bot) or not isinstance(action, PlatformAction):
        raise InvalidType('Use the existing aiogram Bot and a server action')
    if bot.id != action.scope.bot_id:
        raise PermissionDenied('Operation belongs to another bot')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValidationFailure('Use a finite positive timeout')
    request = action.request
    deadline = asyncio.get_running_loop().time() + timeout
    async with asyncio.timeout_at(deadline):
        permit = await hooks.authorize(action)
        if not isinstance(permit, PlatformPermit) or permit.allowed is not True:
            raise PermissionDenied('Current host policy rejected the action')
        await _rights(bot, action, request, permit, datetime.now(timezone.utc))
        if action.contract.write:
            claimed = await hooks.claim(action, permit)
            if type(claimed) is not bool:
                raise InvalidType('Host claim must return an explicit bool')
            if not claimed:
                raise ConflictFailure('Existing intent requires explicit reconciliation, not another send')

        def receipt(outcome: Any, result_id: int | None = None) -> PlatformReceipt:
            return PlatformReceipt(
                action.scope.operation_id, action.fingerprint, action.contract.method, outcome, result_id
            )

        if action.scope.join_query_id is not None:
            try:
                _join_time(permit, datetime.now(timezone.utc))
            except PermissionDenied:
                try:
                    await hooks.record(action, receipt('rejected'))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    raise UnknownOutcome(
                        'Expired query receipt is unconfirmed; reconcile the existing intent'
                    ) from None
                raise
        try:
            remaining = deadline - asyncio.get_running_loop().time()
            if action.scope.join_query_id is not None:
                remaining = min(remaining, _join_time(permit, datetime.now(timezone.utc)))
            if remaining <= 0:
                raise TimeoutError('Native operation deadline expired')
            async with asyncio.timeout(remaining):
                value = await bot(request, request_timeout=max(1, math.ceil(remaining)))
            if value is False:
                raise TelegramBadRequest(request, 'Native API returned false')
            if action.contract.secret:
                secret = SecretToken(value)
                if int(secret.reveal().split(':', 1)[0]) != action.scope.child_bot_id:
                    raise ValidationFailure('Managed token belongs to another child bot')
                value = secret
            result_id = getattr(value, 'message_thread_id', None) or getattr(value, 'id', None)
            if type(result_id) is not int:
                result_id = None
        except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter):
            if action.contract.write:
                try:
                    await hooks.record(action, receipt('rejected'))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    raise UnknownOutcome(
                        'Native rejection receipt is unconfirmed; reconcile the existing intent'
                    ) from None
            raise PermissionDenied('Telegram explicitly rejected the native operation') from None
        except BaseException as error:
            if action.contract.write:
                try:
                    await hooks.record(action, receipt('unknown'))
                except BaseException:
                    pass  # Durable sending intent remains unknown after recorder failure.
                if not isinstance(error, asyncio.CancelledError):
                    raise UnknownOutcome('Native result is unconfirmed; reconcile the existing intent') from None
            raise
        outcome = receipt('succeeded', result_id)
        if action.contract.write:
            try:
                await hooks.record(action, outcome)
            except asyncio.CancelledError:
                raise
            except Exception:
                raise UnknownOutcome(
                    'Telegram replied but the durable receipt is unconfirmed; reconcile the same intent'
                ) from None
        return PlatformResult(outcome, value)


def managed_bot_link(manager_username: str, new_username: str, *, name: str | None = None) -> str:
    """Build the native user-confirmed flow; this function creates no bot or token."""
    for value in (manager_username, new_username):
        if (
            not isinstance(value, str)
            or not re.fullmatch(r'[A-Za-z0-9_]{5,32}', value)
            or not value.lower().endswith('bot')
        ):
            raise ValidationFailure('Use plain valid bot usernames without URLs or @ prefixes')
    if name is not None and (not isinstance(name, str) or not name or len(name) > 128):
        raise ValidationFailure('Use a bounded suggested display name')
    return f'https://t.me/newbot/{manager_username}/{new_username}' + (
        '?' + urlencode({'name': name}) if name is not None else ''
    )


_SERVICE_FIELDS = (
    'forum_topic_created',
    'forum_topic_edited',
    'forum_topic_closed',
    'forum_topic_reopened',
    'general_forum_topic_hidden',
    'general_forum_topic_unhidden',
    'story',
    'gift',
    'unique_gift',
    'managed_bot_created',
    'migrate_to_chat_id',
    'migrate_from_chat_id',
)
_UPDATE_FIELDS = (
    'message_reaction',
    'message_reaction_count',
    'chat_join_request',
    'business_connection',
    'business_message',
    'edited_business_message',
    'deleted_business_messages',
    'managed_bot',
)


@dataclass(frozen=True, slots=True)
class PlatformEvent:
    bot_id: int
    update_id: int
    kind: str
    chat_id: int | None = None
    message_thread_id: int | None = None
    message_id: int | None = None
    source_user_id: int | None = None
    source_chat_id: int | None = None
    business_connection_id: str | None = field(default=None, repr=False)
    owner_id: int | None = None
    child_bot_id: int | None = None
    join_query_id: str | None = field(default=None, repr=False)
    details_json: str = field(default='{}', repr=False)


PlatformLookup = Callable[[PlatformEvent], Awaitable[PlatformScope | None]]
PlatformObserver = Callable[[PlatformEvent, PlatformScope], Awaitable[None]]


def platform_event(update: Update, *, bot_id: int) -> PlatformEvent | None:
    """Immutable available native observation. Identity/count/owner facts grant no ACL."""
    _integer(bot_id)
    if not isinstance(update, Update):
        raise InvalidType('Use a native aiogram Update')
    kinds = [k for k in type(update).model_fields if k != 'update_id' and getattr(update, k) is not None]
    if len(kinds) != 1:
        return None
    kind = kinds[0]
    value = getattr(update, kind)
    if kind == 'message':
        services = [k for k in _SERVICE_FIELDS if getattr(value, k, None) is not None]
        if not services:
            return None
        kind = services[0]
    elif kind not in _UPDATE_FIELDS:
        return None
    chat = getattr(value, 'chat', None)
    user = getattr(value, 'from_user', None) or getattr(value, 'user', None)
    actor_chat = getattr(value, 'sender_chat', None) or getattr(value, 'actor_chat', None)
    connection = value.id if kind == 'business_connection' else getattr(value, 'business_connection_id', None)
    child = getattr(value, 'bot_user', None)
    if kind == 'managed_bot_created':
        child = value.managed_bot_created.bot_user
    return PlatformEvent(
        bot_id,
        update.update_id,
        kind,
        getattr(chat, 'id', None),
        getattr(value, 'message_thread_id', None),
        getattr(value, 'message_id', None),
        None if actor_chat is not None else getattr(user, 'id', None),
        getattr(actor_chat, 'id', None),
        connection,
        value.user.id if kind in ('business_connection', 'managed_bot') else None,
        getattr(child, 'id', None),
        getattr(value, 'query_id', None),
        value.model_dump_json(),
    )


def platform_events_router(lookup: PlatformLookup, observe: PlatformObserver) -> Router:
    """Fresh host binding per observation; host owns durable dedup/order/revocation."""
    if not callable(lookup) or not callable(observe):
        raise InvalidType('Use async host lookup and observer')
    router = Router(name='pattern-platform-events')

    async def emit(value: Any, bot: Bot, event_update: Update) -> None:
        event = platform_event(event_update, bot_id=bot.id)
        if event is None:
            return
        scope = await lookup(event)
        if scope is None:
            return
        if not isinstance(scope, PlatformScope):
            raise InvalidType('Host returned an invalid event binding')
        if scope.bot_id != event.bot_id:
            return
        for key in (
            'chat_id',
            'message_thread_id',
            'business_connection_id',
            'owner_id',
            'child_bot_id',
            'join_query_id',
        ):
            actual = getattr(event, key)
            if actual is not None and actual != getattr(scope, key):
                return
        if scope.message_id is not None and event.message_id is not None and scope.message_id != event.message_id:
            return
        await observe(event, scope)

    for kind in _UPDATE_FIELDS:
        router.observers[kind].register(emit)
    router.message.register(emit, F.func(lambda m: any(getattr(m, k, None) is not None for k in _SERVICE_FIELDS)))
    return router
