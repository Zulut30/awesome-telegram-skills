"""Bounded message fields for the optional aiogram dialog adapter; no HTTP."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar, Mapping, TypeAlias

from aiogram.types import Message

from ..errors import InvalidType, ValidationFailure
from .forms import InvalidField, _plain

FieldValue: TypeAlias = str | Mapping[str, str | int | float | None]


def _text(value: object, maximum: int = 256) -> str:
    if not isinstance(value, str) or not _plain(value, maximum) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise InvalidField('Введите значение без управляющих символов в указанном формате.')
    return value.strip()


def _record(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise InvalidField('Данные поля повреждены. Повторите ввод.')
    return dict(value)


@dataclass(frozen=True, slots=True)
class _Field:
    name: str
    label: str
    prompt: str
    kind: ClassVar[str]
    native: ClassVar[bool] = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', self.name):
            raise ValidationFailure('Use a unique 1..32 lowercase ASCII field name')
        if not _plain(self.label, 64) or not _plain(self.prompt, 512):
            raise ValidationFailure('Use a bounded label and prompt')

    def signature(self) -> str:
        # Exact field kind/config prevents silently reusing another step schema.
        return json.dumps({'kind': self.kind, **asdict(self)}, sort_keys=True, ensure_ascii=False)

    def restore(self, value: object) -> FieldValue:
        raise NotImplementedError

    def read(self, message: Message) -> FieldValue:
        return self.restore(message.text)

    def display(self, value: FieldValue) -> str:
        return str(value)


def _decimal(value: object) -> Decimal:
    if type(value) not in (str, int, Decimal):
        raise InvalidType('Use a decimal string, int or Decimal, never float/bool')
    text = str(value)
    if len(text) > 64:
        raise ValidationFailure('Decimal bound is too long')
    try:
        result = Decimal(text)
    except InvalidOperation:
        raise ValidationFailure('Use a finite decimal bound') from None
    if not result.is_finite() or result.adjusted() > 64 or result.adjusted() < -64:
        raise ValidationFailure('Use a bounded finite decimal')
    return result


@dataclass(frozen=True, slots=True)
class NumberField(_Field):
    """Exact decimal string (comma/dot); no float, exponent or silent rounding."""

    minimum: str | int | Decimal | None = None
    maximum: str | int | Decimal | None = None
    decimal_places: int = 2
    kind: ClassVar[str] = 'number'

    def __post_init__(self) -> None:
        _Field.__post_init__(self)
        if type(self.decimal_places) is not int or not 0 <= self.decimal_places <= 18:
            raise ValidationFailure('Use decimal_places 0..18')
        for name in ('minimum', 'maximum'):
            value = getattr(self, name)
            if value is not None:
                canonical = format(_decimal(value), 'f')
                _decimal(canonical)  # Reject normalized overflow at configuration time.
                object.__setattr__(self, name, canonical)
        if self.minimum is not None and self.maximum is not None and _decimal(self.minimum) > _decimal(self.maximum):
            raise ValidationFailure('Minimum exceeds maximum')

    def restore(self, value: object) -> str:
        text = _text(value, 64)
        if not re.fullmatch(r'[+-]?[0-9]+(?:[.,][0-9]+)?', text):
            raise InvalidField('Введите число без экспоненты; разделитель — точка или запятая.')
        text = text.replace(',', '.')
        if '.' in text and len(text.split('.')[1]) > self.decimal_places:
            raise InvalidField(f'Допустимо до {self.decimal_places} знаков после разделителя.')
        number = Decimal(text)
        if (self.minimum is not None and number < _decimal(self.minimum)) or (
            self.maximum is not None and number > _decimal(self.maximum)
        ):
            raise InvalidField('Число вне разрешенного диапазона.')
        canonical = format(number, 'f')
        if '.' in canonical:
            canonical = canonical.rstrip('0').rstrip('.')
        return '0' if number == 0 else canonical


@dataclass(frozen=True, slots=True)
class EmailField(_Field):
    """ASCII dot-atom mailbox; lowercase domain, preserved local case; no DNS."""

    kind: ClassVar[str] = 'email'

    def restore(self, value: object) -> str:
        text = _text(value, 254)
        if text.count('@') != 1:
            raise InvalidField('Введите email в формате name@example.com.')
        local, domain = text.split('@')
        labels = domain.split('.')
        if (
            not 1 <= len(local) <= 64
            or local.startswith('.')
            or local.endswith('.')
            or '..' in local
            or not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+", local)
            or len(labels) < 2
            or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', part) for part in labels)
        ):
            raise InvalidField('Введите email без пробелов, с корректным именем и доменом.')
        return local + '@' + domain.lower()


@dataclass(frozen=True, slots=True)
class PhoneField(_Field):
    """Explicit international number, 7..15 digits (component policy), not identity."""

    kind: ClassVar[str] = 'phone'

    def restore(self, value: object) -> str:
        text = _text(value, 64)
        if not re.fullmatch(r'\+[0-9 ()-]+', text):
            raise InvalidField('Укажите международный номер с + и кодом страны.')
        canonical = re.sub(r'[ ()-]', '', text)
        if not re.fullmatch(r'\+[1-9][0-9]{6,14}', canonical):
            raise InvalidField('Укажите от 7 до 15 цифр, начиная с кода страны.')
        return canonical


@dataclass(frozen=True, slots=True)
class DateField(_Field):
    """Calendar date YYYY-MM-DD; no implicit locale, time or timezone."""

    minimum: str | None = None
    maximum: str | None = None
    kind: ClassVar[str] = 'date'

    def __post_init__(self) -> None:
        _Field.__post_init__(self)
        for value in (self.minimum, self.maximum):
            if value is not None:
                try:
                    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                        raise ValueError
                except ValueError:
                    raise ValidationFailure('Date bounds must be canonical YYYY-MM-DD') from None
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValidationFailure('Minimum date exceeds maximum')

    def restore(self, value: object) -> str:
        text = _text(value, 10)
        try:
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', text):
                raise ValueError
            result = date.fromisoformat(text).isoformat()
        except ValueError:
            raise InvalidField('Введите существующую дату в формате ГГГГ-ММ-ДД.') from None
        if (self.minimum is not None and result < self.minimum) or (self.maximum is not None and result > self.maximum):
            raise InvalidField('Дата вне разрешенного диапазона.')
        return result


@dataclass(frozen=True, slots=True)
class FileField(_Field):
    """Opaque document reference and metadata, never downloaded or used as path."""

    max_bytes: int = 10 * 1024 * 1024
    mime_types: tuple[str, ...] = ()
    kind: ClassVar[str] = 'file'

    def __post_init__(self) -> None:
        _Field.__post_init__(self)
        if type(self.max_bytes) is not int or not 1 <= self.max_bytes <= 2**53 - 1:
            raise ValidationFailure('Use a positive bounded metadata byte limit')
        if not isinstance(self.mime_types, (tuple, list)) or len(self.mime_types) > 32:
            raise ValidationFailure('Use at most 32 MIME strings')
        if any(
            not isinstance(m, str) or len(m) > 127 or not re.fullmatch(r'[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+', m)
            for m in self.mime_types
        ):
            raise ValidationFailure('Use bounded explicit MIME strings')
        object.__setattr__(self, 'mime_types', tuple(self.mime_types))

    def restore(self, value: object) -> dict[str, Any]:
        result = _record(value, {'file_id', 'file_unique_id', 'file_name', 'mime_type', 'file_size'})
        for key in ('file_id', 'file_unique_id'):
            result[key] = _text(result[key], 1024)
        for key in ('file_name', 'mime_type'):
            if result[key] is not None:
                result[key] = _text(result[key], 255)
        if type(result['file_size']) is not int or not 0 <= result['file_size'] <= self.max_bytes:
            raise InvalidField('Размер файла неизвестен или превышает разрешенный лимит.')
        if self.mime_types and result['mime_type'] not in self.mime_types:
            raise InvalidField('Этот тип файла не разрешен.')
        return result

    def read(self, message: Message) -> dict[str, Any]:
        document = message.document
        if document is None or message.media_group_id is not None:
            raise InvalidField('Отправьте один документ ответом на текущий вопрос.')
        return self.restore(
            {
                name: getattr(document, name)
                for name in ('file_id', 'file_unique_id', 'file_name', 'mime_type', 'file_size')
            }
        )

    def display(self, value: FieldValue) -> str:
        assert isinstance(value, Mapping)
        return f"{value['file_name'] or 'Документ'} ({value['file_size']} байт)"


@dataclass(frozen=True, slots=True)
class ContactField(_Field):
    """Native contact candidate; default requires contact.user_id == current author."""

    own: bool = True
    kind: ClassVar[str] = 'contact'
    native: ClassVar[bool] = True

    def __post_init__(self) -> None:
        _Field.__post_init__(self)
        if type(self.own) is not bool:
            raise InvalidType('Own must be bool')

    def restore(self, value: object) -> dict[str, Any]:
        result = _record(value, {'phone_number', 'first_name', 'last_name', 'user_id'})
        for key, maximum in (('phone_number', 64), ('first_name', 64)):
            result[key] = _text(result[key], maximum)
        if result['last_name'] is not None:
            result['last_name'] = _text(result['last_name'], 64)
        if result['user_id'] is not None and (
            type(result['user_id']) is not int or not 0 < result['user_id'] <= 2**63 - 1
        ):
            raise InvalidField('Контакт имеет некорректный user_id.')
        if self.own and result['user_id'] is None:
            raise InvalidField('Поделитесь своим контактом через кнопку.')
        return result

    def read(self, message: Message) -> dict[str, Any]:
        contact, author = message.contact, message.from_user
        if (
            contact is None
            or message.forward_origin is not None
            or (self.own and (author is None or contact.user_id != author.id))
        ):
            raise InvalidField(
                'Поделитесь своим контактом через кнопку.' if self.own else 'Отправьте контакт без пересылки.'
            )
        return self.restore(
            {name: getattr(contact, name) for name in ('phone_number', 'first_name', 'last_name', 'user_id')}
        )

    def display(self, value: FieldValue) -> str:
        assert isinstance(value, Mapping)
        return f"{value['first_name']} {value['last_name'] or ''} · {value['phone_number']}"


@dataclass(frozen=True, slots=True)
class LocationField(_Field):
    """Static coordinate candidate; does not prove physical presence/permission."""

    kind: ClassVar[str] = 'location'
    native: ClassVar[bool] = True

    def restore(self, value: object) -> dict[str, Any]:
        result = _record(value, {'latitude', 'longitude', 'horizontal_accuracy'})
        for key, maximum in (('latitude', 90), ('longitude', 180)):
            number = result[key]
            if type(number) not in (int, float) or not -maximum <= number <= maximum or not math.isfinite(number):
                raise InvalidField('Координаты вне разрешенного диапазона.')
            result[key] = float(number)
        accuracy = result['horizontal_accuracy']
        if accuracy is not None and (
            type(accuracy) not in (int, float) or not 0 <= accuracy <= 1500 or not math.isfinite(accuracy)
        ):
            raise InvalidField('Некорректная точность геопозиции.')
        result['horizontal_accuracy'] = float(accuracy) if accuracy is not None else None
        return result

    def read(self, message: Message) -> dict[str, Any]:
        location = message.location
        if location is None or location.live_period is not None or message.forward_origin is not None:
            raise InvalidField('Отправьте обычную статичную геопозицию без пересылки.')
        return self.restore(
            {name: getattr(location, name) for name in ('latitude', 'longitude', 'horizontal_accuracy')}
        )

    def display(self, value: FieldValue) -> str:
        assert isinstance(value, Mapping)
        return f"{value['latitude']}, {value['longitude']}"
