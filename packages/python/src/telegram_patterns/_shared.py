"""Internal helpers shared by several SDK-free modules; not part of the public API.

Modules import these names instead of each other's `_private` helpers. Error messages are the ones the
callers already raised, so moving a helper here changes no behaviour.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import InvalidType, UnsupportedCapability, ValidationFailure

# Canonical JSON and SQLite operations: sqlite_once, slots.

_MAX_PAYLOAD_DEPTH = 64


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _check_payload(value: Any, depth: int = 0) -> None:
    """Only JSON values hash unambiguously: {1: 'a'} vs {'1': 'a'} or tuple vs list would collide."""
    if depth > _MAX_PAYLOAD_DEPTH:
        raise ValidationFailure("Operation payload is nested too deeply")
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationFailure("Operation payload numbers must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _check_payload(item, depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValidationFailure("Operation payload keys must be strings")
            _check_payload(item, depth + 1)
        return
    raise ValidationFailure(
        "Operation payload must contain only dict with str keys, list, str, int, float, bool or None"
    )


def payload_digest(payload: Any) -> str:
    _check_payload(payload)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def owned_transaction(action: int, *_arguments: Any) -> int:
    """SQLite authorizer that keeps the transaction owned by the caller.

    Includes Python commit/rollback, SQL transaction commands and the implicit COMMIT performed by
    executescript. Savepoints remain local.
    """
    return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_TRANSACTION else sqlite3.SQLITE_OK


# Environment files: settings, diagnostics.

ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ENV_FILE_LIMIT = 65536


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines, optional `export`, quotes and # comments; no interpolation or code."""
    raw = path.read_bytes()
    if len(raw) > _ENV_FILE_LIMIT:
        raise ValidationFailure(f"{path.name} exceeds 64 KiB")
    values: dict[str, str] = {}
    for number, line in enumerate(raw.decode('utf-8-sig').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.removeprefix('export ').partition('=')
        key, value = key.strip(), value.strip()
        if not separator or not ENV_KEY.fullmatch(key):
            raise ValidationFailure(f"Invalid line {number} in {path.name}: expected KEY=VALUE")  # value never echoed
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '\'"':
            value = value[1:-1]
        else:
            value = value.split(' #', 1)[0].rstrip()
        values[key] = value
    return values


def env_flag(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("", "0", "false", "no", "off"):
        return False
    if normalized in ("1", "true", "yes", "on"):
        return True
    raise ValidationFailure(f"{name} must be 1/true/yes/on or 0/false/no/off")  # value never echoed


# Time: calendar_core, slots, the aiogram calendar keyboards.

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def resolve_zone(key: str) -> tzinfo:
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


def to_utc(value: datetime) -> datetime:
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


def micros(value: datetime) -> int:
    delta = to_utc(value) - _EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def instant(value: int) -> datetime:
    return _EPOCH + timedelta(microseconds=value)


# Selection callback prefix: selection, the aiogram selection router.

SELECTION_PREFIX = re.compile(r'[A-Za-z0-9_-]{1,8}:')
