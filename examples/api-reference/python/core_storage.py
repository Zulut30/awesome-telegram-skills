"""SQLite effect/replay; scope/ACL здесь заранее выбраны для публичной fixture."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from telegram_patterns import ConflictFailure, GuardedOnceStore, OnceResult, OnceStore, OperationConflict, PermissionDenied, SQLiteOnce

with TemporaryDirectory() as folder:
    path = Path(folder) / 'fixture.sqlite'
    store: OnceStore[sqlite3.Connection] = SQLiteOnce(path)
    store.initialize()
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE entries(label TEXT)')
    def apply(transaction: sqlite3.Connection) -> dict[str, str]:
        transaction.execute('INSERT INTO entries VALUES (?)', ('public-fixture',))
        return {'status': 'recorded'}
    result: OnceResult = store.run('fixture-actor:42', 'operation-1', {'label': 'public-fixture'}, apply)
    replay = store.run('fixture-actor:42', 'operation-1', {'label': 'public-fixture'}, apply)
    assert result.value == replay.value and not result.replayed and replay.replayed
    try:
        store.run('fixture-actor:42', 'operation-1', {'label': 'changed'}, apply)
    except OperationConflict:
        pass
    else:
        raise AssertionError('Changed payload accepted')
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT COUNT(*) FROM entries').fetchone()[0] == 1
    # Current ACL and domain revision must share the effect transaction.
    guarded: GuardedOnceStore[sqlite3.Connection] = SQLiteOnce(path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE resource(revision INTEGER,allowed INTEGER)')
        db.execute('INSERT INTO resource VALUES(1,1)')
    def check(db: sqlite3.Connection, replayed: bool) -> bool:
        revision, allowed = db.execute('SELECT revision,allowed FROM resource').fetchone()
        if not allowed: return False
        if not replayed and revision != 1: raise ConflictFailure('Domain revision changed')
        return True
    def guarded_apply(db: sqlite3.Connection) -> dict[str,str]:
        db.execute('INSERT INTO entries VALUES (?)',('public-guarded',))
        db.execute('UPDATE resource SET revision=revision+1')
        return {'status':'guarded'}
    guarded_result = guarded.run_guarded('host-origin-fixture','original-operation',{'revision':1},guarded_apply,check=check)
    assert not guarded_result.replayed
    assert guarded.run_guarded('host-origin-fixture','original-operation',{'revision':1},guarded_apply,check=check).replayed
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('UPDATE resource SET allowed=0')
    try:
        guarded.run_guarded('host-origin-fixture','original-operation',{'revision':1},guarded_apply,check=check)
    except PermissionDenied:
        pass
    else:
        raise AssertionError('Revoked ACL exposed saved receipt')
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT COUNT(*) FROM entries').fetchone()[0] == 2
# HTTP/другой connection не входят в эту транзакцию; авторизация до replay.
print(json.dumps({'passed': True, 'case': 'core_storage', 'network': False}))
