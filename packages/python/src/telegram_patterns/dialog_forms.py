"""Mixed private-chat forms on the host FSM; author/step guards before values."""

from __future__ import annotations

import json
import math
import re
import secrets
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Awaitable, Callable, Mapping, Sequence, TypeAlias

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import DisabledEventIsolation
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from ._dialog_storage import _clear_form, _DialogData, _lifetime_data, _read_form, _save_form
from .dialog_fields import (
    ContactField,
    DateField,
    EmailField,
    FieldValue,
    FileField,
    LocationField,
    NumberField,
    PhoneField,
    _Field,
)
from .errors import InvalidCompletion, InvalidType, ValidationFailure
from .forms import InvalidField, TextField, _actor_id, _bot_id, _plain
from .fsm_storage import DialogLifetime
from .native_keyboards import input_prompt, remove_keyboard, reply_keyboard

_Step: TypeAlias = (
    TextField | NumberField | EmailField | PhoneField | DateField | FileField | ContactField | LocationField
)


@dataclass(frozen=True, slots=True)
class DialogSubmission:
    """Server identity and immutable JSON-compatible values; no implicit effect."""

    bot_id: int
    actor_id: int
    chat_id: int
    operation_id: str
    values: Mapping[str, FieldValue] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.values, Mapping) or not 1 <= len(self.values) <= 10:
            raise ValidationFailure('Use 1..10 flat dialog values')
        snapshot: dict[str, FieldValue] = {}
        for key, value in self.values.items():
            if not isinstance(key, str) or not re.fullmatch('[a-z][a-z0-9_]{0,31}', key):
                raise ValidationFailure('Use bounded dialog field names')
            if isinstance(value, str) and _plain(value, 1024):
                snapshot[key] = value
            elif isinstance(value, Mapping) and 1 <= len(value) <= 5:
                for metadata_key, item in value.items():
                    if (
                        not isinstance(metadata_key, str)
                        or not re.fullmatch('[a-z][a-z0-9_]{0,31}', metadata_key)
                        or type(item) not in (str, int, float, type(None))
                        or (isinstance(item, str) and not _plain(item, 1024))
                        or (type(item) is int and not -(2**63) <= item <= 2**63 - 1)
                        or (type(item) is float and not math.isfinite(item))
                    ):
                        raise ValidationFailure('Use flat finite JSON metadata, without nested objects')
                snapshot[key] = MappingProxyType(dict(value))
            else:
                raise ValidationFailure('Use bounded strings or flat JSON metadata')
        object.__setattr__(self, 'values', MappingProxyType(snapshot))

    def as_dict(self) -> dict[str, FieldValue]:
        """Fresh JSON values for the host's durable transaction, never credentials."""
        return {key: dict(value) if isinstance(value, Mapping) else value for key, value in self.values.items()}


def dialog_form_router(
    fields: Sequence[_Step],
    on_submit: Callable[[DialogSubmission], Awaitable[str]],
    *,
    name: str = 'details',
    command: str = 'collect',
    schema_version: int = 1,
    lifetime: DialogLifetime | None = None,
) -> Router:
    """Mixed fields with reply correlation, native candidate confirmation and review.

    Requires the existing Dispatcher FSM and actor-scoped event isolation. Native
    contact/location inputs cannot prove which keyboard generated them; the user
    confirms a bounded candidate on an actor/step/message-bound inline button.
    Host still owns current ACL, durable operation_id deduplication, retention,
    FSM persistence and recovery of unknown effects. Never resets pending effects.
    """
    steps = tuple(fields)
    if not 1 <= len(steps) <= 10 or any(
        not isinstance(
            s, (TextField, NumberField, EmailField, PhoneField, DateField, FileField, ContactField, LocationField)
        )
        for s in steps
    ):
        raise ValidationFailure('Use 1..10 supported dialog fields')
    if len({s.name for s in steps}) != len(steps):
        raise ValidationFailure('Field names must be unique')
    if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,15}', name):
        raise ValidationFailure('Use a 1..16 lowercase ASCII form name')
    if not isinstance(command, str) or not re.fullmatch(r'[a-z0-9_]{1,32}', command) or command in {'back', 'cancel'}:
        raise ValidationFailure('Use an ASCII command distinct from back/cancel')
    if type(schema_version) is not int or not 1 <= schema_version <= 2**31 - 1:
        raise ValidationFailure('Use a positive bounded schema_version')
    if lifetime is not None and not isinstance(lifetime, DialogLifetime):
        raise InvalidType("Use DialogLifetime or None")
    if not callable(on_submit):
        raise InvalidType('on_submit must be an async callable')
    signatures = [
        s.signature()
        if isinstance(s, _Field)
        else json.dumps(
            {'kind': 'text', 'name': s.name, 'label': s.label, 'prompt': s.prompt, 'max_length': s.max_length},
            sort_keys=True,
        )
        for s in steps
    ]
    schema = [schema_version, *signatures]
    router = Router(name=f'dialog-form:{name}')
    namespace, data_key, prefix = f'telegram_patterns:dialog:{name}', '__telegram_patterns_dialog', f'dlg:{name}:'
    private = (
        (F.chat.type == 'private')
        & F.business_connection_id.is_(None)
        & F.from_user.is_bot.is_(False)
        & F.message_thread_id.is_(None)
        & F.is_topic_message.is_not(True)
    )
    frozen_text = 'Отправка уже началась. Нажмите «Отправить» в последней форме, чтобы проверить результат.'
    stale_text = f'Действие устарело. Откройте текущий вопрос командой /{command}.'

    def require(dispatcher: Dispatcher, state: FSMContext | None, message: Message, actor: int) -> FSMContext:
        if state is None or isinstance(dispatcher.fsm.events_isolation, DisabledEventIsolation):
            raise RuntimeError('Dialogs require enabled FSM and events_isolation on the existing Dispatcher')
        if (state.key.bot_id, state.key.chat_id, state.key.user_id) != (_bot_id(message), message.chat.id, actor):
            raise RuntimeError('Dialogs require an actor-scoped FSM key')
        return state

    def restore(step: _Step, value: object, actor: int) -> FieldValue:
        if isinstance(step, TextField):
            if not isinstance(value, str) or not _plain(value, step.max_length):
                raise InvalidField()
            return value  # Custom validators run once at input, never during replay.
        result = step.restore(value)
        if isinstance(step, ContactField) and step.own and isinstance(result, Mapping) and result['user_id'] != actor:
            raise InvalidField('Поделитесь своим контактом через кнопку.')
        return result

    def positive(value: object) -> bool:
        return type(value) is int and 0 < value <= 2**63 - 1

    async def load(state: FSMContext, message: Message, actor: int) -> _DialogData | None:
        stored = await _read_form(state, namespace, data_key, lifetime)
        if stored is None:
            return None
        try:
            if (
                not isinstance(stored, dict)
                or set(stored)
                != {
                    'schema',
                    'owner',
                    'index',
                    'values',
                    'operation_id',
                    'submission_started',
                    'last_message_id',
                    'prompt_message_id',
                    'review_message_id',
                    'candidate',
                    'keyboard_active',
                }
                | ({'lifetime'} if lifetime is not None else set())
                or stored['schema'] != schema
                or stored['owner'] != [_bot_id(message), message.chat.id, actor]
                or type(stored['index']) is not int
                or not 0 <= stored['index'] <= len(steps)
                or not isinstance(stored['values'], dict)
                or set(stored['values']) != {s.name for s in steps[: stored['index']]}
                or not isinstance(stored['operation_id'], str)
                or not re.fullmatch('[a-f0-9]{32}', stored['operation_id'])
                or type(stored['submission_started']) is not bool
                or type(stored['keyboard_active']) is not bool
                or not positive(stored['last_message_id'])
                or any(
                    stored[k] is not None and not positive(stored[k])
                    for k in ('prompt_message_id', 'review_message_id')
                )
                or (
                    stored['submission_started']
                    and (stored['index'] != len(steps) or stored['review_message_id'] is None)
                )
            ):
                raise ValueError
            for step in steps[: stored['index']]:
                if restore(step, stored['values'][step.name], actor) != stored['values'][step.name]:
                    raise ValueError
            candidate = stored['candidate']
            if candidate is not None:
                if (
                    stored['index'] == len(steps)
                    or not isinstance(steps[stored['index']], (ContactField, LocationField))
                    or not isinstance(candidate, dict)
                    or set(candidate) != {'value', 'nonce', 'message_id'}
                    or not isinstance(candidate['nonce'], str)
                    or not re.fullmatch('[a-f0-9]{8}', candidate['nonce'])
                    or (candidate['message_id'] is not None and not positive(candidate['message_id']))
                    or restore(steps[stored['index']], candidate['value'], actor) != candidate['value']
                ):
                    raise ValueError
        except (ValueError, TypeError, KeyError, OverflowError):
            raise RuntimeError('Stored dialog requires reconciliation or a schema migration') from None
        if lifetime is not None and lifetime.expired(stored.get("lifetime")) and not stored["submission_started"]:
            await _clear_form(state, data_key, stored)
            await message.answer(
                f"Срок черновика истёк. Начать заново: /{command}.", parse_mode=None, reply_markup=remove_keyboard()
            )
            return None
        return stored

    async def save(state: FSMContext, data: _DialogData) -> None:
        await _save_form(state, namespace, data_key, data)

    async def clear(state: FSMContext, data: _DialogData | None) -> None:
        await _clear_form(state, data_key, data)

    def sent_id(reply: Message, message: Message) -> int:
        if not positive(reply.message_id) or reply.chat.id != message.chat.id:
            raise RuntimeError('Expected a prompt in the current chat')
        return reply.message_id

    def keyboard(data: _DialogData, action: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Подтвердить' if action.startswith('v:') else 'Отправить',
                        callback_data=f"{prefix}{data['operation_id']}:{action}",
                    )
                ]
            ]
        )

    async def remove(message: Message, state: FSMContext, data: _DialogData) -> None:
        if data['keyboard_active']:
            await message.answer('Клавиатура ввода закрыта.', parse_mode=None, reply_markup=remove_keyboard())
            data['keyboard_active'] = False
            await save(state, data)

    def display(step: _Step, value: FieldValue) -> str:
        text = str(value) if isinstance(step, TextField) else step.display(value)
        # Bounded plain text; user metadata cannot overflow Telegram's 4096 units.
        return text if _plain(text, 280) else text[:120] + '…'

    async def show(message: Message, state: FSMContext, data: _DialogData) -> None:
        data.update(prompt_message_id=None, review_message_id=None, candidate=None)
        await save(state, data)  # Invalidate old UI before a potentially unknown send.
        if data['index'] == len(steps):
            await remove(message, state, data)
            text = 'Проверьте ответы:\n' + '\n'.join(f"{s.label}: {display(s, data['values'][s.name])}" for s in steps)
            reply = await message.answer(
                text + '\n/back — исправить · /cancel — отмена', parse_mode=None, reply_markup=keyboard(data, 'submit')
            )
            data['review_message_id'] = sent_id(reply, message)
        else:
            step = steps[data['index']]
            markup: ForceReply | ReplyKeyboardMarkup = input_prompt()
            if isinstance(step, (ContactField, LocationField)):
                data['keyboard_active'] = True  # Preserve cleanup even if send result is unknown.
                await save(state, data)
                button = KeyboardButton(
                    text='Поделиться контактом' if isinstance(step, ContactField) else 'Поделиться геопозицией',
                    request_contact=True if isinstance(step, ContactField) else None,
                    request_location=True if isinstance(step, LocationField) else None,
                )
                markup = reply_keyboard([[button]], chat_type='private', one_time=True)
            else:
                await remove(message, state, data)
            reply = await message.answer(
                f"Шаг {data['index'] + 1}/{len(steps)}. {step.prompt}\n/back — назад · /cancel — отмена",
                parse_mode=None,
                reply_markup=markup,
            )
            data['prompt_message_id'] = sent_id(reply, message)
        await save(state, data)

    @router.message(private, StateFilter(None, namespace), Command(command))
    async def start(message: Message, dispatcher: Dispatcher, state: FSMContext | None = None) -> None:
        state = require(dispatcher, state, message, _actor_id(message))
        data = await load(state, message, _actor_id(message))
        if data is not None and data['submission_started']:
            await message.answer(frozen_text, parse_mode=None)
            return
        if data is not None and message.message_id <= data['last_message_id']:
            return
        if data is None:
            data = _DialogData(
                {
                    'schema': schema,
                    'owner': [_bot_id(message), message.chat.id, _actor_id(message)],
                    'index': 0,
                    'values': {},
                    'operation_id': secrets.token_hex(16),
                    'submission_started': False,
                    'last_message_id': message.message_id,
                    'prompt_message_id': None,
                    'review_message_id': None,
                    'candidate': None,
                    'keyboard_active': False,
                    **_lifetime_data(lifetime),
                }
            )
            await save(state, data)
        data['last_message_id'] = message.message_id
        await show(message, state, data)  # Explicit resume keeps accepted answers and intent.

    @router.message(private, StateFilter(namespace), Command('back', 'cancel'))
    async def navigate(message: Message, dispatcher: Dispatcher, state: FSMContext | None = None) -> None:
        state = require(dispatcher, state, message, _actor_id(message))
        data = await load(state, message, _actor_id(message))
        if data is None:
            return
        if data['submission_started']:
            await message.answer(frozen_text, parse_mode=None)
            return
        if message.message_id <= data['last_message_id']:
            return
        data['last_message_id'] = message.message_id
        if message.text and message.text.split()[0].split('@')[0] == '/cancel':
            await remove(message, state, data)
            await clear(state, data)
            await message.answer(f'Форма отменена. Начать заново: /{command}.', parse_mode=None)
            return
        data['index'] = max(0, data['index'] - 1)
        data['values'] = {s.name: data['values'][s.name] for s in steps[: data['index']]}
        data['operation_id'] = secrets.token_hex(16)
        await show(message, state, data)

    @router.message(private, StateFilter(namespace), lambda event: not event.text or not event.text.startswith('/'))
    async def receive(message: Message, dispatcher: Dispatcher, state: FSMContext | None = None) -> None:
        state = require(dispatcher, state, message, _actor_id(message))
        data = await load(state, message, _actor_id(message))
        if data is None:
            return
        if data['submission_started']:
            await message.answer(frozen_text, parse_mode=None)
            return
        if message.message_id <= data['last_message_id']:
            return
        data['last_message_id'] = message.message_id
        await save(state, data)
        if data['index'] == len(steps):
            return  # Text cannot submit or rotate the review's receipt link.
        step = steps[data['index']]
        if data['prompt_message_id'] is None:
            await message.answer(stale_text, parse_mode=None)
            return
        if not isinstance(step, (ContactField, LocationField)):
            reply = message.reply_to_message
            if (
                reply is None
                or reply.message_id != data['prompt_message_id']
                or reply.chat.id != message.chat.id
                or reply.from_user is None
                or not reply.from_user.is_bot
                or reply.from_user.id != _bot_id(message)
            ):
                await message.answer('Ответьте на текущий вопрос бота.', parse_mode=None)
                return
        try:
            value = step.read(message.text or '') if isinstance(step, TextField) else step.read(message)
        except InvalidField as error:
            await message.answer(str(error), parse_mode=None)
            await show(message, state, data)
            return
        if isinstance(step, (ContactField, LocationField)):
            assert isinstance(value, Mapping)
            data['candidate'] = {'value': dict(value), 'nonce': secrets.token_hex(4), 'message_id': None}
            await save(state, data)  # Old candidate becomes unusable even after lost send.
            await remove(message, state, data)
            reply = await message.answer(
                f"{step.label}: {display(step, value)}\nПодтвердите значение для текущего вопроса.",
                parse_mode=None,
                reply_markup=keyboard(data, 'v:' + data['candidate']['nonce']),
            )
            data['candidate']['message_id'] = sent_id(reply, message)
            await save(state, data)
        else:
            data['values'][step.name] = value
            data['index'] += 1
            await show(message, state, data)

    @router.callback_query(F.data.startswith(prefix))
    async def confirm(query: CallbackQuery, dispatcher: Dispatcher, state: FSMContext | None = None) -> None:
        await query.answer()  # ACK foreign/stale/inaccessible actions before any work.
        message = query.message
        if (
            not isinstance(message, Message)
            or message.chat.type != 'private'
            or message.business_connection_id is not None
            or message.message_thread_id is not None
            or message.is_topic_message is True
            or query.from_user.is_bot
            or message.from_user is None
            or not message.from_user.is_bot
            or message.from_user.id != _bot_id(message)
        ):
            return
        state = require(dispatcher, state, message, query.from_user.id)
        data = await load(state, message, query.from_user.id)
        if data is None:
            return
        candidate = data['candidate']
        if (
            candidate is not None
            and not data['submission_started']
            and message.message_id == candidate['message_id']
            and query.data == f"{prefix}{data['operation_id']}:v:{candidate['nonce']}"
        ):
            step = steps[data['index']]
            data['values'][step.name] = candidate['value']
            data['index'] += 1
            await show(message, state, data)
            return
        if (
            data['index'] != len(steps)
            or message.message_id != data['review_message_id']
            or query.data != f"{prefix}{data['operation_id']}:submit"
        ):
            await message.answer(stale_text, parse_mode=None)
            return
        data['submission_started'] = True
        await save(state, data)
        submission = DialogSubmission(
            _bot_id(message), query.from_user.id, message.chat.id, data['operation_id'], data['values']
        )
        try:
            text = await on_submit(submission)
            if not _plain(text, 4096):
                raise InvalidCompletion('on_submit must return nonempty plain text up to 4096 UTF-16 units')
        except Exception:
            await message.answer(
                'Результат отправки пока не подтверждён. Нажмите «Отправить» ещё раз для проверки той же заявки.',
                parse_mode=None,
            )
            raise
        await clear(state, data)  # Completion is final even if the following feedback is lost.
        await message.answer(text, parse_mode=None, reply_markup=remove_keyboard())

    return router
