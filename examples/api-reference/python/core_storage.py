"""SQLite effect/replay; scope/ACL здесь заранее выбраны для публичной fixture."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from telegram_patterns import OnceResult, OnceStore, OperationConflict, SQLiteOnce

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
# HTTP/другой connection не входят в эту транзакцию; авторизация до replay.
print(json.dumps({'passed': True, 'case': 'core_storage', 'network': False}))
