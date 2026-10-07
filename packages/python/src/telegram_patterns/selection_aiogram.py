"""Compatibility path: the implementation lives in telegram_patterns._aiogram.selection_ui.

Importing this module returns that same module object, so names, patches and private helpers stay shared.
"""

import sys

from ._aiogram import selection_ui as _implementation
from ._aiogram.selection_ui import *  # noqa: F403

sys.modules[__name__] = _implementation
