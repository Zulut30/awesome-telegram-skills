"""Compatibility path: the implementation lives in telegram_patterns._aiogram.keyboards.

Importing this module returns that same module object, so names, patches and private helpers stay shared.
"""

import sys

from ._aiogram import keyboards as _implementation
from ._aiogram.keyboards import *  # noqa: F403

sys.modules[__name__] = _implementation
