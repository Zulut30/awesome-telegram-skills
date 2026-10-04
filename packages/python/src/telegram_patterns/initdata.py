"""Bot-owner HMAC validation. Does not implement OIDC or Ed25519 validation."""
from __future__ import annotations
from .errors import ErrorCode, ValidationFailure

from dataclasses import dataclass
import hmac
import json
import re
import time
from types import MappingProxyType
from typing import Mapping
from urllib.parse import parse_qsl


class InvalidInitData(ValidationFailure):
    """Untrusted launch data; messages do not include raw input or secrets."""
    code: ErrorCode = 'invalid-init-data'


@dataclass(frozen=True)
class VerifiedLaunch:
    user_id: int
    auth_date: int
    user: Mapping[str, object]


def validate_init_data(
    raw: str, bot_token: str, *, max_age_seconds: int = 3600,
    future_tolerance_seconds: int = 30, now: int | None = None,
    max_length: int = 16384,
) -> VerifiedLaunch:
    """Validate raw URL-encoded initData; require a signed user identity.

    A successful result authenticates launch data only. Object permissions,
    session creation and replay-sensitive operations belong to the service.
    """
    if not isinstance(bot_token, str) or not bot_token:
        raise ValidationFailure("bot_token must be configured on the server")
    for name, value, minimum in [("max_age_seconds", max_age_seconds, 1),
                                 ("future_tolerance_seconds", future_tolerance_seconds, 0),
                                 ("max_length", max_length, 1)]:
        if type(value) is not int or value < minimum:
            raise ValidationFailure(f"Invalid {name}")
    if now is not None and (type(now) is not int or now < 0):
        raise ValidationFailure("now must be a nonnegative Unix timestamp")
    if not isinstance(raw, str) or not raw or len(raw) > max_length:
        raise InvalidInitData("Invalid launch data size")
    if re.search(r"%(?![0-9a-fA-F]{2})", raw):
        raise InvalidInitData("Invalid URL encoding")
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True,
                          encoding="utf-8", errors="strict", max_num_fields=64)
    except (ValueError, UnicodeError):
        raise InvalidInitData("Invalid launch encoding") from None
    if not pairs or any(not k for k, _ in pairs) or len({k for k, _ in pairs}) != len(pairs):
        raise InvalidInitData("Ambiguous launch fields")
    data = dict(pairs)
    signature = data.pop("hash", "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", signature):
        raise InvalidInitData("Invalid hash")
    # signature remains in this HMAC string if present; Ed25519 has other rules.
    check = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    try:
        encoded_check = check.encode("utf-8")
    except UnicodeError:
        raise InvalidInitData("Invalid launch encoding") from None
    secret = hmac.digest(b"WebAppData", bot_token.encode("utf-8"), "sha256")
    expected = hmac.digest(secret, encoded_check, "sha256")
    if not hmac.compare_digest(expected, bytes.fromhex(signature)):
        raise InvalidInitData("Invalid signature")
    if not re.fullmatch(r"[0-9]{1,20}", data.get("auth_date", "")):
        raise InvalidInitData("Invalid auth_date")
    auth_date = int(data["auth_date"])
    current = int(time.time()) if now is None else now
    age = current - auth_date
    if age < -future_tolerance_seconds or age >= max_age_seconds:
        raise InvalidInitData("Launch data outside freshness policy")
    try:
        user = json.loads(data.get("user", ""))
    except (ValueError, TypeError, RecursionError):
        raise InvalidInitData("Invalid user") from None
    if not isinstance(user, dict) or type(user.get("id")) is not int or user["id"] <= 0:
        raise InvalidInitData("Missing signed user identity")
    return VerifiedLaunch(user_id=user["id"], auth_date=auth_date, user=MappingProxyType(user))
