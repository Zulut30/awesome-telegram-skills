"""Small private-chat text forms using the host's aiogram FSM and isolation."""

from __future__ import annotations

import inspect
import re
import secrets
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Awaitable, Callable, Mapping, Sequence

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import DisabledEventIsolation
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..errors import ErrorCode, InvalidCompletion, InvalidType, ValidationFailure
from .dialog_storage import _clear_form, _DialogData, _lifetime_data, _read_form, _save_form
from .fsm_storage import DialogLifetime


def _plain(text: str, limit: int) -> bool:
    try:
        return isinstance(text, str) and bool(text.strip()) and len(text.encode("utf-16-le")) // 2 <= limit
    except UnicodeError:
        return False


class InvalidField(ValidationFailure):
    """A bounded, user-facing validation message; never include secrets here."""

    code: ErrorCode = 'invalid-field'

    def __init__(self, message: str = "Проверьте значение и попробуйте ещё раз.") -> None:
        if not _plain(message, 256):
            raise ValidationFailure("Validation message must be nonempty plain text up to 256 UTF-16 units")
        super().__init__(message)


def _bot_id(message: Message) -> int:
    bot = message.bot
    if bot is None:
        raise RuntimeError('Forms require a Message bound to the current Bot')
    return bot.id


def _actor_id(message: Message) -> int:
    user = message.from_user
    if user is None:
        raise RuntimeError('Forms require a user author')
    return user.id


@dataclass(frozen=True, slots=True)
class TextField:
    name: str
    label: str
    prompt: str
    max_length: int = 128
    validate: Callable[[str], str] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", self.name):
            raise ValidationFailure("Field name must be 1..32 lowercase ASCII characters")
        if not _plain(self.label, 64) or not _plain(self.prompt, 512):
            raise ValidationFailure("Use a label up to 64 and a prompt up to 512 UTF-16 units")
        if type(self.max_length) is not int or not 1 <= self.max_length <= 256:
            raise ValidationFailure("Field max_length must be 1..256 UTF-16 units")
        if self.validate is not None and (
            not callable(self.validate)
            or inspect.iscoroutinefunction(self.validate)
            or inspect.iscoroutinefunction(getattr(self.validate, '__call__', None))
        ):
            raise InvalidType("Field validator must be a synchronous callable")

    def read(self, text: str) -> str:
        value = text.strip() if isinstance(text, str) else ""
        if not _plain(value, self.max_length):
            raise InvalidField(f"Введите от 1 до {self.max_length} символов.")
        if self.validate is not None:
            value = self.validate(value)
            if not _plain(value, self.max_length):
                raise ValidationFailure("Validator must return a bounded nonempty string")
        return value


@dataclass(frozen=True, slots=True)
class FormSubmission:
    """Server-derived identity and stable retry key; service still owns ACL/effect."""

    bot_id: int
    actor_id: int
    chat_id: int
    operation_id: str
    values: Mapping[str, str] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


def text_form_router(
    fields: Sequence[TextField],
    on_submit: Callable[[FormSubmission], Awaitable[str]],
    *,
    name: str = "application",
    command: str = "apply",
    schema_version: int = 1,
    lifetime: DialogLifetime | None = None,
) -> Router:
    """Private-chat form with review, /back, /cancel and explicit submit button.

    Host Dispatcher MUST have enabled FSM event isolation; defaults are rejected.
    Does not replace storage, register commands or persist business objects.
    on_submit must authorize and durably deduplicate using operation_id. Failure
    preserves that key and freezes edits/cancel/restart until the same operation
    is reconciled by retry. A successful return clears the form BEFORE feedback.
    With DialogLifetime the existing storage must support atomic snapshots;
    /apply resumes accepted answers without extending the original draft deadline.
    Version changes require explicit host migration; pending effects never expire.
    """
    steps = tuple(fields)
    if not 1 <= len(steps) <= 10 or any(not isinstance(item, TextField) for item in steps):
        raise ValidationFailure("Use 1..10 TextField items")
    if len({item.name for item in steps}) != len(steps):
        raise ValidationFailure("Field names must be unique")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,15}", name):
        raise ValidationFailure("Form name must be 1..16 lowercase ASCII characters")
    if not isinstance(command, str) or not re.fullmatch(r"[a-z0-9_]{1,32}", command) or command in {"back", "cancel"}:
        raise ValidationFailure("Use an ASCII command distinct from back/cancel, without '/'")
    if type(schema_version) is not int or not 1 <= schema_version <= 2**31 - 1:
        raise ValidationFailure("Use a positive bounded schema_version")
    if lifetime is not None and not isinstance(lifetime, DialogLifetime):
        raise InvalidType("Use DialogLifetime or None")
    if not callable(on_submit):
        raise InvalidType("on_submit must be an async callable")

    router = Router(name=f"text-form:{name}")
    namespace = f"telegram_patterns:form:{name}"
    data_key = "__telegram_patterns_form"
    prefix = f"form:{name}:"
    frozen_text = "Отправка уже началась. Нажмите «Отправить» в последней форме, чтобы проверить результат."
    stale_text = f"Кнопка устарела. Откройте актуальную форму командой /{command}."
    private = (
        (F.chat.type == "private")
        & F.business_connection_id.is_(None)
        & F.from_user.is_bot.is_(False)
        & F.message_thread_id.is_(None)
        & F.is_topic_message.is_not(True)
    )

    def require_fsm(dispatcher: Dispatcher, state: FSMContext | None, message: Message, actor: int) -> FSMContext:
        if state is None or isinstance(dispatcher.fsm.events_isolation, DisabledEventIsolation):
            raise RuntimeError("Text forms require enabled FSM and events_isolation on the existing Dispatcher")
        if (state.key.bot_id, state.key.chat_id, state.key.user_id) != (_bot_id(message), message.chat.id, actor):
            raise RuntimeError("Text forms require an actor-scoped FSM key")
        return state

    async def load(state: FSMContext, message: Message, actor: int) -> _DialogData | None:
        stored = await _read_form(state, namespace, data_key, lifetime)
        if stored is None:
            return None
        if (
            not isinstance(stored, dict)
            or stored.get("schema") != [step.name for step in steps]
            or type(stored.get("form_version", 1)) is not int
            or stored.get("form_version", 1) != schema_version
            or (lifetime is not None and "form_version" not in stored)
            or (lifetime is None and "lifetime" in stored)
            or stored.get("owner") != [_bot_id(message), message.chat.id, actor]
            or type(stored.get("index")) is not int
            or not 0 <= stored["index"] <= len(steps)
            or not isinstance(stored.get("values"), dict)
            or set(stored["values"]) != {step.name for step in steps[: stored["index"]]}
            or not isinstance(stored.get("operation_id"), str)
            or not re.fullmatch(r"[a-f0-9]{16}", stored["operation_id"])
            or type(stored.get("submission_started")) is not bool
            or type(stored.get("last_message_id")) is not int
            or (stored.get("review_message_id") is not None and type(stored["review_message_id"]) is not int)
            or any(not _plain(stored["values"][step.name], step.max_length) for step in steps[: stored["index"]])
        ):
            # Never silently reset potentially pending identity after a schema
            # change or storage corruption. The host must reconcile/migrate it.
            raise RuntimeError("Stored form requires reconciliation or a schema migration")
        if lifetime is not None and lifetime.expired(stored.get("lifetime")) and not stored["submission_started"]:
            await _clear_form(state, data_key, stored)
            await message.answer(f"Срок черновика истёк. Начать заново: /{command}.", parse_mode=None)
            return None
        return stored

    async def save(state: FSMContext, data: _DialogData) -> None:
        await _save_form(state, namespace, data_key, data)

    async def clear(state: FSMContext, data: _DialogData | None) -> None:
        await _clear_form(state, data_key, data)

    async def prompt(message: Message, index: int) -> None:
        await message.answer(
            f"Шаг {index + 1}/{len(steps)}. {steps[index].prompt}\n/back — назад · /cancel — отмена", parse_mode=None
        )

    async def review(message: Message, state: FSMContext, data: _DialogData) -> None:
        text = "Проверьте ответы:\n" + "\n".join(f"{step.label}: {data['values'][step.name]}" for step in steps)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Отправить", callback_data=f"{prefix}{data['operation_id']}:submit"),
                ]
            ]
        )
        data["review_message_id"] = None
        await save(state, data)  # Reject old review before a potentially unknown send.
        reply = await message.answer(
            text + "\n/back — исправить · /cancel — отмена", parse_mode=None, reply_markup=keyboard
        )
        data["review_message_id"] = reply.message_id
        await save(state, data)

    @router.message(private, StateFilter(None, namespace), Command(command))
    async def start(message: Message, dispatcher: Dispatcher, state: FSMContext | None = None) -> None:
        state = require_fsm(dispatcher, state, message, _actor_id(message))
        previous = await load(state, message, _actor_id(message))
        if previous is not None and previous["submission_started"]:
            await message.answer(frozen_text, parse_mode=None)
            return
        if previous is not None and message.message_id <= previous["last_message_id"]:
            return
        if lifetime is not None and previous is not None:
            previous["last_message_id"] = message.message_id
            await save(state, previous)
            if previous["index"] == len(steps):
                await review(message, state, previous)
            else:
                await prompt(message, previous["index"])
            return
        data = _DialogData(
            {
                "owner": [_bot_id(message), message.chat.id, _actor_id(message)],
                "schema": [step.name for step in steps],
                "values": {},
                "index": 0,
                "operation_id": secrets.token_hex(8),
                "submission_started": False,
                "review_message_id": None,
                "last_message_id": message.message_id,
                "form_version": schema_version,
                **_lifetime_data(lifetime),
            },
            previous.snapshot if previous is not None else None,
        )
        await save(state, data)
        await prompt(message, 0)

    @router.message(private, StateFilter(namespace), Command("cancel"))
    async def cancel(message: Message, dispatcher: Dispatcher, state: FSMContext | None = None) -> None:
        state = require_fsm(dispatcher, state, message, _actor_id(message))
        data = await load(state, message, _actor_id(message))
        if data is not None and data["submission_started"]:
            await message.answer(frozen_text, parse_mode=None)
            return
        if data is not None and message.message_id <= data["last_message_id"]:
            return
        await clear(state, data)
        await message.answer(f"Форма отменена. Начать заново: /{command}.", parse_mode=None)

    @router.message(private, StateFilter(namespace), Command("back"))
    async def back(message: Message, dispatcher: Dispatcher, state: FSMContext | None = None) -> None:
        state = require_fsm(dispatcher, state, message, _actor_id(message))
        data = await load(state, message, _actor_id(message))
        if data is None:
            await message.answer(stale_text, parse_mode=None)
            return
        if data["submission_started"]:
            await message.answer(frozen_text, parse_mode=None)
            return
        if message.message_id <= data["last_message_id"]:
            return
        data["index"] = max(0, data["index"] - 1)
        data["values"] = {step.name: data["values"][step.name] for step in steps[: data["index"]]}
        data.update(operation_id=secrets.token_hex(8), review_message_id=None, last_message_id=message.message_id)
        await save(state, data)
        await prompt(message, data["index"])

    @router.message(private, StateFilter(namespace), lambda event: not event.text or not event.text.startswith("/"))
    async def receive(message: Message, dispatcher: Dispatcher, state: FSMContext | None = None) -> None:
        state = require_fsm(dispatcher, state, message, _actor_id(message))
        data = await load(state, message, _actor_id(message))
        if data is None:
            await message.answer(stale_text, parse_mode=None)
            return
        if data["submission_started"]:
            await message.answer(frozen_text, parse_mode=None)
            return
        if message.message_id <= data["last_message_id"]:
            return
        if data["index"] == len(steps):
            await review(message, state, data)
            return
        try:
            value = steps[data["index"]].read(message.text)
        except InvalidField as error:
            await message.answer(str(error), parse_mode=None)
            await prompt(message, data["index"])
            return
        data["values"][steps[data["index"]].name] = value
        data["index"] += 1
        data["last_message_id"] = message.message_id
        await save(state, data)
        if data["index"] == len(steps):
            await review(message, state, data)
        else:
            await prompt(message, data["index"])

    @router.callback_query(F.data.startswith(prefix))
    async def submit(query: CallbackQuery, dispatcher: Dispatcher, state: FSMContext | None = None) -> None:
        # All matching callbacks, including inaccessible/foreign/stale ones, ACK.
        await query.answer()
        message = query.message
        if (
            not isinstance(message, Message)
            or message.chat.type != "private"
            or message.business_connection_id is not None
            or message.message_thread_id is not None
            or message.is_topic_message is True
            or query.from_user.is_bot
        ):
            return
        state = require_fsm(dispatcher, state, message, query.from_user.id)
        data = await load(state, message, query.from_user.id)
        if (
            data is None
            or data["index"] != len(steps)
            or message.message_id != data["review_message_id"]
            or query.data != f"{prefix}{data['operation_id']}:submit"
        ):
            await message.answer(stale_text, parse_mode=None)
            return
        data["submission_started"] = True
        await save(state, data)  # Keep stable identity even after unknown outcome.
        submission = FormSubmission(
            _bot_id(message), query.from_user.id, message.chat.id, data["operation_id"], data["values"]
        )
        try:
            text = await on_submit(submission)
            if not _plain(text, 4096):
                raise InvalidCompletion("on_submit must return nonempty plain text up to 4096 UTF-16 units")
        except Exception:
            await message.answer(
                "Результат отправки пока не подтверждён. Нажмите «Отправить» ещё раз для проверки той же заявки.",
                parse_mode=None,
            )
            raise  # Host error handling/observability, never raw errors in chat.
        await clear(state, data)
        await message.answer(text, parse_mode=None)

    return router
