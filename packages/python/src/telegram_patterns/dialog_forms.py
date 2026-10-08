"""Compatibility path: the implementation lives in telegram_patterns._aiogram.dialog_forms.

Importing this module returns that same module object, so names, patches and private helpers stay shared.
"""

import sys

from ._aiogram import dialog_forms as _implementation
from ._aiogram.dialog_forms import *  # noqa: F403

sys.modules[__name__] = _implementation
