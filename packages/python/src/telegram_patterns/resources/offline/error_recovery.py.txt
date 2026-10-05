"""Offline: lost response after commit, explicit reconciliation of the SAME key."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from telegram_patterns import SQLiteOnce, safe_error_report


def main() -> None:
    with TemporaryDirectory(prefix='telegram-errors-') as folder:
        database = Path(folder) / 'orders.sqlite'
        once = SQLiteOnce(database)
        once.initialize()
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('CREATE TABLE orders(id INTEGER PRIMARY KEY, product TEXT)')
        scope, key, payload = 'verified-actor:42', 'order-opaque-001', {'product': 'fixture'}
        try:
            once.run(scope, key, payload, lambda db: {'id': db.execute(
                'INSERT INTO orders(product) VALUES (?)', (payload['product'],)).lastrowid})
            raise TimeoutError('fixture: response lost AFTER successful commit')
        except TimeoutError as error:
            failure = safe_error_report(error, operation='write')
        assert failure.recovery == 'reconcile' and failure.outcome == 'unknown'
        # This is an explicit status/replay check with the SAME authorized scope
        # and immutable key. A new key would represent a new operation.
        def must_not_apply(db):
            raise AssertionError('Reconciliation duplicated the effect')
        result = once.run(scope, key, payload, must_not_apply)
        with closing(sqlite3.connect(database)) as db:
            count = db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
        assert result.replayed and count == 1
        print(json.dumps({'passed': True, 'network': False, 'effect_count': count,
                          'replayed': result.replayed, 'failure': failure.as_dict()}))


if __name__ == '__main__': main()
