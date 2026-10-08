"""Ephemeral messages in groups (Bot API 10.2+): when one may be sent, to whom, and how to edit or delete it.

An ephemeral message is visible only to one member of a group or supergroup and the bot. A bot that is not
an administrator answers within 15 seconds of the user's action and names it: the callback_query_id of a
button press or the ephemeral_message_id of an incoming ephemeral message (an ephemeral command). An
administrator bot may write to any non-bot member at any time. Delivery is never guaranteed, messages may
disappear, and an ephemeral_message_id can be reused after its message is deleted or expires.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .errors import ErrorCode, ValidationFailure

EPHEMERAL_WINDOW_SECONDS = 15
_GROUPS = ('group', 'supergroup')


class EphemeralNotAllowed(ValidationFailure):
    """The message cannot be ephemeral here; the reason is safe to log, the host picks another channel."""

    code: ErrorCode = 'validation-failed'


@dataclass(frozen=True, slots=True)
class EphemeralTrigger:
    """The user's action an ephemeral answer refers to, with the host clock time it was received."""

    kind: Literal['callback', 'ephemeral_message']
    received_at: float
    callback_query_id: str | None = None
    ephemeral_message_id: int | None = None
    from_ephemeral_message: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.received_at, bool) or not isinstance(self.received_at, (int, float)) or self.received_at < 0:
            raise ValidationFailure('received_at must be a nonnegative clock reading')
        if self.kind == 'callback':
            if (
                not isinstance(self.callback_query_id, str)
                or not self.callback_query_id
                or self.ephemeral_message_id is not None
            ):
                raise ValidationFailure('A callback trigger has a callback_query_id only')
        elif self.kind == 'ephemeral_message':
            if (
                type(self.ephemeral_message_id) is not int
                or self.ephemeral_message_id <= 0
                or self.callback_query_id is not None
            ):
                raise ValidationFailure('An ephemeral message trigger has a positive ephemeral_message_id only')
            if self.from_ephemeral_message:
                raise ValidationFailure('from_ephemeral_message describes callback triggers')
        else:
            raise ValidationFailure("Expected 'callback' or 'ephemeral_message'")
        if type(self.from_ephemeral_message) is not bool:
            raise ValidationFailure('from_ephemeral_message must be a boolean')

    @classmethod
    def callback(
        cls, callback_query_id: str, received_at: float, *, from_ephemeral_message: bool = False
    ) -> EphemeralTrigger:
        """A button press; from_ephemeral_message is True when the button sits on an ephemeral message."""
        return cls(
            'callback', received_at, callback_query_id=callback_query_id, from_ephemeral_message=from_ephemeral_message
        )

    @classmethod
    def reply_to(cls, ephemeral_message_id: int, received_at: float) -> EphemeralTrigger:
        """An incoming ephemeral message, for example an ephemeral command."""
        return cls('ephemeral_message', received_at, ephemeral_message_id=ephemeral_message_id)


def ephemeral_parameters(
    *,
    chat_type: str,
    receiver_user_id: int,
    receiver_is_bot: bool = False,
    bot_is_admin: bool = False,
    trigger: EphemeralTrigger | None = None,
    now: float,
    replace_original: bool = False,
) -> dict[str, Any]:
    """Keyword arguments to add to sendMessage and other send* methods, or EphemeralNotAllowed with the reason.

    The result holds ephemeral_message_parameters and, for an answer to an ephemeral message, reply_parameters.
    replace_original shows the answer in place of the pressed message; it needs a fresh callback trigger
    from an ordinary message. A trigger older than 15 seconds is still usable by an administrator bot, but then
    the answer is not tied to the triggering client and cannot replace a message.
    """
    if chat_type not in _GROUPS:
        raise EphemeralNotAllowed('Ephemeral messages exist only in groups and supergroups')
    if type(receiver_user_id) is not int or receiver_user_id <= 0:
        raise ValidationFailure('receiver_user_id must be a positive user id')
    for name, flag in (
        ('receiver_is_bot', receiver_is_bot),
        ('bot_is_admin', bot_is_admin),
        ('replace_original', replace_original),
    ):
        if type(flag) is not bool:
            raise ValidationFailure(f'{name} must be a boolean')
    if isinstance(now, bool) or not isinstance(now, (int, float)) or now < 0:
        raise ValidationFailure('now must be a nonnegative clock reading')
    if trigger is not None and not isinstance(trigger, EphemeralTrigger):
        raise ValidationFailure('Expected an EphemeralTrigger')
    if receiver_is_bot:
        raise EphemeralNotAllowed('An ephemeral message goes to a user, not to a bot')
    fresh = trigger is not None and 0 <= now - trigger.received_at <= EPHEMERAL_WINDOW_SECONDS
    if not fresh and not bot_is_admin:
        raise EphemeralNotAllowed('A bot that is not an administrator answers within 15 seconds of the user action')
    if replace_original:
        if trigger is None or trigger.kind != 'callback' or not fresh:
            raise EphemeralNotAllowed('Replacing a message needs a fresh button press')
        if trigger.from_ephemeral_message:
            raise EphemeralNotAllowed('A button on an ephemeral message is answered with editEphemeralMessage methods')
    parameters: dict[str, Any] = {'receiver_user_id': receiver_user_id}
    result: dict[str, Any] = {'ephemeral_message_parameters': parameters}
    if fresh and trigger is not None:
        if trigger.kind == 'callback':
            parameters['callback_query_id'] = trigger.callback_query_id
            if replace_original:
                parameters['replace_callback_query_message'] = True
        else:
            result['reply_parameters'] = {'ephemeral_message_id': trigger.ephemeral_message_id}
    return result


@dataclass(frozen=True, slots=True)
class EphemeralMessageRef:
    """Address of a sent ephemeral message for editEphemeralMessage* and deleteEphemeralMessage."""

    chat_id: int
    receiver_user_id: int
    ephemeral_message_id: int

    def __post_init__(self) -> None:
        if type(self.chat_id) is not int or self.chat_id >= 0:
            raise ValidationFailure('chat_id of a group or supergroup is negative')
        if type(self.receiver_user_id) is not int or self.receiver_user_id <= 0:
            raise ValidationFailure('receiver_user_id must be a positive user id')
        if type(self.ephemeral_message_id) is not int or self.ephemeral_message_id <= 0:
            raise ValidationFailure('ephemeral_message_id must be positive; a sent Message carries it, message_id is 0')

    def target(self) -> dict[str, int]:
        """chat_id, receiver_user_id and ephemeral_message_id for an edit or delete request."""
        return {
            'chat_id': self.chat_id,
            'receiver_user_id': self.receiver_user_id,
            'ephemeral_message_id': self.ephemeral_message_id,
        }
