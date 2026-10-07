"""SDK-free calendar snapshots and explicit local-time resolution."""

from __future__ import annotations

import calendar as _calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from itertools import islice
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import InvalidType, UnsupportedCapability, ValidationFailure

_KEY = re.compile(r'[A-Za-z0-9_-]{1,24}\Z', re.ASCII)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MONTHS = (
    'Январь',
    'Февраль',
    'Март',
    'Апрель',
    'Май',
    'Июнь',
    'Июль',
    'Август',
    'Сентябрь',
    'Октябрь',
    'Ноябрь',
    'Декабрь',
)
_WEEKDAYS = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс')


def _zone(key: str) -> tzinfo:
    if not isinstance(key, str) or not key or len(key) > 128:
        raise ValidationFailure('Use a bounded IANA time-zone key')
    if key == 'UTC':
        return timezone.utc
    try:
        return ZoneInfo(key)
    except ValueError:
        raise ValidationFailure('Use a normalized IANA time-zone key') from None
    except ZoneInfoNotFoundError:
        raise UnsupportedCapability(
            'Unknown time zone or missing IANA database; install the calendar extra when needed'
        ) from None


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidType('Use an aware datetime')
    try:
        result = value.astimezone(timezone.utc)
        if result.astimezone(value.tzinfo).replace(tzinfo=None) != value.replace(tzinfo=None):
            raise ValidationFailure('The local time does not exist')
        return result
    except (OverflowError, ValueError) as error:
        if isinstance(error, ValidationFailure):
            raise
        raise ValidationFailure('Datetime conversion is outside the supported range') from None


def _micros(value: datetime) -> int:
    delta = _utc(value) - _EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def _instant(value: int) -> datetime:
    return _EPOCH + timedelta(microseconds=value)


def resolve_local_time(local: datetime, time_zone: str, *, fold: int | None = None) -> datetime:
    """Resolve a naive wall time to UTC; reject gaps and require ambiguous fold.

    No network or process-wide TZ changes. IANA data comes from the host or the
    optional calendar extra; UTC works without it. The supplied fold, not an
    implicit datetime.fold, chooses the earlier (0) or later (1) occurrence.
    """
    if not isinstance(local, datetime) or local.tzinfo is not None:
        raise InvalidType('Use a naive local datetime and explicit time zone')
    if fold is not None and (type(fold) is not int or fold not in (0, 1)):
        raise ValidationFailure('Fold must be None, 0 or 1')
    zone = _zone(time_zone)
    candidates: dict[int, datetime] = {}
    try:
        for choice in (0, 1):
            instant = local.replace(tzinfo=zone, fold=choice).astimezone(timezone.utc)
            returned = instant.astimezone(zone)
            if returned.replace(tzinfo=None) == local.replace(fold=0):
                candidates[choice] = instant
    except (OverflowError, ValueError):
        raise ValidationFailure('Local time is outside the supported range') from None
    if not candidates:
        raise ValidationFailure('The local time is skipped by a time-zone transition')
    if len(set(candidates.values())) > 1 and fold is None:
        raise ValidationFailure('Ambiguous local time: explicitly choose fold=0 or fold=1')
    if fold is not None:
        if fold not in candidates:
            raise ValidationFailure('The selected occurrence does not exist')
        return candidates[fold]
    return next(iter(candidates.values()))


@dataclass(frozen=True, slots=True)
class TimeSlot:
    """Half-open [start, end) UTC interval; one resource is supplied by the host."""

    key: str
    start: datetime
    end: datetime
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not _KEY.fullmatch(self.key):
            raise ValidationFailure('Use a unique 1..24 ASCII slot key')
        if type(self.enabled) is not bool:
            raise InvalidType('Enabled must be bool')
        start, end = _utc(self.start), _utc(self.end)
        if start >= end:
            raise ValidationFailure('Slot end must be after start in UTC')
        object.__setattr__(self, 'start', start)
        object.__setattr__(self, 'end', end)

    def label(self, time_zone: str) -> str:
        """Include UTC offset so repeated DST wall times stay distinguishable."""
        zone = _zone(time_zone)
        try:
            start, end = self.start.astimezone(zone), self.end.astimezone(zone)
        except (OverflowError, ValueError):
            raise ValidationFailure('Display time is outside the supported range') from None

        def offset_label(value: datetime) -> str:
            raw = value.strftime('%z')
            return raw[:3] + ':' + raw[3:5] + (':' + raw[5:] if len(raw) > 5 else '')

        offset = offset_label(start)
        end_label = end.strftime('%H:%M') if start.date() == end.date() else end.strftime('%d.%m %H:%M')
        if start.utcoffset() != end.utcoffset():
            return f'{start:%H:%M} UTC{offset}–{end_label} UTC{offset_label(end)}'
        return f'{start:%H:%M}–{end_label} UTC{offset}'


@dataclass(frozen=True, slots=True)
class CalendarMonth:
    """Immutable Monday-first month; unavailable days have no selection action.

    Host derives available dates from current server slots in the display zone.
    This snapshot does not grant permission or reserve a slot.
    """

    year: int
    month: int
    time_zone: str = 'UTC'
    available_dates: Iterable[date] = ()
    blocked_dates: Iterable[date] = ()
    allowed_dates: frozenset[date] = field(init=False)
    weeks: tuple[tuple[date | None, ...], ...] = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.year) is not int
            or not 1 <= self.year <= 9999
            or type(self.month) is not int
            or not 1 <= self.month <= 12
        ):
            raise ValidationFailure('Use year 1..9999 and month 1..12')
        _zone(self.time_zone)
        values = []
        for dates in (self.available_dates, self.blocked_dates):
            if isinstance(dates, (str, bytes)):
                raise InvalidType('Use dates, not strings')
            try:
                snapshot = tuple(islice(iter(dates), 367))
            except TypeError:
                raise InvalidType('Use an iterable of dates') from None
            if len(snapshot) > 366 or any(
                type(d) is not date or d.year != self.year or d.month != self.month for d in snapshot
            ):
                raise ValidationFailure('Use at most 366 dates belonging to this month')
            values.append(frozenset(snapshot))
        available, blocked = values
        object.__setattr__(self, 'available_dates', available)
        object.__setattr__(self, 'blocked_dates', blocked)
        object.__setattr__(self, 'allowed_dates', available - blocked)
        numbers = _calendar.Calendar(firstweekday=0).monthdayscalendar(self.year, self.month)
        object.__setattr__(
            self, 'weeks', tuple(tuple(date(self.year, self.month, n) if n else None for n in row) for row in numbers)
        )

    def allows(self, day: date) -> bool:
        return type(day) is date and day in self.allowed_dates

    def text(self) -> str:
        rows = [f'{_MONTHS[self.month - 1]} {self.year} · {self.time_zone}', ' '.join(_WEEKDAYS)]
        rows.extend(
            ' '.join('  ' if day is None else f'{day.day:2}' if self.allows(day) else ' ·' for day in week)
            for week in self.weeks
        )
        rows.append('· — недоступно. Дату выбирайте кнопкой ниже.' if self.allowed_dates else 'Нет доступных дат.')
        return '\n'.join(rows)
