"""Small environment configuration independent of any Telegram SDK."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
from typing import Mapping


@dataclass(frozen=True, slots=True)
class BotSettings:
    """Token is excluded from repr; this does not make serialization safe."""
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.token, str) or any(char.isspace() for char in self.token):
            raise ValueError("Bot token must be a nonempty token string")
        number, separator, secret = self.token.partition(":")
        if not separator or not number.isdigit() or not secret:
            raise ValueError("Invalid bot token format")

    @classmethod
    def from_env(cls, token_var: str = "BOT_TOKEN", *,
                 environ: Mapping[str, str] | None = None) -> BotSettings:
        if not isinstance(token_var, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token_var):
            raise ValueError("Invalid token environment variable name")
        token = (os.environ if environ is None else environ).get(token_var)
        if token is None or token == "":
            raise ValueError(f"Set {token_var} before starting the bot")
        return cls(token=token)
