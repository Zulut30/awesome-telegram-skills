"""Compatibility path: the implementation lives in telegram_patterns._aiogram.native_keyboards.

Importing this module returns that same module object, so names, patches and private helpers stay shared.
"""

import sys

from ._aiogram import native_keyboards as _implementation
from ._aiogram.native_keyboards import *  # noqa: F403

sys.modules[__name__] = _implementation
