"""Compatibility path: the implementation lives in telegram_patterns._aiogram.platform_operations.

Importing this module returns that same module object, so names, patches and private helpers stay shared.
"""

import sys

from ._aiogram import platform_operations as _implementation
from ._aiogram.platform_operations import *  # noqa: F403

sys.modules[__name__] = _implementation
