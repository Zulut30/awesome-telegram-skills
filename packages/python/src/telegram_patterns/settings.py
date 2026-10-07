"""Small environment configuration independent of any Telegram SDK."""
from __future__ import annotations
from .errors import ValidationFailure

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Mapping

_ENV_FILE_LIMIT = 65536
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _read_env_file(path: Path) -> dict[str, str]:
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
        if not separator or not _KEY.fullmatch(key):
            raise ValidationFailure(f"Invalid line {number} in {path.name}: expected KEY=VALUE")  # value never echoed
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '\'"':
            value = value[1:-1]
        else:
            value = value.split(' #', 1)[0].rstrip()
        values[key] = value
    return values


@dataclass(frozen=True, slots=True)
class BotSettings:
    """Token is excluded from repr; this does not make serialization safe."""
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.token, str) or any(char.isspace() for char in self.token):
            raise ValidationFailure("Bot token must be a nonempty token string")
        number, separator, secret = self.token.partition(":")
        if not separator or not number.isdigit() or not secret:
            raise ValidationFailure("Invalid bot token format")

    @classmethod
    def from_env(cls, token_var: str = "BOT_TOKEN", *,
                 environ: Mapping[str, str] | None = None,
                 env_file: str | Path | None = None) -> BotSettings:
        """Read the token from the environment; an optional .env file fills only missing values.

        The file is parsed as plain KEY=VALUE lines and never changes os.environ.
        """
        if not isinstance(token_var, str) or not _KEY.fullmatch(token_var):
            raise ValidationFailure("Invalid token environment variable name")
        values: dict[str, str] = {}
        if env_file is not None and Path(env_file).is_file():
            values.update(_read_env_file(Path(env_file)))
        values.update(os.environ if environ is None else environ)
        token = values.get(token_var)
        if token is None or token == "":
            where = f" or in {Path(env_file).name}" if env_file is not None else ""
            raise ValidationFailure(f"Set {token_var} in the environment{where} before starting the bot")
        if "REPLACE_WITH" in token:
            raise ValidationFailure(f"Replace the {token_var} placeholder with the token issued by @BotFather")
        return cls(token=token)
