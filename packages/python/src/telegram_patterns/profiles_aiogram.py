"""Compatibility path: the implementation lives in telegram_patterns._aiogram.profiles.

Importing this module returns that same module object, so names, patches and private helpers stay shared.
"""

import sys

from ._aiogram import profiles as _implementation
from ._aiogram.profiles import *  # noqa: F403

sys.modules[__name__] = _implementation
