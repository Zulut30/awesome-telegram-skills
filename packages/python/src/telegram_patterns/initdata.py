"""Mini App initData validation: bot-owner HMAC (`hash`) and third-party Ed25519 (`signature`). Not OIDC."""

from __future__ import annotations

import base64
import hmac
import json
import re
import time
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Mapping
from urllib.parse import parse_qsl

from .errors import ErrorCode, UnsupportedCapability, ValidationFailure


class InvalidInitData(ValidationFailure):
    """Untrusted launch data; messages do not include raw input or secrets."""

    code: ErrorCode = 'invalid-init-data'


def _frozen(value: Any) -> Any:
    """Read-only view of parsed JSON: objects become mappings, arrays become tuples."""
    if isinstance(value, dict):
        return MappingProxyType({key: _frozen(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_frozen(item) for item in value)
    return value


def _thawed(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thawed(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thawed(item) for item in value]
    return value


def _reject_constant(name: str) -> Any:
    raise ValueError(f"Non-standard JSON constant {name}")


@dataclass(frozen=True)
class VerifiedLaunch:
    """Signed launch fields; nested JSON values are read-only (mappings and tuples)."""

    user_id: int
    auth_date: int
    user: Mapping[str, object]
    query_id: str | None = None
    chat_type: str | None = None
    chat_instance: str | None = None
    start_param: str | None = None
    can_send_after: int | None = None
    chat: Mapping[str, object] | None = None
    receiver: Mapping[str, object] | None = None

    def as_dict(self) -> dict[str, Any]:
        """Fresh JSON-compatible copy; absent optional fields are omitted."""
        result: dict[str, Any] = {'user_id': self.user_id, 'auth_date': self.auth_date, 'user': _thawed(self.user)}
        for name in ('query_id', 'chat_type', 'chat_instance', 'start_param', 'can_send_after', 'chat', 'receiver'):
            value = getattr(self, name)
            if value is not None:
                result[name] = _thawed(value)
        return result


# Telegram's Ed25519 keys for third-party validation:
# core.telegram.org/bots/webapps#validating-data-for-third-party-use
TELEGRAM_PUBLIC_KEYS: Mapping[str, bytes] = MappingProxyType(
    {
        'production': bytes.fromhex('e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d'),
        'test': bytes.fromhex('40055058a4ee38156a06562e52eece92a771bcd8346a8c4615cb7376eddf72ec'),
    }
)


def _check_policy(max_age_seconds: int, future_tolerance_seconds: int, max_length: int, now: int | None) -> None:
    for name, value, minimum in [
        ("max_age_seconds", max_age_seconds, 1),
        ("future_tolerance_seconds", future_tolerance_seconds, 0),
        ("max_length", max_length, 1),
    ]:
        if type(value) is not int or value < minimum:
            raise ValidationFailure(f"Invalid {name}")
    if now is not None and (type(now) is not int or now < 0):
        raise ValidationFailure("now must be a nonnegative Unix timestamp")


def _fields(raw: str, max_length: int) -> dict[str, str]:
    """Unambiguous decoded fields of raw initData."""
    if not isinstance(raw, str) or not raw or len(raw) > max_length:
        raise InvalidInitData("Invalid launch data size")
    if re.search(r"%(?![0-9a-fA-F]{2})", raw):
        raise InvalidInitData("Invalid URL encoding")
    try:
        pairs = parse_qsl(
            raw, keep_blank_values=True, strict_parsing=True, encoding="utf-8", errors="strict", max_num_fields=64
        )
    except (ValueError, UnicodeError):
        raise InvalidInitData("Invalid launch encoding") from None
    if not pairs or any(not k for k, _ in pairs) or len({k for k, _ in pairs}) != len(pairs):
        raise InvalidInitData("Ambiguous launch fields")
    return dict(pairs)


def _check_string(data: Mapping[str, str], prefix: str = "") -> bytes:
    try:
        return (prefix + "\n".join(f"{key}={value}" for key, value in sorted(data.items()))).encode("utf-8")
    except UnicodeError:
        raise InvalidInitData("Invalid launch encoding") from None


def _launch(
    data: Mapping[str, str], now: int | None, max_age_seconds: int, future_tolerance_seconds: int
) -> VerifiedLaunch:
    """Freshness and signed identity of fields whose signature is already verified."""
    if not re.fullmatch(r"[0-9]{1,20}", data.get("auth_date", "")):
        raise InvalidInitData("Invalid auth_date")
    auth_date = int(data["auth_date"])
    current = int(time.time()) if now is None else now
    age = current - auth_date
    if age < -future_tolerance_seconds or age >= max_age_seconds:
        raise InvalidInitData("Launch data outside freshness policy")
    objects: dict[str, dict[str, Any] | None] = {}
    for name in ("user", "chat", "receiver"):
        if name not in data:
            objects[name] = None
            continue
        try:
            value = json.loads(data[name], parse_constant=_reject_constant)
        except (ValueError, TypeError, RecursionError):
            raise InvalidInitData(f"Invalid {name}") from None
        if not isinstance(value, dict):
            raise InvalidInitData(f"Invalid {name}")
        objects[name] = value
    user = objects["user"]
    if user is None or type(user.get("id")) is not int or user["id"] <= 0:
        raise InvalidInitData("Missing signed user identity")
    can_send_after = data.get("can_send_after")
    if can_send_after is not None and not re.fullmatch(r"[0-9]{1,10}", can_send_after):
        raise InvalidInitData("Invalid can_send_after")
    return VerifiedLaunch(
        user_id=user["id"],
        auth_date=auth_date,
        user=_frozen(user),
        query_id=data.get("query_id"),
        chat_type=data.get("chat_type"),
        chat_instance=data.get("chat_instance"),
        start_param=data.get("start_param"),
        can_send_after=None if can_send_after is None else int(can_send_after),
        chat=None if objects["chat"] is None else _frozen(objects["chat"]),
        receiver=None if objects["receiver"] is None else _frozen(objects["receiver"]),
    )


def validate_init_data(
    raw: str,
    bot_token: str,
    *,
    max_age_seconds: int = 3600,
    future_tolerance_seconds: int = 30,
    now: int | None = None,
    max_length: int = 16384,
) -> VerifiedLaunch:
    """Validate raw URL-encoded initData; require a signed user identity.

    A successful result authenticates launch data only. Object permissions,
    session creation and replay-sensitive operations belong to the service.
    """
    if not isinstance(bot_token, str) or not bot_token:
        raise ValidationFailure("bot_token must be configured on the server")
    _check_policy(max_age_seconds, future_tolerance_seconds, max_length, now)
    data = _fields(raw, max_length)
    signature = data.pop("hash", "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", signature):
        raise InvalidInitData("Invalid hash")
    # signature remains in this HMAC string if present; Ed25519 has other rules.
    secret = hmac.digest(b"WebAppData", bot_token.encode("utf-8"), "sha256")
    expected = hmac.digest(secret, _check_string(data), "sha256")
    if not hmac.compare_digest(expected, bytes.fromhex(signature)):
        raise InvalidInitData("Invalid signature")
    return _launch(data, now, max_age_seconds, future_tolerance_seconds)


def validate_init_data_signature(
    raw: str,
    bot_id: int,
    *,
    environment: Literal['production', 'test'] = 'production',
    public_key: bytes | None = None,
    max_age_seconds: int = 3600,
    future_tolerance_seconds: int = 30,
    now: int | None = None,
    max_length: int = 16384,
) -> VerifiedLaunch:
    """Validate raw initData without the bot token: the Ed25519 `signature` field and Telegram's public key.

    For a third party that knows only bot_id. The checked string is "<bot_id>:WebAppData" and every
    field except hash and signature, sorted, one per line. `environment` picks the published key;
    `public_key` (32 raw bytes) replaces it, e.g. after a key change announced by Telegram. Needs the
    `signature` extra (cryptography). Freshness, identity and the result are the same as validate_init_data.
    """
    if type(bot_id) is not int or bot_id <= 0:
        raise ValidationFailure("bot_id must be a positive integer")
    if public_key is None:
        if environment not in TELEGRAM_PUBLIC_KEYS:
            raise ValidationFailure("environment must be 'production' or 'test'")
        public_key = TELEGRAM_PUBLIC_KEYS[environment]
    elif type(public_key) is not bytes or len(public_key) != 32:
        raise ValidationFailure("public_key must be 32 raw bytes")
    _check_policy(max_age_seconds, future_tolerance_seconds, max_length, now)
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        raise UnsupportedCapability("Ed25519 needs the signature extra: pip install '<WHEEL>[signature]'") from None
    data = _fields(raw, max_length)
    signature = data.pop("signature", "")
    data.pop("hash", None)
    # 64 signature bytes are 86 base64url characters, padding optional.
    if not re.fullmatch(r"[A-Za-z0-9_-]{86}(?:==)?", signature):
        raise InvalidInitData("Invalid signature")
    decoded = base64.urlsafe_b64decode(signature.rstrip("=") + "==")
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(decoded, _check_string(data, f"{bot_id}:WebAppData\n"))
    except InvalidSignature:
        raise InvalidInitData("Invalid signature") from None
    return _launch(data, now, max_age_seconds, future_tolerance_seconds)
