"""Current permissions, revision and receipt are checked in a real file transaction."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import warnings

from telegram_patterns import (ConflictFailure, InvalidType, OperationConflict,
                               PermissionDenied, SQLiteOnce)


class GuardedOnceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='guarded business operation ')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'project.sqlite'
        self.store = SQLiteOnce(self.path)
        self.store.initialize()
        self.scope = 'bot:100/chat:42/owner:42/topic:7/message:900'
        self.context = (100,42,42,7,900)
        self.payload = {'revision':1,'target':5}
        self.seen = []
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute('CREATE TABLE resource(bot INTEGER,chat INTEGER,owner INTEGER,topic INTEGER,message INTEGER,revision INTEGER,allowed INTEGER,value INTEGER)')
            c.execute('INSERT INTO resource VALUES(100,42,42,7,900,1,1,0)')
            c.execute('CREATE TABLE changes(id INTEGER PRIMARY KEY,value INTEGER)')

    def check(self, c, replayed, *, context=None):
        self.seen.append(replayed)
        row = c.execute('SELECT bot,chat,owner,topic,message,revision,allowed FROM resource').fetchone()
        if tuple(row[:5]) != (self.context if context is None else context) or row[6] != 1:
            return False
        if not replayed and row[5] != self.payload['revision']:
            raise ConflictFailure('Current domain revision changed')
        return True

    def apply(self, c):
        c.execute('INSERT INTO changes(value) VALUES(?)', (5,))
        c.execute('UPDATE resource SET revision=revision+1,value=5')
        return {'id':c.execute('SELECT last_insert_rowid()').fetchone()[0],'value':5,'revision':2}

    def run_operation(self, key='server-issued-operation', *, check=None, apply=None, payload=None):
        return self.store.run_guarded(self.scope,key,self.payload if payload is None else payload,
                                     self.apply if apply is None else apply,check=self.check if check is None else check)

    def counts(self):
        with closing(sqlite3.connect(self.path)) as c:
            return (c.execute('SELECT count(*) FROM changes').fetchone()[0],
                    c.execute('SELECT count(*) FROM telegram_pattern_operations').fetchone()[0],
                    c.execute('SELECT revision,value FROM resource').fetchone())

    def test_current_checks_use_same_transaction_for_new_and_replay(self):
        connections = []
        def check(c,replayed):
            self.assertTrue(c.in_transaction)
            connections.append(c)
            return self.check(c,replayed)
        def apply(c):
            self.assertIs(c,connections[-1])
            return self.apply(c)
        first = self.run_operation(check=check,apply=apply)
        replay = self.run_operation(check=check,apply=lambda c: self.fail('duplicate effect'))
        self.assertEqual(first.value,replay.value)
        self.assertEqual(self.seen,[False,True])
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(self.counts(),(1,1,(2,5)))

    def test_revoked_current_acl_denies_saved_receipt(self):
        self.run_operation()
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute('UPDATE resource SET allowed=0')
        with self.assertRaises(PermissionDenied):
            self.run_operation(apply=lambda c:self.fail('revoked effect'))
        self.assertEqual(self.seen,[False,True])
        self.assertEqual(self.counts(),(1,1,(2,5)))

    def test_each_foreign_actor_and_origin_field_denied_before_receipt(self):
        self.run_operation()
        for index in range(5):
            changed = list(self.context)
            changed[index] += 1
            with self.subTest(index=index), self.assertRaises(PermissionDenied):
                self.run_operation(check=lambda c,r:self.check(c,r,context=tuple(changed)),
                                   apply=lambda c:self.fail('foreign effect'))
        self.assertEqual(self.counts(),(1,1,(2,5)))

    def test_acl_denial_precedes_changed_payload_conflict(self):
        self.run_operation()
        with self.assertRaises(PermissionDenied):
            self.run_operation(check=lambda c,r:False,payload={'revision':1,'target':99})
        self.assertEqual(self.counts(),(1,1,(2,5)))

    def test_changed_original_payload_conflicts_after_current_check(self):
        self.run_operation()
        with self.assertRaises(OperationConflict):
            self.run_operation(payload={'revision':1,'target':99})
        self.assertEqual(self.seen,[False,True])
        self.assertEqual(self.counts(),(1,1,(2,5)))

    def test_new_operation_with_stale_revision_does_not_create_second_change(self):
        self.run_operation()
        with self.assertRaises(ConflictFailure):
            self.run_operation('different-server-operation')
        self.assertEqual(self.counts(),(1,1,(2,5)))

    def test_two_workers_same_operation_return_one_new_and_one_replay(self):
        barrier = threading.Barrier(2)
        def worker():
            barrier.wait(timeout=5)
            return self.run_operation()
        with ThreadPoolExecutor(max_workers=2) as executor:
            a,b = executor.submit(worker),executor.submit(worker)
            results = [a.result(timeout=10),b.result(timeout=10)]
        self.assertEqual(sorted(r.replayed for r in results),[False,True])
        self.assertEqual(results[0].value,results[1].value)
        self.assertEqual(self.counts(),(1,1,(2,5)))

    def test_two_different_operations_same_revision_have_one_winner(self):
        barrier = threading.Barrier(2)
        def worker(key):
            barrier.wait(timeout=5)
            try:
                return self.run_operation(key).replayed
            except ConflictFailure:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as executor:
            a,b = executor.submit(worker,'first-intent'),executor.submit(worker,'second-intent')
            outcomes = [a.result(timeout=10),b.result(timeout=10)]
        self.assertEqual(outcomes.count(False),1)
        self.assertEqual(outcomes.count('conflict'),1)
        self.assertEqual(self.counts(),(1,1,(2,5)))

    def test_check_is_read_only_and_cannot_control_transaction(self):
        attach_path = str(Path(self.temp.name)/'unexpected.sqlite').replace("'", "''")
        statements = ('INSERT INTO changes VALUES(1,9)','UPDATE resource SET value=9',
                      'DELETE FROM resource','COMMIT','ROLLBACK','SAVEPOINT escape',
                      'PRAGMA user_version=8',f"ATTACH DATABASE '{attach_path}' AS extra")
        for statement in statements:
            def invalid(c,replayed):
                c.execute(statement)
                return True
            with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError):
                self.run_operation(check=invalid)
            self.assertEqual(self.counts(),(0,0,(1,0)))
        self.assertEqual({p.name for p in Path(self.temp.name).iterdir()},{'project.sqlite'})

    def test_guard_executescript_cannot_escape_owned_transaction(self):
        def invalid(c,replayed):
            c.executescript('UPDATE resource SET value=9;')
            return True
        with self.assertRaises(sqlite3.DatabaseError):
            self.run_operation(check=invalid)
        self.assertEqual(self.counts(),(0,0,(1,0)))

    def test_effect_commit_and_executescript_still_rollback_after_check(self):
        for mode in ('commit','rollback','script'):
            def invalid(c):
                c.execute('INSERT INTO changes VALUES(1,9)')
                if mode=='commit': c.commit()
                elif mode=='rollback': c.rollback()
                else: c.executescript('UPDATE resource SET value=9;')
                return {'unexpected':True}
            with self.subTest(mode=mode), self.assertRaises(sqlite3.DatabaseError):
                self.run_operation(apply=invalid)
            self.assertEqual(self.counts(),(0,0,(1,0)))

    def test_effect_exception_rolls_back_change_revision_and_receipt(self):
        def fail(c):
            self.apply(c)
            raise RuntimeError('injected project failure')
        with self.assertRaises(RuntimeError):
            self.run_operation(apply=fail)
        self.assertEqual(self.counts(),(0,0,(1,0)))
        self.assertFalse(self.run_operation().replayed)
        self.assertEqual(self.counts(),(1,1,(2,5)))

    def test_bad_result_rolls_back_then_same_intent_can_be_explicitly_reconciled(self):
        def invalid(c):
            self.apply(c)
            return object()
        with self.assertRaises(TypeError):
            self.run_operation(apply=invalid)
        self.assertEqual(self.counts(),(0,0,(1,0)))
        self.assertFalse(self.run_operation().replayed)

    def test_check_requires_exact_true(self):
        for value in (False,None,1,'allowed',{'allowed':True}):
            with self.subTest(value=value), self.assertRaises(PermissionDenied):
                self.run_operation(check=lambda c,r:value)
            self.assertEqual(self.counts(),(0,0,(1,0)))

    def test_async_check_rejected_without_warning_or_effect(self):
        async def invalid(c,replayed):
            return True
        class AsyncCheck:
            async def __call__(self,c,replayed): return True
        for check in (invalid,AsyncCheck(),None,42):
            with self.subTest(check=type(check).__name__), self.assertRaises(InvalidType):
                self.store.run_guarded(self.scope,'id',{},self.apply,check=check)
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            with self.assertRaises(InvalidType):
                self.run_operation(check=lambda c,r:invalid(c,r))
            self.assertEqual(observed,[])
        self.assertEqual(self.counts(),(0,0,(1,0)))

    def test_receipt_is_detached_and_does_not_claim_current_state(self):
        first = self.run_operation()
        first.value['value'] = 999
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute('UPDATE resource SET revision=3,value=8')
        replay = self.run_operation()
        self.assertEqual(replay.value,{'id':1,'value':5,'revision':2})
        self.assertEqual(self.counts(),(1,1,(3,8)))

    def test_payload_preflight_occurs_before_guard_and_effect(self):
        for payload in ({'value':float('nan')},object()):
            with self.subTest(payload=type(payload).__name__), self.assertRaises((ValueError,TypeError)):
                self.run_operation(payload=payload,check=lambda c,r:self.fail('guard after invalid JSON'))
        self.assertEqual(self.counts(),(0,0,(1,0)))

    def test_old_unchecked_run_contract_remains_usable(self):
        result = self.store.run('legacy-host-scoped-operation','old-id',{'old':True},self.apply)
        replay = self.store.run('legacy-host-scoped-operation','old-id',{'old':True},lambda c:self.fail('legacy repeat'))
        self.assertEqual(result.value,replay.value)
        self.assertFalse(result.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(self.seen,[])
        self.assertEqual(self.counts(),(1,1,(2,5)))


if __name__ == '__main__':
    unittest.main()
