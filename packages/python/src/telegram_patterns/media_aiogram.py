"""Compatibility path: the implementation lives in telegram_patterns._aiogram.media.

Importing this module returns that same module object, so names, patches and private helpers stay shared.
"""

import sys

from ._aiogram import media as _implementation
from ._aiogram.media import *  # noqa: F403

sys.modules[__name__] = _implementation
