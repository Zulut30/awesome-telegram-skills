"""Current poll/quiz requests and immutable, scoped observations of available updates."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Awaitable, Callable, Literal, Mapping, Sequence, TypeAlias, cast

from aiogram import Bot, F, Router
from aiogram.methods import SendPoll
from aiogram.types import (
    InputPollMediaUnion,
    InputPollOption,
    InputPollOptionMediaUnion,
    Message,
    MessageEntity,
    Poll,
    PollAnswer,
    Update,
)

from ..errors import InvalidType, PermissionDenied, ValidationFailure
from ..message_text import FormattedText, utf16_length
from .native_keyboards import ChatType

PollKind: TypeAlias = Literal['regular', 'quiz']
__all__ = [
    'PollKind',
    'PollChoice',
    'PollSpec',
    'PollOptionState',
    'PollState',
    'PollVote',
    'PollOptionAddition',
    'PollBinding',
    'PollLocator',
    'PollObservation',
    'PollEvent',
    'PollObserver',
    'PollLookup',
    'poll_request',
    'poll_state',
    'poll_vote',
    'poll_option_added',
    'poll_events_router',
]


def _integer(value: int, low: int = 0, high: int = 2**52 - 1) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValidationFailure('Expected a bounded integer')


def _id(value: int, *, signed: bool = False) -> None:
    if type(value) is not int or value == 0 or abs(value) >= 2**52 or not signed and value < 0:
        raise ValidationFailure('Expected a nonzero 52-bit ID in the required scope')


def _bool(value: bool) -> None:
    if type(value) is not bool:
        raise InvalidType('Expected bool')


def _text(value: str, maximum: int = 256, *, empty: bool = False) -> None:
    if not isinstance(value, str):
        raise InvalidType('Expected str')
    try:
        utf16_length(value)
    except ValueError:
        raise ValidationFailure('Poll text contains invalid Unicode') from None
    if not (0 if empty else 1) <= len(value) <= maximum:
        raise ValidationFailure('Poll text exceeds the declared character bound')


def _formatted(
    value: FormattedText | str, maximum: int, *, empty: bool = False, custom_only: bool = False
) -> FormattedText:
    result = FormattedText(value) if isinstance(value, str) else value
    if not isinstance(result, FormattedText):
        raise InvalidType('Use literal text or FormattedText')
    _text(result.text, maximum, empty=empty)
    if len(result.entities) > 100 or custom_only and any(e.kind != 'custom_emoji' for e in result.entities):
        raise ValidationFailure('Unsupported poll entities or local entity bound exceeded')
    return result


def _entities(value: FormattedText, entitlement: bool) -> list[MessageEntity]:
    return [
        MessageEntity.model_validate(entity.as_dict())
        for entity in value.entities
        if entity.kind != 'custom_emoji' or entitlement
    ]


def _sequence(value: Sequence[object], maximum: int = 1024) -> tuple[object, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) > maximum:
        raise ValidationFailure('Expected a bounded sequence')
    return tuple(value)


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValidationFailure('Poll time must be timezone-aware')
    return value.astimezone(timezone.utc)


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise InvalidType('Poll detail keys must be strings')
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise InvalidType('Poll details must contain immutable JSON-compatible values')


def _details(value: Poll) -> Mapping[str, object]:
    return cast(Mapping[str, object], _freeze(value.model_dump(mode='json')))


@dataclass(frozen=True, slots=True, init=False)
class PollChoice:
    text: FormattedText = field(repr=False)
    _media: InputPollOptionMediaUnion | None = field(repr=False)

    def __init__(self, text: FormattedText | str, *, media: InputPollOptionMediaUnion | None = None) -> None:
        result = _formatted(text, 100, custom_only=True)
        # Native union validation is performed by the SDK, without IO.
        checked = InputPollOption(text=result.text, text_parse_mode=None, media=media).media
        object.__setattr__(self, 'text', result)
        object.__setattr__(self, '_media', checked.model_copy(deep=True) if checked is not None else None)

    @property
    def media(self) -> InputPollOptionMediaUnion | None:
        return self._media.model_copy(deep=True) if self._media is not None else None


@dataclass(frozen=True, slots=True)
class PollSpec:
    question: FormattedText | str = field(repr=False)
    options: Sequence[PollChoice | FormattedText | str] = field(repr=False)
    kind: PollKind = 'regular'
    is_anonymous: bool = True
    allows_multiple_answers: bool = False
    allows_revoting: bool | None = None
    shuffle_options: bool = False
    allow_adding_options: bool = False
    hide_results_until_closes: bool = False
    members_only: bool = False
    country_codes: Sequence[str] | None = None
    correct_option_ids: Sequence[int] | None = None
    explanation: FormattedText | str | None = field(default=None, repr=False)
    description: FormattedText | str | None = field(default=None, repr=False)
    open_period: int | None = None
    close_date: datetime | None = None
    is_closed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, 'question', _formatted(self.question, 300, custom_only=True))
        options = tuple(
            value if isinstance(value, PollChoice) else PollChoice(cast(FormattedText | str, value))
            for value in _sequence(self.options, 12)
        )
        if not 1 <= len(options) <= 12:
            raise ValidationFailure('Current native polls require 1..12 initial options')
        object.__setattr__(self, 'options', options)
        if self.kind not in ('regular', 'quiz'):
            raise ValidationFailure('Unsupported poll kind')
        for value in (
            self.is_anonymous,
            self.allows_multiple_answers,
            self.shuffle_options,
            self.allow_adding_options,
            self.hide_results_until_closes,
            self.members_only,
            self.is_closed,
        ):
            _bool(value)
        if self.allows_revoting is not None:
            _bool(self.allows_revoting)
        if self.allow_adding_options and (self.is_anonymous or self.kind == 'quiz'):
            raise ValidationFailure('Adding options requires a non-anonymous regular poll')
        if self.correct_option_ids is not None:
            indices = tuple(cast(int, index) for index in _sequence(self.correct_option_ids, 12))
            for index in indices:
                _integer(index, 0, len(options) - 1)
            if not indices or list(indices) != sorted(set(indices)) or self.kind != 'quiz':
                raise ValidationFailure('Quiz answers must be nonempty, unique and monotonically increasing')
            object.__setattr__(self, 'correct_option_ids', indices)
        elif self.kind == 'quiz':
            raise ValidationFailure('Quiz requires correct_option_ids')
        if self.explanation is not None:
            explanation = _formatted(self.explanation, 200, empty=True)
            if self.kind != 'quiz' or explanation.text.count('\n') > 2:
                raise ValidationFailure('Quiz explanation permits at most two line feeds')
            object.__setattr__(self, 'explanation', explanation)
        if self.description is not None:
            object.__setattr__(self, 'description', _formatted(self.description, 1024, empty=True))
        if self.country_codes is not None:
            codes = _sequence(self.country_codes, 12)
            if any(not isinstance(code, str) or not re.fullmatch('[A-Z]{2}', code) for code in codes) or len(
                set(codes)
            ) != len(codes):
                raise ValidationFailure('Use unique uppercase two-letter country codes, including FT when needed')
            object.__setattr__(self, 'country_codes', codes)
        if self.open_period is not None:
            _integer(self.open_period, 5, 2628000)
        if self.close_date is not None:
            object.__setattr__(self, 'close_date', _aware(self.close_date))
        if self.open_period is not None and self.close_date is not None:
            raise ValidationFailure('open_period and close_date are mutually exclusive')


def poll_request(
    spec: PollSpec,
    *,
    chat_id: int | str,
    chat_type: ChatType = 'private',
    message_thread_id: int | None = None,
    business_connection_id: str | None = None,
    media: InputPollMediaUnion | None = None,
    explanation_media: InputPollMediaUnion | None = None,
    custom_emoji_entitlement_verified: bool = False,
    now: datetime | None = None,
) -> SendPoll:
    """One native request, no send/rights lookup; explicit SDK rich media stays host-owned."""
    if not isinstance(spec, PollSpec):
        raise InvalidType('Expected PollSpec')
    if isinstance(chat_id, str):
        if not re.fullmatch(r'@[A-Za-z0-9_]{5,32}', chat_id):
            raise ValidationFailure('Use an explicit numeric chat ID or validated username')
    else:
        _id(chat_id, signed=True)
    if chat_type not in ('private', 'group', 'supergroup', 'channel'):
        raise ValidationFailure('Unsupported poll destination context')
    if message_thread_id is not None:
        _id(message_thread_id)
        if chat_type not in ('private', 'supergroup'):
            raise ValidationFailure('Topics require a forum supergroup or private bot topic context')
    if business_connection_id is not None:
        _text(business_connection_id)
    _bool(custom_emoji_entitlement_verified)
    if (spec.members_only or spec.country_codes is not None) and chat_type != 'channel':
        raise ValidationFailure('Membership and country restrictions are channel-only')
    if explanation_media is not None and spec.kind != 'quiz':
        raise ValidationFailure('Explanation media requires a quiz')
    if spec.close_date is not None:
        deadline = (spec.close_date - _aware(datetime.now(timezone.utc) if now is None else now)).total_seconds()
        if not 5 <= deadline <= 2628000:
            raise ValidationFailure('Poll close date must be within 5..2628000 seconds')
    assert isinstance(spec.question, FormattedText)
    options: list[InputPollOption | str] = []
    for choice in spec.options:
        assert isinstance(choice, PollChoice)
        options.append(
            InputPollOption(
                text=choice.text.text,
                text_parse_mode=None,
                text_entities=_entities(choice.text, custom_emoji_entitlement_verified),
                media=choice.media,
            )
        )
    explanation = spec.explanation if isinstance(spec.explanation, FormattedText) else None
    description = spec.description if isinstance(spec.description, FormattedText) else None
    request = SendPoll(
        chat_id=chat_id,
        message_thread_id=message_thread_id,
        business_connection_id=business_connection_id,
        question=spec.question.text,
        question_parse_mode=None,
        question_entities=_entities(spec.question, custom_emoji_entitlement_verified),
        options=options,
        type=spec.kind,
        is_anonymous=spec.is_anonymous,
        allows_multiple_answers=spec.allows_multiple_answers,
        allows_revoting=spec.allows_revoting,
        shuffle_options=spec.shuffle_options,
        allow_adding_options=spec.allow_adding_options,
        hide_results_until_closes=spec.hide_results_until_closes,
        members_only=spec.members_only,
        country_codes=list(spec.country_codes) if spec.country_codes is not None else None,
        correct_option_ids=list(spec.correct_option_ids) if spec.correct_option_ids is not None else None,
        explanation=explanation.text if explanation is not None else None,
        explanation_parse_mode=None,
        explanation_entities=_entities(explanation, custom_emoji_entitlement_verified)
        if explanation is not None
        else None,
        description=description.text if description is not None else None,
        description_parse_mode=None,
        description_entities=_entities(description, custom_emoji_entitlement_verified)
        if description is not None
        else None,
        media=media,
        explanation_media=explanation_media,
        open_period=spec.open_period,
        close_date=spec.close_date,
        is_closed=spec.is_closed,
    )
    return request.model_copy(deep=True)


@dataclass(frozen=True, slots=True)
class PollOptionState:
    persistent_id: str = field(repr=False)
    text: str = field(repr=False)
    reported_voter_count: int

    def __post_init__(self) -> None:
        _text(self.persistent_id)
        _text(self.text, 100)
        _integer(self.reported_voter_count)


@dataclass(frozen=True, slots=True)
class PollState:
    poll_id: str = field(repr=False)
    options: tuple[PollOptionState, ...] = field(repr=False)
    reported_total_voter_count: int
    is_closed: bool
    is_anonymous: bool
    kind: PollKind
    allows_multiple_answers: bool
    allows_revoting: bool
    members_only: bool
    correct_option_ids: tuple[int, ...] | None
    details: Mapping[str, object] = field(repr=False)

    def __post_init__(self) -> None:
        _text(self.poll_id)
        if self.kind not in ('regular', 'quiz'):
            raise ValidationFailure('Unsupported poll kind')
        for flag in (
            self.is_closed,
            self.is_anonymous,
            self.allows_multiple_answers,
            self.allows_revoting,
            self.members_only,
        ):
            _bool(flag)
        _integer(self.reported_total_voter_count)
        options = tuple(_sequence(self.options))
        if not options or not all(isinstance(option, PollOptionState) for option in options):
            raise ValidationFailure('Invalid observed options')
        if len({option.persistent_id for option in self.options}) != len(options):
            raise ValidationFailure('Observed option identities must be unique')
        if self.correct_option_ids is not None:
            indices = tuple(cast(int, index) for index in _sequence(self.correct_option_ids))
            for index in indices:
                _integer(index, 0, len(options) - 1)
            if self.kind != 'quiz' or list(indices) != sorted(set(indices)):
                raise ValidationFailure('Invalid observed correct options')
            object.__setattr__(self, 'correct_option_ids', indices)
        object.__setattr__(self, 'options', options)
        object.__setattr__(self, 'details', cast(Mapping[str, object], _freeze(dict(self.details))))


def poll_state(value: Poll) -> PollState:
    if not isinstance(value, Poll):
        raise InvalidType('Expected native Poll')
    options = tuple(PollOptionState(option.persistent_id, option.text, option.voter_count) for option in value.options)
    return PollState(
        value.id,
        options,
        value.total_voter_count,
        value.is_closed,
        value.is_anonymous,
        cast(PollKind, value.type),
        value.allows_multiple_answers,
        value.allows_revoting,
        value.members_only,
        tuple(value.correct_option_ids) if value.correct_option_ids is not None else None,
        _details(value),
    )


@dataclass(frozen=True, slots=True)
class PollVote:
    poll_id: str = field(repr=False)
    option_ids: tuple[int, ...] = field(repr=False)
    option_persistent_ids: tuple[str, ...] = field(repr=False)
    voter_user_id: int | None = field(default=None, repr=False)
    voter_chat_id: int | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _text(self.poll_id)
        indices = tuple(_sequence(self.option_ids))
        persistent = tuple(_sequence(self.option_persistent_ids))
        for index in indices:
            _integer(cast(int, index), 0, 1023)
        for identity in persistent:
            _text(cast(str, identity))
        if (
            len(indices) != len(persistent)
            or len(set(indices)) != len(indices)
            or len(set(persistent)) != len(persistent)
        ):
            raise ValidationFailure('Vote option identities must be consistent and unique')
        if (self.voter_user_id is None) == (self.voter_chat_id is None):
            raise ValidationFailure('Vote must preserve exactly one native voter identity kind')
        if self.voter_user_id is not None:
            _id(self.voter_user_id)
        if self.voter_chat_id is not None:
            _id(self.voter_chat_id, signed=True)
        object.__setattr__(self, 'option_ids', indices)
        object.__setattr__(self, 'option_persistent_ids', persistent)

    @property
    def retracted(self) -> bool:
        return not self.option_persistent_ids


def poll_vote(value: PollAnswer) -> PollVote:
    if not isinstance(value, PollAnswer):
        raise InvalidType('Expected native PollAnswer')
    return PollVote(
        value.poll_id,
        tuple(value.option_ids),
        tuple(value.option_persistent_ids),
        value.user.id if value.user is not None else None,
        value.voter_chat.id if value.voter_chat is not None else None,
    )


@dataclass(frozen=True, slots=True)
class PollOptionAddition:
    persistent_id: str = field(repr=False)
    text: str = field(repr=False)
    poll_id: str | None = field(default=None, repr=False)
    chat_id: int | None = field(default=None, repr=False)
    message_id: int | None = None
    business_connection_id: str | None = field(default=None, repr=False)
    details: Mapping[str, object] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        _text(self.persistent_id)
        _text(self.text, 100)
        if self.poll_id is not None:
            _text(self.poll_id)
        if (self.chat_id is None) != (self.message_id is None):
            raise ValidationFailure('Poll address must be complete or absent')
        if self.chat_id is not None:
            _id(self.chat_id, signed=True)
            _id(cast(int, self.message_id))
        if self.business_connection_id is not None:
            _text(self.business_connection_id)
        object.__setattr__(self, 'details', cast(Mapping[str, object], _freeze(dict(self.details))))


def poll_option_added(message: Message) -> PollOptionAddition:
    if not isinstance(message, Message) or message.poll_option_added is None:
        raise InvalidType('Expected Message.poll_option_added')
    value = message.poll_option_added
    original = value.poll_message
    identity = original.poll.id if isinstance(original, Message) and original.poll is not None else None
    return PollOptionAddition(
        value.option_persistent_id,
        value.option_text,
        identity,
        original.chat.id if original is not None else None,
        original.message_id if original is not None else None,
        message.business_connection_id,
        cast(Mapping[str, object], _freeze(value.model_dump(mode='json'))),
    )


@dataclass(frozen=True, slots=True)
class PollBinding:
    bot_id: int
    poll_id: str = field(repr=False)
    chat_id: int = field(repr=False)
    message_id: int
    is_anonymous: bool
    kind: PollKind
    message_thread_id: int | None = None
    business_connection_id: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _id(self.bot_id)
        _text(self.poll_id)
        _id(self.chat_id, signed=True)
        _id(self.message_id)
        _bool(self.is_anonymous)
        if self.kind not in ('regular', 'quiz'):
            raise ValidationFailure('Unsupported poll kind')
        if self.message_thread_id is not None:
            _id(self.message_thread_id)
        if self.business_connection_id is not None:
            _text(self.business_connection_id)

    @classmethod
    def from_message(cls, message: Message, *, bot_id: int) -> PollBinding:
        """Host passes its own confirmed SendPoll response; an arbitrary DTO is not proof."""
        _id(bot_id)
        if not isinstance(message, Message) or message.poll is None or message.forward_origin is not None:
            raise PermissionDenied('Register only the own-bot SendPoll response')
        sender = message.sender_business_bot if message.business_connection_id else message.from_user
        if sender is not None and (sender.id != bot_id or not sender.is_bot):
            raise PermissionDenied('Poll sender does not match the registered bot')
        if sender is None and message.chat.type != 'channel':
            raise PermissionDenied('Own-bot response has no matching sender')
        state = poll_state(message.poll)
        return cls(
            bot_id,
            state.poll_id,
            message.chat.id,
            message.message_id,
            state.is_anonymous,
            state.kind,
            message.message_thread_id,
            message.business_connection_id,
        )


@dataclass(frozen=True, slots=True)
class PollLocator:
    bot_id: int
    poll_id: str | None = field(default=None, repr=False)
    chat_id: int | None = field(default=None, repr=False)
    message_id: int | None = None

    def __post_init__(self) -> None:
        _id(self.bot_id)
        if self.poll_id is not None:
            _text(self.poll_id)
        if (self.chat_id is None) != (self.message_id is None):
            raise ValidationFailure('Poll address must be complete')
        if self.chat_id is not None:
            _id(self.chat_id, signed=True)
            _id(cast(int, self.message_id))
        if self.poll_id is None and self.chat_id is None:
            raise ValidationFailure('Poll identity or exact address is required')


PollObservation: TypeAlias = PollState | PollVote | PollOptionAddition


@dataclass(frozen=True, slots=True)
class PollEvent:
    update_id: int
    binding: PollBinding = field(repr=False)
    observation: PollObservation = field(repr=False)

    def __post_init__(self) -> None:
        _integer(self.update_id)
        if not isinstance(self.binding, PollBinding) or not isinstance(
            self.observation, (PollState, PollVote, PollOptionAddition)
        ):
            raise InvalidType('Expected a binding and normalized poll observation')
        if self.observation.poll_id is not None and self.observation.poll_id != self.binding.poll_id:
            raise PermissionDenied('Poll observation does not match its binding')


PollObserver: TypeAlias = Callable[[PollEvent], Awaitable[None]]
PollLookup: TypeAlias = Callable[[PollLocator], Awaitable[PollBinding | None]]


def poll_events_router(lookup: PollLookup, observe: PollObserver) -> Router:
    """Fresh host binding per update; no vote counting, retry, hidden-voter inference or IO."""
    if not callable(lookup) or not callable(observe):
        raise InvalidType('Use async host lookup and observer')
    router = Router(name='pattern-poll-events')

    async def emit(observation: PollObservation, bot: Bot, update: Update, message: Message | None = None) -> None:
        if isinstance(observation, PollOptionAddition):
            if observation.chat_id is None or observation.message_id is None:
                return  # API omitted the poll address: do not guess an association.
            locator = PollLocator(bot.id, observation.poll_id, observation.chat_id, observation.message_id)
        else:
            locator = PollLocator(bot.id, observation.poll_id)
        binding = await lookup(locator)
        if binding is None:
            return
        if not isinstance(binding, PollBinding):
            raise InvalidType('Host lookup returned an invalid binding')
        if (
            binding.bot_id != bot.id
            or locator.poll_id is not None
            and locator.poll_id != binding.poll_id
            or locator.chat_id is not None
            and (locator.chat_id, locator.message_id) != (binding.chat_id, binding.message_id)
        ):
            return
        if isinstance(observation, PollState) and (
            observation.is_anonymous != binding.is_anonymous or observation.kind != binding.kind
        ):
            return
        if isinstance(observation, PollVote) and binding.is_anonymous:
            return
        if message is not None and (
            message.chat.id != binding.chat_id
            or message.message_thread_id != binding.message_thread_id
            or message.business_connection_id != binding.business_connection_id
        ):
            return
        await observe(PollEvent(update.update_id, binding, observation))

    @router.poll()
    async def state(value: Poll, bot: Bot, event_update: Update) -> None:
        await emit(poll_state(value), bot, event_update)

    @router.poll_answer()
    async def vote(value: PollAnswer, bot: Bot, event_update: Update) -> None:
        await emit(poll_vote(value), bot, event_update)

    async def addition(message: Message, bot: Bot, event_update: Update) -> None:
        await emit(poll_option_added(message), bot, event_update, message)

    router.message.register(addition, F.poll_option_added)
    router.business_message.register(addition, F.poll_option_added)
    return router
