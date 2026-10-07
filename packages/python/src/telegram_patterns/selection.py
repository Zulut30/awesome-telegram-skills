"""Server-owned selection drafts; synchronous atomic state, no SDK or effects."""

from __future__ import annotations

import math
import re
import secrets
import threading
import time
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Literal, Mapping, Sequence

from .errors import ConflictFailure, InvalidType, ValidationFailure

_KEY = re.compile(r'[A-Za-z0-9_-]{1,24}')
_PREFIX = re.compile(r'[A-Za-z0-9_-]{1,8}:')
_ACTION = re.compile(r'(?:[stf]:[A-Za-z0-9_-]{1,24}|q:(?:inc|dec)|y:[0-9a-f]{16}|ask|back|cancel|refresh)')
_MAX_REVISION = 9_999_999_999


def _key(value: str) -> None:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise ValidationFailure('Use 1..24 ASCII letters/digits/_/- for selection keys')


def _label(value: str, limit: int = 40) -> None:
    try:
        valid = (
            isinstance(value, str)
            and bool(value.strip())
            and not any(ord(c) < 32 or ord(c) == 127 for c in value)
            and len(value.encode('utf-16-le')) // 2 <= limit
        )
    except UnicodeError:
        valid = False
    if not valid:
        raise ValidationFailure(f'Use a single-line nonempty label up to {limit} UTF-16 units')


def _labels(value: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or len(value) > 8:
        raise InvalidType('Use a mapping with up to eight field/filter labels')
    result = dict(value)
    for key, label in result.items():
        _key(key)
        _label(label)
    return MappingProxyType(result)


@dataclass(frozen=True, slots=True)
class SelectionOption:
    key: str
    label: str
    filters: Sequence[str] = ()
    enabled: bool = True

    def __post_init__(self) -> None:
        _key(self.key)
        _label(self.label)
        if isinstance(self.filters, (str, bytes)) or not isinstance(self.filters, Sequence):
            raise InvalidType('Use a sequence of filter keys')
        filters = tuple(self.filters)
        for key in filters:
            _key(key)
        if len(filters) > 8 or len(set(filters)) != len(filters):
            raise ValidationFailure('Use up to eight distinct filter keys per option')
        if type(self.enabled) is not bool:
            raise InvalidType('Option enabled must be a bool')
        object.__setattr__(self, 'filters', filters)


@dataclass(frozen=True, slots=True)
class SelectionSpec:
    """Snapshot of the current server rules; replace it when resource_version changes."""

    options: Sequence[SelectionOption]
    toggles: Mapping[str, str] = field(default_factory=dict)
    filters: Mapping[str, str] = field(default_factory=lambda: {'all': 'Все'})
    quantity_min: int = 1
    quantity_max: int = 99
    min_selected: int = 0
    max_selected: int | None = None
    confirm_text: str = 'Подтвердить действие'
    resource_version: str = '1'

    def __post_init__(self) -> None:
        if isinstance(self.options, (str, bytes)) or not isinstance(self.options, Sequence):
            raise InvalidType('Use a sequence of SelectionOption')
        options = tuple(self.options)
        if not 1 <= len(options) <= 60 or any(not isinstance(o, SelectionOption) for o in options):
            raise ValidationFailure('Use 1..60 SelectionOption items')
        if len({o.key for o in options}) != len(options):
            raise ValidationFailure('Option keys must be unique')
        toggles, filters = _labels(self.toggles), _labels(self.filters)
        if 'all' not in filters or any(k not in filters for o in options for k in o.filters):
            raise ValidationFailure('Declare all option filters, including the all filter')
        if (
            type(self.quantity_min) is not int
            or type(self.quantity_max) is not int
            or not 0 <= self.quantity_min <= self.quantity_max <= 1_000_000
        ):
            raise ValidationFailure('Use integer quantity bounds in 0..1000000')
        maximum = len(options) if self.max_selected is None else self.max_selected
        if (
            type(maximum) is not int
            or type(self.min_selected) is not int
            or not 0 <= self.min_selected <= maximum <= len(options)
            or self.min_selected > sum(o.enabled for o in options)
        ):
            raise ValidationFailure('Selection bounds must fit the available server options')
        _label(self.confirm_text, 48)
        _label(self.resource_version, 64)
        object.__setattr__(self, 'options', options)
        object.__setattr__(self, 'toggles', toggles)
        object.__setattr__(self, 'filters', filters)
        object.__setattr__(self, 'max_selected', maximum)

    @property
    def selection_limit(self) -> int:
        return len(self.options) if self.max_selected is None else self.max_selected


@dataclass(frozen=True, slots=True)
class SelectionContext:
    """Host-derived Bot API identity; callback strings are never an identity source."""

    bot_id: int
    owner_id: int
    chat_id: int
    message_id: int
    message_thread_id: int | None = None

    def __post_init__(self) -> None:
        if any(type(v) is not int or v <= 0 for v in (self.bot_id, self.owner_id, self.message_id)):
            raise ValidationFailure('Bot, owner and message IDs must be positive integers')
        if type(self.chat_id) is not int or self.chat_id == 0:
            raise ValidationFailure('Chat ID must be a nonzero integer')
        if self.message_thread_id is not None and (
            type(self.message_thread_id) is not int or self.message_thread_id <= 0
        ):
            raise ValidationFailure('Thread ID must be a positive integer or None')


@dataclass(frozen=True, slots=True)
class SelectionState:
    """Immutable view, not an externally supplied authoritative draft or grant."""

    session_id: str
    prefix: str
    context: SelectionContext
    spec: SelectionSpec
    revision: int
    selected: tuple[str, ...]
    toggles: tuple[tuple[str, bool], ...]
    quantity: int
    filter_key: str
    expires_at: float
    phase: Literal['editing', 'confirming', 'confirmed', 'cancelled'] = 'editing'
    confirmation_id: str | None = None
    confirmation_expires_at: float | None = None
    operation_id: str | None = None

    def callback(self, action: str) -> str:
        """Bounded wire code; constructing it does not authorize an action."""
        if (
            not isinstance(action, str)
            or not _ACTION.fullmatch(action)
            or not _PREFIX.fullmatch(self.prefix)
            or not re.fullmatch(r'[0-9a-f]{16}', self.session_id)
            or type(self.revision) is not int
            or not 0 <= self.revision <= _MAX_REVISION
        ):
            raise ValidationFailure('Invalid selection callback fields')
        data = f'{self.prefix}{self.session_id}:{self.revision}:{action}'
        if len(data.encode('utf-8')) > 64:
            raise ValidationFailure('Selection callback exceeds 64 bytes')
        return data

    def text(self) -> str:
        labels = {o.key: o.label for o in self.spec.options}
        selected = ', '.join(labels[k] for k in self.selected) or 'ничего'
        flags = '\n'.join(f'{self.spec.toggles[k]}: {"да" if v else "нет"}' for k, v in self.toggles)
        phase = {
            'editing': 'Выберите варианты.',
            'confirming': f'Проверьте выбор: {self.spec.confirm_text}.',
            'confirmed': 'Выбор подтвержден.',
            'cancelled': 'Выбор отменен.',
        }[self.phase]
        return '\n'.join(
            part
            for part in (
                phase,
                f'Выбрано: {selected}',
                f'Количество: {self.quantity}',
                f'Фильтр: {self.spec.filters[self.filter_key]}',
                flags,
            )
            if part
        )


@dataclass(frozen=True, slots=True)
class SelectionResult:
    status: Literal['accepted', 'confirming', 'confirmed', 'cancelled', 'invalid', 'denied', 'stale']
    text: str
    state: SelectionState | None = None


class SelectionMenu:
    """One message's server-owned draft. All mutations are atomic in this process.

    No I/O, persistence, business effect or cross-worker guarantee. Confirming
    consumes a local intent once and returns operation_id/resource_version for
    the host's own current-ACL, idempotent transaction. It does not execute it.
    """

    def __init__(
        self,
        spec: SelectionSpec,
        context: SelectionContext,
        *,
        prefix: str = 'sel:',
        selected: Sequence[str] = (),
        toggles: Mapping[str, bool] | None = None,
        quantity: int | None = None,
        ttl_seconds: float = 1800,
        confirmation_ttl_seconds: float = 60,
    ) -> None:
        if not isinstance(spec, SelectionSpec) or not isinstance(context, SelectionContext):
            raise InvalidType('Use SelectionSpec and SelectionContext')
        if not isinstance(prefix, str) or not _PREFIX.fullmatch(prefix):
            raise ValidationFailure('Use 1..8 ASCII prefix characters followed by colon')
        for value in (ttl_seconds, confirmation_ttl_seconds):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValidationFailure('Selection TTLs must be finite and positive')
        if isinstance(selected, (str, bytes)) or not isinstance(selected, Sequence):
            raise InvalidType('Use a sequence of selected option keys')
        keys = tuple(selected)
        allowed = {o.key for o in spec.options if o.enabled}
        if (
            any(not isinstance(k, str) or k not in allowed for k in keys)
            or len(set(keys)) != len(keys)
            or len(keys) > spec.selection_limit
        ):
            raise ValidationFailure('Initial selected keys must be distinct available options within the limit')
        values = {} if toggles is None else toggles
        if not isinstance(values, Mapping) or any(
            k not in spec.toggles or type(v) is not bool for k, v in values.items()
        ):
            raise ValidationFailure('Use declared toggle keys and bool values')
        amount = spec.quantity_min if quantity is None else quantity
        if type(amount) is not int or not spec.quantity_min <= amount <= spec.quantity_max:
            raise ValidationFailure('Initial quantity is outside server bounds')
        self._lock = threading.RLock()
        self._ttl, self._confirm_ttl = float(ttl_seconds), float(confirmation_ttl_seconds)
        self._state = SelectionState(
            secrets.token_hex(8),
            prefix,
            context,
            spec,
            0,
            tuple(o.key for o in spec.options if o.key in keys),
            tuple((k, values.get(k, False)) for k in spec.toggles),
            amount,
            'all',
            time.monotonic() + self._ttl,
        )
        self._pattern = re.compile(re.escape(prefix) + r'([0-9a-f]{16}):(0|[1-9][0-9]{0,9}):(.+)')

    @property
    def state(self) -> SelectionState:
        with self._lock:
            return self._state

    def _guard(self, data: str, context: SelectionContext) -> SelectionResult | None:
        state = self._state
        if not isinstance(context, SelectionContext):
            raise InvalidType('Derive a SelectionContext from the authenticated host event')
        if context.owner_id != state.context.owner_id:
            return SelectionResult('denied', 'Это выбор другого пользователя.')
        if context != state.context:
            return SelectionResult('stale', 'Кнопка относится к другому сообщению или контексту.')
        match = self._pattern.fullmatch(data) if isinstance(data, str) and len(data) <= 64 else None
        if (
            match is None
            or not _ACTION.fullmatch(match[3])
            or match[1] != state.session_id
            or int(match[2]) != state.revision
            or time.monotonic() >= state.expires_at
            or state.phase in {'confirmed', 'cancelled'}
        ):
            return SelectionResult('stale', 'Кнопка устарела. Откройте актуальный выбор.', state)
        return None

    def check(self, data: str, context: SelectionContext) -> SelectionResult | None:
        """Cheap preflight; apply repeats it atomically after any awaited host work."""
        with self._lock:
            return self._guard(data, context)

    def _commit(self, **changes) -> SelectionState:
        if self._state.revision >= _MAX_REVISION:
            raise ConflictFailure('Selection revision limit reached; create a new authenticated menu')
        self._state = replace(
            self._state, revision=self._state.revision + 1, expires_at=time.monotonic() + self._ttl, **changes
        )
        return self._state

    def replace_spec(self, spec: SelectionSpec) -> SelectionState:
        """Trusted host refresh; changed rules revoke every button/confirmation.

        Retain only available selections, clamp quantity and remove obsolete
        fields. A refresh is explicit to the user; it never confirms a new draft.
        Same rules preserve revisions. Closed menus retain their original intent.
        """
        if not isinstance(spec, SelectionSpec):
            raise InvalidType('Use the current server SelectionSpec')
        with self._lock:
            state = self._state
            if spec == state.spec:
                return state
            if state.phase in {'confirmed', 'cancelled'}:
                raise ConflictFailure('Closed selection retains its original intent; create a new menu')
            values = dict(state.toggles)
            chosen = tuple(o.key for o in spec.options if o.enabled and o.key in state.selected)[: spec.selection_limit]
            # Host configuration refresh invalidates wire revisions without renewing an expired draft.
            expires_at = state.expires_at
            self._commit(
                spec=spec,
                selected=chosen,
                toggles=tuple((k, values.get(k, False)) for k in spec.toggles),
                quantity=min(max(state.quantity, spec.quantity_min), spec.quantity_max),
                filter_key=state.filter_key if state.filter_key in spec.filters else 'all',
                phase='editing',
                confirmation_id=None,
                confirmation_expires_at=None,
                operation_id=None,
            )
            self._state = replace(self._state, expires_at=expires_at)
            return self._state

    def apply(self, data: str, context: SelectionContext) -> SelectionResult:
        with self._lock:
            refused = self._guard(data, context)
            if refused is not None:
                return refused
            state, spec = self._state, self._state.spec
            action = data.split(':', 3)[3]
            if (
                state.phase == 'confirming'
                and action not in {'back', 'cancel', 'refresh'}
                and not action.startswith('y:')
            ):
                return SelectionResult('stale', 'Сначала вернитесь к редактированию выбора.', state)
            changes: dict = {'confirmation_id': None, 'confirmation_expires_at': None, 'phase': 'editing'}
            status: Literal['accepted', 'confirming', 'confirmed', 'cancelled'] = 'accepted'
            if action.startswith('s:'):
                key = action[2:]
                option = next((o for o in spec.options if o.key == key), None)
                if (
                    option is None
                    or not option.enabled
                    or (state.filter_key != 'all' and state.filter_key not in option.filters)
                ):
                    return SelectionResult('invalid', 'Этот вариант сейчас недоступен.', state)
                chosen = set(state.selected)
                if key in chosen:
                    chosen.remove(key)
                elif len(chosen) >= spec.selection_limit:
                    return SelectionResult('invalid', 'Достигнуто допустимое число вариантов.', state)
                else:
                    chosen.add(key)
                changes['selected'] = tuple(o.key for o in spec.options if o.key in chosen)
            elif action.startswith('t:'):
                key = action[2:]
                values = dict(state.toggles)
                if key not in values:
                    return SelectionResult('invalid', 'Такого переключателя нет.', state)
                values[key] = not values[key]
                changes['toggles'] = tuple(values.items())
            elif action.startswith('f:'):
                key = action[2:]
                if key not in spec.filters:
                    return SelectionResult('invalid', 'Такого фильтра нет.', state)
                changes['filter_key'] = key
            elif action.startswith('q:'):
                amount = state.quantity + (1 if action == 'q:inc' else -1)
                if not spec.quantity_min <= amount <= spec.quantity_max:
                    return SelectionResult('invalid', 'Количество вне допустимого диапазона.', state)
                changes['quantity'] = amount
            elif action == 'ask':
                if len(state.selected) < spec.min_selected:
                    return SelectionResult('invalid', 'Выберите необходимое число вариантов.', state)
                status = 'confirming'
                changes.update(
                    phase='confirming',
                    confirmation_id=secrets.token_hex(8),
                    confirmation_expires_at=min(state.expires_at, time.monotonic() + self._confirm_ttl),
                )
            elif action.startswith('y:'):
                if (
                    state.phase != 'confirming'
                    or action[2:] != state.confirmation_id
                    or state.confirmation_expires_at is None
                    or time.monotonic() >= state.confirmation_expires_at
                ):
                    return SelectionResult('stale', 'Подтверждение истекло или относится к другому выбору.', state)
                status = 'confirmed'
                changes.update(phase='confirmed', operation_id=f'selection-{state.session_id}-{state.confirmation_id}')
            elif action == 'cancel':
                status = 'cancelled'
                changes['phase'] = 'cancelled'
            elif action == 'back' and state.phase != 'confirming':
                return SelectionResult('stale', 'Подтверждение еще не открыто.', state)
            current = self._commit(**changes)
            text = {
                'accepted': 'Выбор обновлен.',
                'confirming': 'Проверьте выбор перед подтверждением.',
                'confirmed': 'Выбор подтвержден.',
                'cancelled': 'Выбор отменен.',
            }[status]
            return SelectionResult(status, text, current)


def selection_markup(state: SelectionState, *, columns: int = 2, styles: bool = False) -> dict[str, Any]:
    """InlineKeyboardMarkup JSON for a selection snapshot, for any SDK; every press still goes through menu.apply.

    Without styles it matches telegram_patterns.aiogram.selection_keyboard with default capabilities.
    """
    from .markup import inline_button, inline_markup, layout_rows

    if not isinstance(state, SelectionState):
        raise InvalidType('Use the server SelectionState')
    if type(styles) is not bool:
        raise InvalidType('styles must be bool')
    if state.phase in {'confirmed', 'cancelled'}:
        return {'inline_keyboard': []}

    def button(text: str, action: str, style: Literal['primary', 'success', 'danger'] | None = None) -> dict[str, Any]:
        return inline_button(text, callback_data=state.callback(action), style=style if styles else None)

    rows: list[list[dict[str, Any]]] = []
    if state.phase == 'confirming':
        if state.confirmation_id is None:
            raise ValidationFailure('Confirming view needs its server confirmation ID')
        rows = [
            [button('Да: ' + state.spec.confirm_text, 'y:' + state.confirmation_id, 'danger')],
            [button('Изменить выбор', 'back'), button('Отмена', 'cancel')],
        ]
    else:
        choices = [
            button(
                ('✓ ' if o.key in state.selected else '□ ') + o.label,
                's:' + o.key,
                'success' if o.key in state.selected else None,
            )
            for o in state.spec.options
            if o.enabled and (state.filter_key == 'all' or state.filter_key in o.filters)
        ]
        if choices:
            rows.extend(layout_rows(choices, (columns,)))
        rows.extend(
            [[button(('✓ ' if value else '□ ') + state.spec.toggles[key], 't:' + key)] for key, value in state.toggles]
        )
        rows.append([button('−1', 'q:dec'), button(str(state.quantity) + ' ↻', 'refresh'), button('+1', 'q:inc')])
        filters = [
            button(('✓ ' if key == state.filter_key else '') + label, 'f:' + key)
            for key, label in state.spec.filters.items()
        ]
        rows.extend(layout_rows(filters, (2,)))
        rows.append([button(state.spec.confirm_text, 'ask', 'danger'), button('Отмена', 'cancel')])
    return inline_markup(rows)
