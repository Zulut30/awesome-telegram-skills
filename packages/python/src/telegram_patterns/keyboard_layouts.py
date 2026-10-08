"""Compatibility path: the implementation lives in telegram_patterns._aiogram.keyboard_layouts.

Importing this module returns that same module object, so names, patches and private helpers stay shared.
"""

import sys

from ._aiogram import keyboard_layouts as _implementation
from ._aiogram.keyboard_layouts import *  # noqa: F403

sys.modules[__name__] = _implementation
