"""Real SQLite/filesystem/process verification of public SQLite recovery and CLI."""

from __future__ import annotations

import hashlib
import io
import json
import multiprocessing
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from _support import integration

import telegram_patterns.sqlite_recovery as recovery
from telegram_patterns import (
    OutboxClaim,
    OutboxRecord,
    SQLiteOutbox,
    SQLiteRecoveryError,
    SQLiteRecoveryResult,
    backup_sqlite,
    restore_sqlite_new,
)
from telegram_patterns.cli import main


def create_database(path, *, large=False):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE child(id INTEGER PRIMARY KEY,parent_id INTEGER REFERENCES parent(id))")
        db.execute("INSERT INTO parent VALUES (1)")
        db.execute("INSERT INTO child VALUES (1,1)")
        db.execute("CREATE TABLE financial_operations(operation_id TEXT PRIMARY KEY,state TEXT,provider_ref TEXT)")
        db.executemany(
            "INSERT INTO financial_operations VALUES (?,?,?)",
            [
                ("intent-pending", "pending", None),
                ("intent-sending", "sending", "native:in-flight"),
                ("intent-unknown", "unknown", "native:do-not-resend"),
                ("intent-confirmed", "confirmed", "native:done"),
            ],
        )
        db.execute("CREATE TABLE items(id INTEGER PRIMARY KEY,payload BLOB)")
        db.execute("INSERT INTO items VALUES (1,?)", (b"fixture",))
        if large:
            db.executemany(
                "INSERT INTO items VALUES (?,?)",
                ((i, b"x" * 4096) for i in range(2, 1202)),
            )


def rows(path):
    with closing(sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute(
            "SELECT operation_id,state,provider_ref FROM financial_operations ORDER BY operation_id"
        ).fetchall()


def copy_worker(source, destination, source_root, target_root, results, gate=None, crash=None):
    original = recovery._publish_new_file

    def publish(*args):
        if gate is not None:
            gate.wait(15)
        if crash == "before":
            os._exit(41)
        original(*args)
        if crash == "after":
            os._exit(42)

    recovery._publish_new_file = publish
    try:
        result = recovery.backup_sqlite(
            source,
            destination,
            source_root=source_root,
            destination_root=target_root,
            deadline_seconds=10,
        )
        if results is not None:
            results.put(("passed", result.sha256, result.cleanup_complete))
    except recovery.SQLiteRecoveryError as error:
        if results is not None:
            results.put((error.code, error.phase, None))


def writer_worker(database, commands, responses, *, exclusive=False):
    with closing(sqlite3.connect(database, isolation_level=None, timeout=0)) as db:
        if exclusive:
            db.execute("BEGIN EXCLUSIVE")
            db.execute(
                "UPDATE financial_operations SET provider_ref='uncommitted-private' WHERE operation_id='intent-unknown'"
            )
            responses.put("exclusive-ready")
            commands.get(timeout=20)
            db.rollback()
            return
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
        responses.put("wal-ready")
        while True:
            action = commands.get(timeout=30)
            if action == "stop":
                break
            operation_id = action[1]
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO parent VALUES (?)", (operation_id,))
            db.execute("INSERT INTO child VALUES (?,?)", (operation_id, operation_id))
            db.execute(
                "INSERT INTO financial_operations VALUES (?,?,?)",
                (f"wal-intent-{operation_id}", "unknown", "native:wal-committed"),
            )
            db.commit()
            responses.put(("committed", operation_id))


class _RecoveryFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="telegram-recovery-")
        self.base = Path(self.temporary.name).resolve()
        self.assertTrue(self.base.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertTrue(self.base.name.startswith("telegram-recovery-"))
        self.source_root, self.target_root = self.base / "source", self.base / "target"
        self.source_root.mkdir(mode=0o700)
        self.target_root.mkdir(mode=0o700)
        self.source, self.target = (
            self.source_root / "live.sqlite",
            self.target_root / "snapshot.sqlite",
        )
        create_database(self.source)
        self.caller = self.target_root / "caller-owned.txt"
        self.caller.write_bytes(b"CALLER-FILE-UNCHANGED")

    def tearDown(self):
        self.assertTrue(self.base.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertTrue(self.base.name.startswith("telegram-recovery-"))
        self.temporary.cleanup()

    def backup(self, destination=None, **options):
        return recovery.backup_sqlite(
            self.source,
            self.target if destination is None else destination,
            source_root=self.source_root,
            destination_root=self.target_root,
            **options,
        )

    def assert_no_preparation(self):
        self.assertEqual(list(self.target_root.glob(".sqlite-recovery-*")), [])
        self.assertEqual(self.caller.read_bytes(), b"CALLER-FILE-UNCHANGED")


class RecoveryTests(_RecoveryFixture):
    @integration
    def test_restored_public_outbox_keeps_unknown_intent_and_never_authorizes_another_send(self):
        scope, operation_key = 'bot:100:restore', 'order:original-intent'
        payload = {'order_id': 'order:1', 'method': 'sendMessage', 'chat_id': 42}
        outbox = SQLiteOutbox(self.source)
        outbox.initialize()
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE business_order(id TEXT PRIMARY KEY,state TEXT,operation_key TEXT UNIQUE)')
            db.execute('INSERT INTO business_order VALUES (?,?,?)', ('order:1', 'awaiting-receipt', operation_key))
            receipt = outbox.enqueue(db, scope, operation_key, payload, now=10)
        self.assertEqual((receipt.operation_key, receipt.state, receipt.duplicate), (operation_key, 'pending', False))
        claim = outbox.claim(scope, 'original-sender', lease_seconds=1, now=10)
        self.assertIsInstance(claim, OutboxClaim)
        self.assertEqual(outbox.recover_expired(scope, now=11), 1)
        original = outbox.get(scope, operation_key)
        self.assertIsInstance(original, OutboxRecord)
        self.assertEqual(
            (original.operation_key, original.state, original.revision, original.attempts),
            (operation_key, 'unknown', 2, 1),
        )
        source_bytes = self.source.read_bytes()

        backup = backup_sqlite(
            self.source, self.target, source_root=self.source_root, destination_root=self.target_root
        )
        restored_path = self.source_root / 'restored-business-new.sqlite'
        restored = restore_sqlite_new(
            self.target, restored_path, source_root=self.target_root, destination_root=self.source_root
        )
        self.assertTrue(backup.cleanup_complete and restored.cleanup_complete)
        reopened = SQLiteOutbox(restored_path)
        reopened.initialize()
        self.assertEqual(reopened.get(scope, operation_key), original)
        with closing(sqlite3.connect(restored_path)) as db:
            self.assertEqual(
                db.execute('SELECT id,state,operation_key FROM business_order').fetchall(),
                [('order:1', 'awaiting-receipt', operation_key)],
            )
        self.assertEqual(reopened.recover_expired(scope, now=10_000), 0)
        self.assertIsNone(reopened.claim(scope, 'restored-worker', now=10_000))
        self.assertEqual(reopened.get(scope, operation_key), original)
        self.assertEqual(self.source.read_bytes(), source_bytes)
        self.assertEqual(outbox.get(scope, operation_key), original)
        self.assertEqual(self.caller.read_bytes(), b'CALLER-FILE-UNCHANGED')
        self.assert_no_preparation()

    def test_four_recovery_symbols_are_public_and_results_hide_private_destination(self):
        self.assertIs(backup_sqlite, recovery.backup_sqlite)
        self.assertIs(restore_sqlite_new, recovery.restore_sqlite_new)
        self.assertIs(SQLiteRecoveryError, recovery.SQLiteRecoveryError)
        result = self.backup()
        self.assertIsInstance(result, SQLiteRecoveryResult)
        self.assertNotIn(str(self.target), repr(result))
        if os.name == 'nt':
            self.assertFalse(result.directory_synced)

    def test_backup_restore_new_integrity_checksums_and_all_financial_intents_are_preserved(
        self,
    ):
        original = rows(self.source)
        source_bytes = self.source.read_bytes()
        result = self.backup()
        restored = self.target_root / "restored-new.sqlite"
        restored_result = recovery.restore_sqlite_new(
            self.target,
            restored,
            source_root=self.target_root,
            destination_root=self.target_root,
        )
        self.assertEqual(rows(restored), original)
        self.assertEqual(rows(self.source), original)
        self.assertEqual(self.source.read_bytes(), source_bytes)
        self.assertEqual(result.sha256, hashlib.sha256(self.target.read_bytes()).hexdigest())
        self.assertEqual(restored_result.sha256, hashlib.sha256(restored.read_bytes()).hexdigest())
        self.assertEqual((result.operation, restored_result.operation), ("backup", "restore-new"))
        self.assertGreater(result.pages, 0)
        self.assertEqual(result.bytes, self.target.stat().st_size)
        self.assertTrue(result.cleanup_complete and restored_result.cleanup_complete)
        self.assert_no_preparation()

    def test_existing_readonly_target_and_running_database_are_never_overwritten(self):
        self.target.write_bytes(b"EXISTING-CALLER-CONTENT")
        self.target.chmod(stat.S_IREAD)
        try:
            with self.assertRaises(recovery.SQLiteRecoveryError) as failure:
                self.backup()
            self.assertEqual(failure.exception.code, "destination-exists")
            self.assertEqual(self.target.read_bytes(), b"EXISTING-CALLER-CONTENT")
        finally:
            self.target.chmod(stat.S_IREAD | stat.S_IWRITE)
        before = self.source.read_bytes()
        with self.assertRaises(recovery.SQLiteRecoveryError) as failure:
            recovery.restore_sqlite_new(
                self.source,
                self.source,
                source_root=self.source_root,
                destination_root=self.source_root,
            )
        self.assertEqual(failure.exception.code, "source-target-conflict")
        self.assertEqual(self.source.read_bytes(), before)
        self.assert_no_preparation()

    def test_hardlinked_destination_conflict_preserves_both_names(self):
        os.link(self.source, self.target)
        before = self.source.read_bytes()
        with self.assertRaises(recovery.SQLiteRecoveryError) as failure:
            self.backup()
        self.assertEqual(failure.exception.code, "source-target-conflict")
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(self.source.read_bytes(), before)
        self.assert_no_preparation()

    def test_readonly_source_is_supported_without_changing_its_bytes(self):
        before = self.source.read_bytes()
        self.source.chmod(stat.S_IREAD)
        try:
            result = self.backup()
            self.assertTrue(result.cleanup_complete)
            self.assertEqual(self.source.read_bytes(), before)
            self.assertEqual(rows(self.target), rows(self.source))
        finally:
            self.source.chmod(stat.S_IREAD | stat.S_IWRITE)
        self.assert_no_preparation()

    def test_traversal_absolute_escape_missing_source_and_nonfinite_deadlines_are_refused(
        self,
    ):
        for index, path in enumerate(["../escaped.sqlite", self.base / "escaped.sqlite"]):
            with (
                self.subTest(case=index),
                self.assertRaises(recovery.SQLiteRecoveryError) as failure,
            ):
                self.backup(path)
            self.assertEqual(failure.exception.code, "invalid-path")
        for index, seconds in enumerate([0, -1, 301, float("nan"), float("inf"), True]):
            with (
                self.subTest(case=index),
                self.assertRaises(recovery.SQLiteRecoveryError) as failure,
            ):
                self.backup(deadline_seconds=seconds)
            self.assertEqual(failure.exception.code, "invalid-arguments")
        with self.assertRaises(recovery.SQLiteRecoveryError) as failure:
            recovery.backup_sqlite(
                "missing.sqlite",
                self.target,
                source_root=self.source_root,
                destination_root=self.target_root,
            )
        self.assertEqual(failure.exception.code, "source-missing")
        self.assertFalse(self.target.exists())
        self.assert_no_preparation()

    def test_malformed_and_truncated_database_never_publish_and_cleanup_owned_preparation(
        self,
    ):
        for index, contents in enumerate([b"SECRET-CANARY-not-a-database" * 8, self.source.read_bytes()[:512]]):
            source = self.source_root / f"invalid-{index}.sqlite"
            source.write_bytes(contents)
            with (
                self.subTest(case=index),
                self.assertRaises(recovery.SQLiteRecoveryError) as failure,
            ):
                recovery.backup_sqlite(
                    source,
                    self.target,
                    source_root=self.source_root,
                    destination_root=self.target_root,
                )
            self.assertEqual(failure.exception.code, "invalid-database")
            self.assertEqual(source.read_bytes(), contents)
            self.assertFalse(self.target.exists())
            self.assert_no_preparation()

    def test_foreign_key_violation_is_rejected_even_when_structure_is_valid(self):
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute("INSERT INTO child VALUES (99,999)")
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
        before = self.source.read_bytes()
        with self.assertRaises(recovery.SQLiteRecoveryError) as failure:
            self.backup()
        self.assertEqual(failure.exception.code, "foreign-key-invalid")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse(self.target.exists())
        self.assert_no_preparation()

    def test_internal_error_messages_are_redacted_and_only_owned_files_are_cleaned(
        self,
    ):
        canary = "DO-NOT-LOG-PRIVATE-PROVIDER-CONTENT"
        with (
            patch.object(recovery, "_snapshot", side_effect=sqlite3.DatabaseError(canary)),
            self.assertRaises(recovery.SQLiteRecoveryError) as failure,
        ):
            self.backup()
        formatted = "".join(traceback.format_exception(failure.exception))
        self.assertNotIn(canary, str(failure.exception))
        self.assertNotIn(canary, formatted)
        self.assertFalse(self.target.exists())
        self.assert_no_preparation()

    def test_data_sync_failure_never_publishes_or_leaves_owned_preparation(self):
        before = self.source.read_bytes()
        with (
            patch.object(os, "fsync", side_effect=OSError("PRIVATE-FSYNC-CANARY")),
            self.assertRaises(recovery.SQLiteRecoveryError) as failure,
        ):
            self.backup()
        self.assertEqual(failure.exception.code, "io-failed")
        self.assertNotIn("PRIVATE-FSYNC-CANARY", str(failure.exception))
        self.assertFalse(self.target.exists())
        self.assertEqual(self.source.read_bytes(), before)
        self.assert_no_preparation()
        # Handles were released after failure: both directory and source can be renamed.
        replacement = self.source_root / "source-renamed.sqlite"
        self.source.rename(replacement)
        replacement.rename(self.source)
        renamed = self.base / "target-renamed"
        self.target_root.rename(renamed)
        renamed.rename(self.target_root)

    def test_unknown_entry_in_owned_stage_is_preserved_and_cleanup_is_explicit(self):
        original = recovery._publish_new_file
        retained = []

        def add_caller_entry(prepared, *args):
            marker = prepared.parent / "caller-owned-marker"
            marker.write_bytes(b"CALLER-STAGING-CONTENT")
            retained.append(marker)
            original(prepared, *args)

        with patch.object(recovery, "_publish_new_file", add_caller_entry):
            result = self.backup()
        self.assertFalse(result.cleanup_complete)
        self.assertEqual(rows(self.target), rows(self.source))
        self.assertEqual(retained[0].read_bytes(), b"CALLER-STAGING-CONTENT")
        self.assertEqual(list(retained[0].parent.iterdir()), retained)
        self.assertEqual(self.caller.read_bytes(), b"CALLER-FILE-UNCHANGED")

    @unittest.skipUnless(os.name == "posix", "POSIX directory fsync")
    def test_directory_sync_failure_after_publication_is_unknown_and_never_overwritten(
        self,
    ):
        fsync = os.fsync

        def fail_directory(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise OSError("PRIVATE-DIRECTORY-CANARY")
            fsync(descriptor)

        with (
            patch.object(os, "fsync", fail_directory),
            self.assertRaises(recovery.SQLiteRecoveryError) as failure,
        ):
            self.backup()
        self.assertEqual(failure.exception.code, "publication-unknown")
        self.assertEqual(rows(self.target), rows(self.source))
        before = self.target.read_bytes()
        with self.assertRaises(recovery.SQLiteRecoveryError) as retried:
            self.backup()
        self.assertEqual(retried.exception.code, "destination-exists")
        self.assertEqual(self.target.read_bytes(), before)
        self.assert_no_preparation()

    @unittest.skipUnless(os.name == "nt", "Windows path aliases and native directory pinning")
    def test_windows_device_ads_names_and_parent_rename_are_refused(self):
        for index, name in enumerate(["NUL.sqlite", "COM1", "copy.sqlite:stream", "trailing.sqlite."]):
            with (
                self.subTest(case=index),
                self.assertRaises(recovery.SQLiteRecoveryError) as failure,
            ):
                self.backup(self.target_root / name)
            self.assertEqual(failure.exception.code, "invalid-path")
        original = recovery._publish_new_file
        observed = []

        def verify_pinning(*args):
            with self.assertRaises(PermissionError):
                self.target_root.rename(self.base / "moved-root")
            with self.assertRaises(PermissionError):
                self.source.rename(self.source_root / "moved-source.sqlite")
            observed.append("pinned")
            original(*args)

        with patch.object(recovery, "_publish_new_file", verify_pinning):
            self.backup()
        self.assertEqual(observed, ["pinned"])
        self.assertTrue(self.target.exists())
        self.assertFalse((self.base / "moved-root").exists())
        self.assert_no_preparation()

    def test_symbolic_source_and_destination_ancestor_are_never_followed(self):
        outside = self.base / "outside"
        outside.mkdir(mode=0o700)
        marker = outside / "preserve.txt"
        marker.write_bytes(b"OUTSIDE-UNCHANGED")
        linked_source = self.source_root / "linked.sqlite"
        linked_directory = self.target_root / "linked-directory"
        try:
            linked_source.symlink_to(self.source)
            linked_directory.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            if linked_source.is_symlink():
                linked_source.unlink()
            if linked_directory.is_symlink():
                linked_directory.unlink()
            self.skipTest("OS did not permit creating file/directory symlinks: " + type(error).__name__)
        try:
            for index, source, destination in [
                (0, linked_source, self.target),
                (1, self.source, linked_directory / "escape.sqlite"),
            ]:
                with (
                    self.subTest(case=index),
                    self.assertRaises(recovery.SQLiteRecoveryError) as failure,
                ):
                    recovery.backup_sqlite(
                        source,
                        destination,
                        source_root=self.source_root,
                        destination_root=self.target_root,
                    )
                self.assertEqual(failure.exception.code, "unsafe-path")
            self.assertEqual(marker.read_bytes(), b"OUTSIDE-UNCHANGED")
            self.assertFalse((outside / "escape.sqlite").exists())
        finally:
            linked_source.unlink()
            linked_directory.unlink()
        self.assert_no_preparation()

    @integration
    @unittest.skipUnless(os.name == "nt", "Windows junctions")
    def test_junction_root_or_nested_directory_is_refused_and_outside_data_survives(
        self,
    ):
        outside = self.base / "outside"
        outside.mkdir()
        marker = outside / "preserve.txt"
        marker.write_bytes(b"OUTSIDE-UNCHANGED")
        junction = self.target_root / "junction"
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(created.returncode, 0)
        try:
            with self.assertRaises(recovery.SQLiteRecoveryError) as failure:
                self.backup(junction / "escape.sqlite")
            self.assertEqual(failure.exception.code, "unsafe-path")
            with self.assertRaises(recovery.SQLiteRecoveryError) as failure:
                recovery.backup_sqlite(
                    self.source,
                    "escape.sqlite",
                    source_root=self.source_root,
                    destination_root=junction,
                )
            self.assertEqual(failure.exception.code, "unsafe-path")
        finally:
            self.assertTrue(junction.absolute().is_relative_to(self.base))
            junction.rmdir()  # Remove only the reparse-point entry, not its target.
        self.assertEqual(marker.read_bytes(), b"OUTSIDE-UNCHANGED")
        self.assertFalse((outside / "escape.sqlite").exists())
        self.assert_no_preparation()


class RecoveryCliTests(_RecoveryFixture):
    def invoke(self, arguments):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            status = main(arguments)
        return status, output.getvalue(), error.getvalue()

    def arguments(self, verb='backup-sqlite', **changes):
        values = {
            'source': str(self.source),
            'target': str(self.target),
            'source_root': str(self.source_root),
            'target_root': str(self.target_root),
        }
        values.update(changes)
        return [
            verb,
            values['source'],
            values['target'],
            '--source-root',
            values['source_root'],
            '--target-root',
            values['target_root'],
            '--json',
        ]

    def test_main_help_lists_both_commands_and_recovery_help_is_specific(self):
        for arguments in [['--help'], ['backup-sqlite', '--help'], ['restore-sqlite-new', '--help']]:
            output = io.StringIO()
            with redirect_stdout(output), self.assertRaises(SystemExit) as exit_status:
                main(arguments)
            self.assertEqual(exit_status.exception.code, 0)
            text = output.getvalue()
            if arguments == ['--help']:
                self.assertIn('backup-sqlite', text)
                self.assertIn('restore-sqlite-new', text)
            else:
                self.assertIn('--source-root', text)
                self.assertIn('--target-root', text)
                self.assertIn('--deadline-seconds', text)

    def test_parse_failures_never_echo_unknown_options_values_or_paths(self):
        canary = 'PRIVATE-RECOVERY-ARGUMENT'
        for verb in ['backup-sqlite', 'restore-sqlite-new']:
            for arguments in [
                [verb, '--unknown-' + canary],
                [*self.arguments(verb), '--deadline-seconds', canary],
                [verb, canary],
            ]:
                with self.subTest(verb=verb, arguments_count=len(arguments)):
                    status, output, error = self.invoke(arguments)
                    self.assertEqual(status, 2)
                    self.assertEqual(output, '')
                    self.assertEqual(
                        json.loads(error), {'passed': False, 'code': 'invalid-arguments', 'phase': 'arguments'}
                    )
                    self.assertNotIn(canary, output + error)
        self.assertFalse(self.target.exists())
        self.assert_no_preparation()

    def test_runtime_error_and_existing_destination_are_fixed_without_overwrite(self):
        private_source = self.source_root / 'PRIVATE-MISSING-DATABASE.sqlite'
        status, output, error = self.invoke(self.arguments(source=str(private_source)))
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(error)['code'], 'source-missing')
        self.assertNotIn('PRIVATE-MISSING-DATABASE', output + error)
        self.target.write_bytes(b'CALLER-DESTINATION')
        status, output, error = self.invoke(self.arguments())
        self.assertEqual(status, 2)
        self.assertEqual(output, '')
        self.assertEqual(json.loads(error)['code'], 'destination-exists')
        self.assertEqual(self.target.read_bytes(), b'CALLER-DESTINATION')
        self.assert_no_preparation()

    def test_cli_unknown_publication_is_separate_from_safe_to_retry_read_failure(self):
        for code, expected in [('publication-unknown', 4), ('deadline-exceeded', 3)]:
            with (
                self.subTest(code=code),
                patch(
                    'telegram_patterns._sqlite_recovery_cli.backup_sqlite',
                    side_effect=SQLiteRecoveryError(code, 'publish'),
                ),
            ):
                status, output, error = self.invoke(self.arguments())
            self.assertEqual(status, expected)
            self.assertEqual(output, '')
            self.assertEqual(json.loads(error)['code'], code)
        self.assertFalse(self.target.exists())


@integration
class RecoveryProcessTests(_RecoveryFixture):
    """Run separately with explicit real child processes and the same owned temporary sandbox."""

    def test_live_wal_commits_during_backup_remain_consistent_and_source_main_file_is_unchanged(
        self,
    ):
        self.source.unlink()
        create_database(self.source, large=True)
        context = multiprocessing.get_context("spawn")
        commands, responses = context.Queue(), context.Queue()
        child = context.Process(target=writer_worker, args=(str(self.source), commands, responses))
        child.start()
        try:
            self.assertEqual(responses.get(timeout=10), "wal-ready")
            commands.put(("commit", 10))
            self.assertEqual(responses.get(timeout=10), ("committed", 10))
            before = self.source.read_bytes()
            connect = sqlite3.connect
            observed = []

            class SourceConnection(sqlite3.Connection):
                def backup(self, target, *, pages=-1, progress=None, name="main", sleep=0.25):
                    def step(status, remaining, total):
                        if not observed and remaining > 0:
                            commands.put(("commit", 11))
                            self_response = responses.get(timeout=10)
                            observed.append(self_response)
                        if progress is not None:
                            progress(status, remaining, total)

                    return super().backup(target, pages=pages, progress=step, name=name, sleep=sleep)

            def source_connect(*args, **kwargs):
                if "?mode=ro" in str(args[0]):
                    kwargs["factory"] = SourceConnection
                return connect(*args, **kwargs)

            with patch.object(sqlite3, "connect", source_connect):
                self.backup()
            self.assertEqual(observed, [("committed", 11)])
            self.assertEqual(self.source.read_bytes(), before)
            copied = rows(self.target)
            self.assertIn(("wal-intent-10", "unknown", "native:wal-committed"), copied)
            with closing(sqlite3.connect(self.target)) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(
                    db.execute("SELECT count(*) FROM parent WHERE id=11").fetchone()[0],
                    db.execute("SELECT count(*) FROM child WHERE id=11").fetchone()[0],
                )
        finally:
            commands.put("stop")
            child.join(10)
            if child.is_alive():
                child.terminate()
                child.join(5)
        self.assertEqual(child.exitcode, 0)
        self.assert_no_preparation()

    def test_exclusive_source_writer_is_bounded_without_partial_publication(self):
        context = multiprocessing.get_context("spawn")
        commands, responses = context.Queue(), context.Queue()
        child = context.Process(
            target=writer_worker,
            args=(str(self.source), commands, responses),
            kwargs={"exclusive": True},
        )
        child.start()
        try:
            self.assertEqual(responses.get(timeout=10), "exclusive-ready")
            started = time.monotonic()
            with self.assertRaises(recovery.SQLiteRecoveryError) as failure:
                self.backup(deadline_seconds=0.2)
            self.assertIn(failure.exception.code, ("database-busy", "deadline-exceeded"))
            self.assertLess(time.monotonic() - started, 2)
            self.assertFalse(self.target.exists())
            self.assert_no_preparation()
        finally:
            commands.put("stop")
            child.join(10)
            if child.is_alive():
                child.terminate()
                child.join(5)
        self.assertEqual(child.exitcode, 0)

    def test_two_prepared_processes_publish_exactly_one_complete_new_file(self):
        context = multiprocessing.get_context("spawn")
        gate, results = context.Barrier(2), context.Queue()
        children = [
            context.Process(
                target=copy_worker,
                args=(
                    str(self.source),
                    str(self.target),
                    str(self.source_root),
                    str(self.target_root),
                    results,
                    gate,
                ),
            )
            for _ in range(2)
        ]
        for child in children:
            child.start()
        for child in children:
            child.join(20)
            if child.is_alive():
                child.terminate()
                child.join(5)
            self.assertEqual(child.exitcode, 0)
        outcomes = [results.get(timeout=5) for _ in children]
        self.assertEqual(sorted(row[0] for row in outcomes), ["destination-exists", "passed"])
        self.assertEqual(rows(self.target), rows(self.source))
        winner = next(row for row in outcomes if row[0] == "passed")
        self.assertEqual(winner[1], hashlib.sha256(self.target.read_bytes()).hexdigest())
        self.assertTrue(winner[2])
        self.assert_no_preparation()

    def test_real_crash_before_publish_has_no_destination_and_keeps_private_preparation(
        self,
    ):
        child = multiprocessing.get_context("spawn").Process(
            target=copy_worker,
            args=(
                str(self.source),
                str(self.target),
                str(self.source_root),
                str(self.target_root),
                None,
            ),
            kwargs={"crash": "before"},
        )
        child.start()
        child.join(20)
        if child.is_alive():
            child.terminate()
            child.join(5)
        self.assertEqual(child.exitcode, 41)
        self.assertFalse(self.target.exists())
        prepared = list(self.target_root.glob(".sqlite-recovery-*/snapshot.sqlite"))
        self.assertEqual(len(prepared), 1)
        self.assertEqual(rows(prepared[0]), rows(self.source))
        self.assertEqual(self.caller.read_bytes(), b"CALLER-FILE-UNCHANGED")

    def test_real_crash_after_publish_keeps_complete_file_and_retry_refuses_overwrite(
        self,
    ):
        child = multiprocessing.get_context("spawn").Process(
            target=copy_worker,
            args=(
                str(self.source),
                str(self.target),
                str(self.source_root),
                str(self.target_root),
                None,
            ),
            kwargs={"crash": "after"},
        )
        child.start()
        child.join(20)
        if child.is_alive():
            child.terminate()
            child.join(5)
        self.assertEqual(child.exitcode, 42)
        self.assertEqual(rows(self.target), rows(self.source))
        before = self.target.read_bytes()
        with self.assertRaises(recovery.SQLiteRecoveryError) as failure:
            self.backup()
        self.assertEqual(failure.exception.code, "destination-exists")
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(self.caller.read_bytes(), b"CALLER-FILE-UNCHANGED")

    def test_cli_backup_restore_new_json_and_argument_redaction(self):
        cli = [sys.executable, "-I", "-m", "telegram_patterns"]
        backup = subprocess.run(
            [
                *cli,
                "backup-sqlite",
                str(self.source),
                str(self.target),
                "--source-root",
                str(self.source_root),
                "--target-root",
                str(self.target_root),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(backup.returncode, 0, backup.stdout + backup.stderr)
        report = json.loads(backup.stdout)
        self.assertTrue(report["passed"] and report["published"] and report["cleanup_complete"])
        self.assertEqual(report["sha256"], hashlib.sha256(self.target.read_bytes()).hexdigest())
        restored = self.target_root / "restored.sqlite"
        restore = subprocess.run(
            [
                *cli,
                "restore-sqlite-new",
                str(self.target),
                str(restored),
                "--source-root",
                str(self.target_root),
                "--target-root",
                str(self.target_root),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(restore.returncode, 0, restore.stdout + restore.stderr)
        self.assertEqual(rows(restored), rows(self.source))
        canary = "SECRET-DO-NOT-ECHO"
        invalid = subprocess.run(
            [*cli, "backup-sqlite", "--unknown-" + canary],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(json.loads(invalid.stderr)["code"], "invalid-arguments")
        self.assertNotIn(canary, invalid.stdout + invalid.stderr)
        self.assert_no_preparation()


if __name__ == "__main__":
    unittest.main()
