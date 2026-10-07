"""Test scopes. TELEGRAM_PATTERNS_TESTS=unit skips integration tests; the default run executes everything.

Integration tests start child processes (Python, multiprocessing, generators, builds) or take seconds.
Unit tests run in one process; scripts/run_python_tests.py --unit refuses any child process they start.
"""

import os
import unittest

UNIT_ONLY = os.environ.get('TELEGRAM_PATTERNS_TESTS') == 'unit'


def integration(test):
    """Mark a test (or class) that starts processes or runs generators; skipped in the unit scope."""
    return unittest.skipIf(UNIT_ONLY, 'integration test; run without TELEGRAM_PATTERNS_TESTS=unit')(test)
