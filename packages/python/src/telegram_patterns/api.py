"""Discover and construct ALL methods supported by the installed aiogram SDK."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

import aiogram.methods as methods
from aiogram.methods.base import TelegramMethod
from pydantic import ValidationError


class InvalidAPIRequest(ValueError):
    """Controlled failure with no payload values, secrets or SDK error dump."""


@dataclass(frozen=True, slots=True)
class MethodSpec:
    name: str
    sdk_class: str
    fields: tuple[str, ...]
    required: tuple[str, ...]
    url: str


@lru_cache(maxsize=1)
def _methods() -> Mapping[str, type[TelegramMethod[Any]]]:
    return {value.__api_method__: value for value in vars(methods).values()
            if isinstance(value, type) and issubclass(value, TelegramMethod)
            and isinstance(getattr(value, '__api_method__', None), str)}


def method_catalog() -> tuple[MethodSpec, ...]:
    """Runtime SDK capabilities; never a statement of server rights/live testing."""
    return tuple(MethodSpec(name, model.__name__, tuple(model.model_fields),
                            tuple(key for key, field in model.model_fields.items() if field.is_required()),
                            'https://core.telegram.org/bots/api#' + name.lower())
                 for name, model in sorted(_methods().items()))


def build_request(name: str, parameters: Mapping[str, Any] | None = None) -> TelegramMethod[Any]:
    """Native SDK request, no network. Use await existing_bot(request) explicitly.

    Top-level unknown fields are rejected instead of silently forwarded. Nested
    validation follows SDK; context/rights/limits/action semantics are the host's
    responsibility. InputFile models may be passed; no implicit file reads.
    """
    if not isinstance(name, str) or name not in _methods():
        raise InvalidAPIRequest('Unknown or unsupported Telegram method in the installed SDK')
    if parameters is not None and not isinstance(parameters, Mapping):
        raise InvalidAPIRequest('Parameters must be a mapping')
    model = _methods()[name]
    data = dict(parameters or {})
    if any(not isinstance(key, str) or key not in model.model_fields for key in data):
        raise InvalidAPIRequest('Unknown top-level Telegram method parameter')
    try:
        return model.model_validate(data)
    except (ValidationError, TypeError, ValueError):
        raise InvalidAPIRequest('Invalid parameters for the selected Telegram method') from None
