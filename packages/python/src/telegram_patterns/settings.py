"""Small environment configuration independent of any Telegram SDK."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from ._shared import ENV_KEY, env_flag, read_env_file
from .errors import ValidationFailure


@dataclass(frozen=True, slots=True)
class BotSettings:
    """Token is excluded from repr; this does not make serialization safe."""

    token: str = field(repr=False)
    test_environment: bool = False  # True routes Bot API calls to https://api.telegram.org/bot<token>/test/<method>

    def __post_init__(self) -> None:
        if type(self.test_environment) is not bool:
            raise ValidationFailure("test_environment must be bool")
        if not isinstance(self.token, str) or any(char.isspace() for char in self.token):
            raise ValidationFailure("Bot token must be a nonempty token string")
        number, separator, secret = self.token.partition(":")
        if not separator or not number.isdigit() or not secret:
            raise ValidationFailure("Invalid bot token format")

    @classmethod
    def from_env(
        cls,
        token_var: str = "BOT_TOKEN",
        *,
        environ: Mapping[str, str] | None = None,
        env_file: str | Path | None = None,
        test_environment_var: str = "TELEGRAM_TEST_ENVIRONMENT",
    ) -> BotSettings:
        """Read the token from the environment; an optional .env file fills only missing values.

        The file is parsed as plain KEY=VALUE lines and never changes os.environ.
        test_environment_var set to 1/true/yes/on selects the separate Telegram test environment.
        """
        if not isinstance(token_var, str) or not ENV_KEY.fullmatch(token_var):
            raise ValidationFailure("Invalid token environment variable name")
        if not isinstance(test_environment_var, str) or not ENV_KEY.fullmatch(test_environment_var):
            raise ValidationFailure("Invalid test environment variable name")
        values: dict[str, str] = {}
        if env_file is not None and Path(env_file).is_file():
            values.update(read_env_file(Path(env_file)))
        values.update(os.environ if environ is None else environ)
        token = values.get(token_var)
        if token is None or token == "":
            where = f" or in {Path(env_file).name}" if env_file is not None else ""
            raise ValidationFailure(f"Set {token_var} in the environment{where} before starting the bot")
        if "REPLACE_WITH" in token:
            raise ValidationFailure(f"Replace the {token_var} placeholder with the token issued by @BotFather")
        return cls(token=token, test_environment=env_flag(values.get(test_environment_var, ""), test_environment_var))
