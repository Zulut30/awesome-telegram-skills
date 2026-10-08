"""Compatibility path: the implementation lives in telegram_patterns._aiogram.inline_mode.

Importing this module returns that same module object, so names, patches and private helpers stay shared.
"""

import sys

from ._aiogram import inline_mode as _implementation
from ._aiogram.inline_mode import *  # noqa: F403

sys.modules[__name__] = _implementation
