"""Test scopes. TELEGRAM_PATTERNS_TESTS=unit skips integration tests; the default run executes everything.

Integration tests start child processes (Python, multiprocessing, generators, builds) or take seconds.
Unit tests run in one process; scripts/run_python_tests.py --unit refuses any child process they start.
"""

import os
import unittest
from importlib.metadata import PackageNotFoundError, version

UNIT_ONLY = os.environ.get('TELEGRAM_PATTERNS_TESTS') == 'unit'


def integration(test):
    """Mark a test (or class) that starts processes or runs generators; skipped in the unit scope."""
    return unittest.skipIf(UNIT_ONLY, 'integration test; run without TELEGRAM_PATTERNS_TESTS=unit')(test)


def _aiogram_release() -> tuple[int, int]:
    try:
        major, minor = version('aiogram').split('.')[:2]
        return int(major), int(minor)
    except (PackageNotFoundError, ValueError):
        return (0, 0)


AIOGRAM = _aiogram_release()


def requires_aiogram(minimum: tuple[int, int], feature: str):
    """Skip on an older aiogram; the CI matrix runs the suite on every tested release (3.29-3.31)."""
    return unittest.skipIf(AIOGRAM < minimum, f'{feature} needs aiogram {minimum[0]}.{minimum[1]}+')
