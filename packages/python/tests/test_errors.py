import asyncio
from dataclasses import FrozenInstanceError
import json
import unittest

from telegram_patterns import (
    AuthenticationRequired, InvalidCompletion, InvalidInitData, InvalidType,
    OperationConflict, PatternError, PermissionDenied, TimeoutFailure,
    TransportFailure, UnknownOutcome, UnsupportedCapability, ValidationFailure,
    safe_error_report,
)
from telegram_patterns.aiogram import InvalidAPIRequest, InvalidField, action_menu


class ErrorContractTests(unittest.TestCase):
    def test_public_reports_do_not_serialize_secret_exception_text_or_args(self):
        secret = 'BOT_TOKEN=100:PRIVATE initData=SIGNED_BODY'
        for error in (ValueError(secret), ValidationFailure(secret), PermissionDenied(secret),
                      InvalidInitData(secret), InvalidField(secret), UnknownOutcome(secret)):
            with self.subTest(error=type(error).__name__):
                value = safe_error_report(error, operation='write')
                self.assertNotIn(secret, json.dumps(value.as_dict()))
                self.assertEqual(set(value.as_dict()), {'code', 'category', 'outcome', 'recovery', 'message'})
                with self.assertRaises(FrozenInstanceError): value.message = secret

    def test_timeout_and_transport_write_require_reconciliation_read_can_be_repeated(self):
        for error in (TimeoutError('private'), TimeoutFailure('private'), TransportFailure('private')):
            with self.subTest(error=type(error).__name__):
                read = safe_error_report(error, operation='read')
                write = safe_error_report(error, operation='write')
                self.assertEqual((read.outcome, read.recovery), ('read-failed', 'retry-read'))
                self.assertEqual((write.outcome, write.recovery), ('unknown', 'reconcile'))
        self.assertEqual(safe_error_report(TimeoutError()).category, 'timeout')
        self.assertEqual(safe_error_report(TransportFailure()).category, 'network')

    def test_known_pre_effect_rejections_are_distinct_and_keep_old_catches(self):
        cases = [(ValidationFailure('x'), 'validation', 'fix-input'),
                 (PermissionDenied('x'), 'permission', 'check-permissions'),
                 (AuthenticationRequired('x'), 'permission', 'authenticate'),
                 (UnsupportedCapability('x'), 'unsupported', 'use-fallback'),
                 (OperationConflict('x'), 'conflict', 'reconcile')]
        for error, category, recovery in cases:
            with self.subTest(category=category, recovery=recovery):
                report = error.report(operation='write')
                self.assertEqual((report.category, report.recovery, report.outcome), (category, recovery, 'rejected'))
        for error in (ValidationFailure('x'), InvalidInitData('x'), InvalidAPIRequest('x'), InvalidField('x'), OperationConflict('x')):
            self.assertIsInstance(error, ValueError)
            self.assertIsInstance(error, PatternError)
        self.assertIsInstance(InvalidType('x'), TypeError)
        with self.assertRaises(ValidationFailure) as caught: action_menu([], columns=0)
        self.assertEqual(caught.exception.report(operation='write').recovery, 'fix-input')

    def test_raw_errors_and_cancellation_do_not_prove_that_a_write_was_rejected(self):
        for error in (ValueError('bad response after commit'), PermissionError('remote failure'), asyncio.CancelledError(), RuntimeError()):
            with self.subTest(error=type(error).__name__):
                report = safe_error_report(error, operation='write')
                self.assertEqual((report.outcome, report.recovery), ('unknown', 'reconcile'))
        self.assertEqual(safe_error_report(asyncio.CancelledError()).category, 'cancelled')
        self.assertEqual(safe_error_report(PermissionError()).category, 'permission')

    def test_unknown_result_is_not_local_validation_even_when_value_error_compatible(self):
        error = InvalidCompletion('Business effect committed, feedback is invalid')
        self.assertIsInstance(error, ValueError)
        self.assertIsInstance(error, UnknownOutcome)
        self.assertEqual((error.report().outcome, error.report().recovery), ('unknown', 'reconcile'))

    def test_normalizer_does_not_call_exception_string_or_overridden_report(self):
        class HostFailure(PatternError):
            def __str__(self): raise AssertionError('secret formatter must not run')
            def report(self, **options): raise AssertionError('host override must not run')
        report = safe_error_report(HostFailure(), operation='write')
        self.assertEqual((report.code, report.outcome), ('internal', 'unknown'))
        with self.assertRaises(TypeError): safe_error_report({'code': 'permission-denied'})
        with self.assertRaises(ValueError): safe_error_report(RuntimeError(), operation='invented')


if __name__ == '__main__': unittest.main()
