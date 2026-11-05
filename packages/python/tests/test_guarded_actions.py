"""Guarded local operations keep current access, revision, effect and receipt together."""

from __future__ import annotations

import gc
import json
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
import warnings
from contextlib import closing
from pathlib import Path

from _support import integration
from telegram_patterns import ConflictFailure, InvalidType, OperationConflict, PermissionDenied, SQLiteOnce

CONTEXT = (100, -42, 42, 7, 900)
SCOPE = json.dumps(CONTEXT, separators=(',', ':'))
PAYLOAD = {'resource': 'counter', 'revision': 1, 'target': 5}


def current_check(connection, replayed, *, context=CONTEXT, payload=None):
    payload = PAYLOAD if payload is None else payload
    row = connection.execute('SELECT bot,chat,actor,topic,prompt,revision,allowed FROM resource').fetchone()
    if tuple(row[:5]) != context or row[6] != 1:
        return False
    if not replayed and row[5] != payload['revision']:
        raise ConflictFailure('Current resource revision changed')
    return True


def change(connection, target=5):
    connection.execute('INSERT INTO changes(value) VALUES(?)', (target,))
    connection.execute('UPDATE resource SET revision=revision+1,value=?', (target,))
    return {'id': connection.execute('SELECT last_insert_rowid()').fetchone()[0], 'value': target, 'revision': 2}


def process_operation(database, key, target, barrier, queue, mode='normal'):
    store = SQLiteOnce(database)
    payload = {**PAYLOAD, 'target': target}

    def apply(connection):
        result = change(connection, target)
        if mode == 'crash-before-commit':
            os._exit(73)
        return result

    if barrier is not None:
        barrier.wait(timeout=10)
    try:
        result = store.run_guarded(
            SCOPE,
            key,
            payload,
            apply,
            check=lambda connection, replayed: current_check(connection, replayed, payload=payload),
        )
        if mode == 'crash-after-commit':
            os._exit(74)
        queue.put({'status': 'done', 'replayed': result.replayed, 'value': result.value})
    except Exception as error:
        queue.put({'status': 'error', 'error': type(error).__name__})


class GuardedActionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='guarded actions ')
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'project.sqlite'
        self.store = SQLiteOnce(self.database)
        self.store.initialize()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(
                'CREATE TABLE resource(bot INTEGER,chat INTEGER,actor INTEGER,topic INTEGER,prompt INTEGER,'
                'revision INTEGER,allowed INTEGER,value INTEGER)'
            )
            connection.execute('INSERT INTO resource VALUES(100,-42,42,7,900,1,1,0)')
            connection.execute('CREATE TABLE changes(id INTEGER PRIMARY KEY,value INTEGER)')

    def run_action(self, key='server-issued-operation', *, check=current_check, apply=change, payload=PAYLOAD):
        return self.store.run_guarded(SCOPE, key, payload, apply, check=check)

    def state(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return (
                connection.execute('SELECT count(*) FROM changes').fetchone()[0],
                connection.execute('SELECT count(*) FROM telegram_pattern_operations').fetchone()[0],
                connection.execute('SELECT revision,value FROM resource').fetchone(),
            )

    def assert_pristine(self):
        self.assertEqual(self.state(), (0, 0, (1, 0)))

    def test_new_and_replayed_action_check_the_same_owned_transaction(self):
        observations = []

        def check(connection, replayed):
            self.assertTrue(connection.in_transaction)
            self.assertIs(type(replayed), bool)
            observations.append((connection, replayed))
            return current_check(connection, replayed)

        def apply(connection):
            self.assertIs(connection, observations[-1][0])
            return change(connection)

        first = self.run_action(check=check, apply=apply)
        replay = self.run_action(check=check, apply=lambda connection: self.fail('Duplicate effect'))
        self.assertEqual([item[1] for item in observations], [False, True])
        self.assertEqual((first.replayed, replay.replayed), (False, True))
        self.assertEqual(first.value, replay.value)
        self.assertEqual(self.state(), (1, 1, (2, 5)))

    def test_host_check_helper_that_ends_the_transaction_cannot_return_a_receipt(self):
        def broken_check(connection, replayed):
            # A host helper may replace the authorizer: callbacks are trusted, not sandboxed.
            connection.set_authorizer(None)
            connection.commit()
            return True

        with self.assertRaisesRegex(RuntimeError, 'check must preserve'):
            self.run_action(check=broken_check, apply=lambda connection: self.fail('Effect after lost transaction'))
        self.assert_pristine()

    def test_host_apply_helper_that_ends_the_transaction_cannot_record_success(self):
        def broken_apply(connection):
            connection.set_authorizer(None)
            connection.rollback()
            return {'status': 'not-committed'}

        with self.assertRaisesRegex(RuntimeError, 'apply must not commit'):
            self.run_action(apply=broken_apply)
        self.assert_pristine()

    def test_replay_rechecks_current_acl_and_does_not_expose_revoked_receipt(self):
        self.run_action()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('UPDATE resource SET allowed=0')
        with self.assertRaises(PermissionDenied):
            self.run_action(apply=lambda connection: self.fail('Revoked operation executed'))
        self.assertEqual(self.state(), (1, 1, (2, 5)))

    def test_each_actor_bot_chat_topic_and_prompt_binding_is_checked_before_replay(self):
        self.run_action()
        for field in range(len(CONTEXT)):
            foreign = list(CONTEXT)
            foreign[field] += 1
            with self.subTest(field=field), self.assertRaises(PermissionDenied):
                self.run_action(
                    check=lambda connection, replayed: current_check(connection, replayed, context=tuple(foreign))
                )
        self.assertEqual(self.state(), (1, 1, (2, 5)))

    def test_authorization_denial_precedes_changed_payload_conflict(self):
        self.run_action()
        with self.assertRaises(PermissionDenied):
            self.run_action(check=lambda connection, replayed: False, payload={**PAYLOAD, 'target': 99})
        self.assertEqual(self.state(), (1, 1, (2, 5)))

    def test_same_key_with_changed_payload_is_refused_after_current_check(self):
        self.run_action()
        calls = []

        def check(connection, replayed):
            calls.append(replayed)
            return current_check(connection, replayed)

        with self.assertRaises(OperationConflict):
            self.run_action(payload={**PAYLOAD, 'target': 99}, check=check)
        self.assertEqual(calls, [True])
        self.assertEqual(self.state(), (1, 1, (2, 5)))

    def test_new_key_with_stale_revision_is_refused_without_second_effect(self):
        self.run_action()
        with self.assertRaises(ConflictFailure):
            self.run_action('another-server-issued-operation')
        self.assertEqual(self.state(), (1, 1, (2, 5)))

    def test_replay_returns_detached_original_receipt_even_after_later_revision(self):
        result = self.run_action()
        result.value['value'] = 999
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('UPDATE resource SET revision=3,value=8')
        replay = self.run_action()
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.value, {'id': 1, 'value': 5, 'revision': 2})
        self.assertEqual(self.state(), (1, 1, (3, 8)))

    def test_check_requires_exact_true_not_merely_truthy_value(self):
        for name, decision in [
            ('false', False),
            ('none', None),
            ('integer', 1),
            ('text', 'yes'),
            ('mapping', {'ok': True}),
        ]:
            with self.subTest(decision=name), self.assertRaises(PermissionDenied):
                self.run_action(check=lambda connection, replayed: decision)
            self.assert_pristine()

    def test_check_cannot_write_schema_data_or_control_the_transaction(self):
        attached = str(self.database.with_name('unexpected.sqlite')).replace("'", "''")
        statements = {
            'insert': 'INSERT INTO changes VALUES(1,9)',
            'update': 'UPDATE resource SET value=9',
            'delete': 'DELETE FROM resource',
            'schema': 'CREATE TABLE unexpected(value INTEGER)',
            'commit': 'COMMIT',
            'rollback': 'ROLLBACK',
            'savepoint': 'SAVEPOINT escape',
            'pragma': 'PRAGMA user_version=8',
            'attach': f"ATTACH DATABASE '{attached}' AS extra",
        }
        for mode, statement in statements.items():

            def invalid(connection, replayed):
                connection.execute(statement)
                return True

            with self.subTest(mode=mode), self.assertRaises(sqlite3.DatabaseError):
                self.run_action(check=invalid)
            self.assert_pristine()
        self.assertFalse(self.database.with_name('unexpected.sqlite').exists())

    def test_check_executescript_cannot_escape_the_transaction(self):
        def invalid(connection, replayed):
            connection.executescript('UPDATE resource SET value=9;')
            return True

        with self.assertRaises(sqlite3.DatabaseError):
            self.run_action(check=invalid)
        self.assert_pristine()

    def test_effect_cannot_commit_rollback_or_implicitly_commit(self):
        for mode in ('commit', 'rollback', 'script'):

            def invalid(connection):
                change(connection)
                if mode == 'script':
                    connection.executescript('UPDATE resource SET value=9;')
                else:
                    getattr(connection, mode)()

            with self.subTest(mode=mode), self.assertRaises(sqlite3.DatabaseError):
                self.run_action(apply=invalid)
            self.assert_pristine()

    def test_effect_exception_rolls_back_and_the_same_intent_can_be_retried(self):
        def invalid(connection):
            change(connection)
            raise RuntimeError('Injected local pre-commit failure')

        with self.assertRaises(RuntimeError):
            self.run_action(apply=invalid)
        self.assert_pristine()
        self.assertFalse(self.run_action().replayed)

    def test_unserializable_effect_result_rolls_back_the_business_change(self):
        def invalid(connection):
            change(connection)
            return object()

        with self.assertRaises(TypeError):
            self.run_action(apply=invalid)
        self.assert_pristine()
        self.assertFalse(self.run_action().replayed)

    def test_invalid_payload_is_rejected_before_check_or_effect(self):
        for mode, payload in [('nan', {'value': float('nan')}), ('object', object()), ('key', {1: 'value'})]:
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.run_action(payload=payload, check=lambda connection, replayed: self.fail('Guard executed'))
        self.assert_pristine()

    def test_async_callbacks_are_refused_before_work_and_coroutine_results_are_closed(self):
        async def async_check(connection, replayed):
            return True

        async def async_apply(connection):
            return change(connection)

        class AsyncCheck:
            async def __call__(self, connection, replayed):
                return True

        class AsyncApply:
            async def __call__(self, connection):
                return change(connection)

        for callback in (async_check, AsyncCheck(), None, 42):
            with self.subTest(check=type(callback).__name__), self.assertRaises(InvalidType):
                self.run_action(check=callback)
        for callback in (async_apply, AsyncApply(), None, 42):
            with self.subTest(apply=type(callback).__name__), self.assertRaises(InvalidType):
                self.run_action(apply=callback)
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            with self.assertRaises(InvalidType):
                self.run_action(check=lambda connection, replayed: async_check(connection, replayed))
            with self.assertRaises(InvalidType):
                self.run_action(apply=lambda connection: async_apply(connection))

            def writes_before_returning_coroutine(connection):
                change(connection)
                return async_apply(connection)

            with self.assertRaises(InvalidType):
                self.run_action(apply=writes_before_returning_coroutine)
            gc.collect()
        self.assertEqual(observed, [])
        self.assert_pristine()

    def test_async_generator_callbacks_are_refused_without_running_the_body(self):
        async def invalid_check(connection, replayed):
            self.fail('Async generator check executed')
            yield True

        async def invalid_apply(connection):
            self.fail('Async generator effect executed')
            yield 5

        with self.assertRaises(InvalidType):
            self.run_action(check=invalid_check)
        with self.assertRaises(InvalidType):
            self.run_action(apply=invalid_apply)
        with self.assertRaises(InvalidType):
            self.run_action(check=lambda connection, replayed: invalid_check(connection, replayed))
        with self.assertRaises(InvalidType):
            self.run_action(apply=lambda connection: invalid_apply(connection))
        self.assert_pristine()

    def test_legacy_run_keeps_existing_replay_and_savepoint_contract(self):
        def apply(connection):
            connection.execute('SAVEPOINT business')
            value = change(connection)
            connection.execute('RELEASE business')
            return value

        first = self.store.run(SCOPE, 'legacy', PAYLOAD, apply)
        replay = self.store.run(SCOPE, 'legacy', PAYLOAD, lambda connection: self.fail('Legacy duplicate'))
        self.assertEqual((first.replayed, replay.replayed), (False, True))
        self.assertEqual(first.value, replay.value)
        self.assertEqual(self.state(), (1, 1, (2, 5)))

    def spawn(self, key, target=5, *, barrier=None, queue=None, mode='normal'):
        context = multiprocessing.get_context('spawn')
        process = context.Process(
            target=process_operation, args=(str(self.database), key, target, barrier, queue, mode)
        )
        process.start()

        def close():
            if process.is_alive():
                process.terminate()
            process.join(timeout=10)
            process.close()

        self.addCleanup(close)
        return process

    @integration
    def test_waiting_process_checks_acl_after_the_prior_writer_revokes_access(self):
        context = multiprocessing.get_context('spawn')
        barrier, queue = context.Barrier(2), context.Queue()
        self.addCleanup(queue.close)
        with closing(sqlite3.connect(self.database, isolation_level=None)) as connection:
            connection.execute('BEGIN IMMEDIATE')
            worker = self.spawn('revoked-while-waiting', barrier=barrier, queue=queue)
            barrier.wait(timeout=10)
            connection.execute('UPDATE resource SET allowed=0')
            connection.commit()
        self.assertEqual(queue.get(timeout=15), {'status': 'error', 'error': 'PermissionDenied'})
        worker.join(timeout=10)
        self.assertEqual(worker.exitcode, 0)
        self.assert_pristine()

    @integration
    def test_two_processes_same_key_commit_one_effect_and_replay_one_receipt(self):
        context = multiprocessing.get_context('spawn')
        barrier, queue = context.Barrier(2), context.Queue()
        self.addCleanup(queue.close)
        workers = [self.spawn('shared-operation', barrier=barrier, queue=queue) for _ in range(2)]
        results = [queue.get(timeout=15) for _ in workers]
        for worker in workers:
            worker.join(timeout=10)
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual([result['status'] for result in results], ['done', 'done'])
        self.assertEqual(sorted(result['replayed'] for result in results), [False, True])
        self.assertEqual(results[0]['value'], results[1]['value'])
        self.assertEqual(self.state(), (1, 1, (2, 5)))

    @integration
    def test_two_processes_different_intents_same_revision_have_one_winner(self):
        context = multiprocessing.get_context('spawn')
        barrier, queue = context.Barrier(2), context.Queue()
        self.addCleanup(queue.close)
        workers = [
            self.spawn(key, target, barrier=barrier, queue=queue) for key, target in [('first', 5), ('second', 9)]
        ]
        results = [queue.get(timeout=15) for _ in workers]
        for worker in workers:
            worker.join(timeout=10)
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual(sorted(result['status'] for result in results), ['done', 'error'])
        self.assertEqual(next(result['error'] for result in results if result['status'] == 'error'), 'ConflictFailure')
        state = self.state()
        self.assertEqual(state[:2], (1, 1))
        self.assertEqual(state[2][0], 2)
        self.assertIn(state[2][1], (5, 9))

    @integration
    def test_process_crash_before_commit_rolls_back_effect_and_receipt(self):
        worker = self.spawn('crash-operation', mode='crash-before-commit')
        worker.join(timeout=10)
        self.assertEqual(worker.exitcode, 73)
        self.assert_pristine()
        self.assertFalse(self.run_action('crash-operation').replayed)
        self.assertEqual(self.state(), (1, 1, (2, 5)))

    @integration
    def test_process_crash_after_commit_reconciles_the_same_operation_on_restart(self):
        worker = self.spawn('lost-response', mode='crash-after-commit')
        worker.join(timeout=10)
        self.assertEqual(worker.exitcode, 74)
        self.assertEqual(self.state(), (1, 1, (2, 5)))
        restarted = SQLiteOnce(self.database)
        replay = restarted.run_guarded(
            SCOPE,
            'lost-response',
            PAYLOAD,
            lambda connection: self.fail('Repeated committed effect'),
            check=current_check,
        )
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.value, {'id': 1, 'value': 5, 'revision': 2})
        self.assertEqual(self.state(), (1, 1, (2, 5)))


if __name__ == '__main__':
    unittest.main()
