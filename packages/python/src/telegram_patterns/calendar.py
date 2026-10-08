"""Compatibility path: the implementation lives in telegram_patterns.calendar_core.

Importing this module returns that same module object, so names, patches and private helpers stay shared.
"""

import sys

from . import calendar_core as _implementation
from .calendar_core import *  # noqa: F403

sys.modules[__name__] = _implementation
