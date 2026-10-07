"""Compatibility path: the implementation lives in telegram_patterns._aiogram.fsm_storage.

Importing this module returns that same module object, so names, patches and private helpers stay shared.
"""

import sys

from ._aiogram import fsm_storage as _implementation
from ._aiogram.fsm_storage import *  # noqa: F403

sys.modules[__name__] = _implementation
