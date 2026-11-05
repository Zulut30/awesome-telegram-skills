"""Fixed diagnostics for explicit SQLite recovery commands; no service switch or SDK."""

from __future__ import annotations

import argparse
import json
import sys
from typing import NoReturn

from .sqlite_recovery import SQLiteRecoveryError, backup_sqlite, restore_sqlite_new

RECOVERY_COMMANDS = frozenset({'backup-sqlite', 'restore-sqlite-new'})


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # Ordinary argparse errors echo arbitrary argument values or filesystem paths.
        raise SQLiteRecoveryError('invalid-arguments', 'arguments')


def register_help(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    commands.add_parser('backup-sqlite', help='Create a checked NEW SQLite snapshot; never overwrite')
    commands.add_parser('restore-sqlite-new', help='Restore SQLite to an absent file; never switch a service')


def main(argv: list[str]) -> int:
    try:
        parser = _Parser(prog='telegram-patterns', description='SQLite snapshots and restore only to a NEW file.')
        commands = parser.add_subparsers(dest='action', required=True)
        for name in sorted(RECOVERY_COMMANDS):
            command = commands.add_parser(name)
            command.add_argument('source')
            command.add_argument('new_target')
            command.add_argument('--source-root', required=True, help='Existing service-owner protected source root')
            command.add_argument('--target-root', required=True, help='Existing service-owner protected target root')
            command.add_argument('--deadline-seconds', type=float, default=30)
            command.add_argument('--json', action='store_true', help='Results are always JSON; errors use stderr')
        args = parser.parse_args(argv)
        action = backup_sqlite if args.action == 'backup-sqlite' else restore_sqlite_new
        result = action(
            args.source,
            args.new_target,
            source_root=args.source_root,
            destination_root=args.target_root,
            deadline_seconds=args.deadline_seconds,
        )
        print(
            json.dumps(
                {
                    'passed': True,
                    'operation': result.operation,
                    'sha256': result.sha256,
                    'bytes': result.bytes,
                    'pages': result.pages,
                    'published': True,
                    'directory_synced': result.directory_synced,
                    'cleanup_complete': result.cleanup_complete,
                }
            )
        )
        return 0
    except SQLiteRecoveryError as error:
        print(json.dumps({'passed': False, 'code': error.code, 'phase': error.phase}), file=sys.stderr)
        if error.code in {'database-busy', 'deadline-exceeded'}:
            return 3
        return 4 if error.code == 'publication-unknown' else 2
    except KeyboardInterrupt:
        print(json.dumps({'passed': False, 'code': 'interrupted', 'phase': 'operation'}), file=sys.stderr)
        return 130
    except Exception:  # noqa: BLE001 -- redact unexpected filesystem details at the command boundary
        print(json.dumps({'passed': False, 'code': 'io-failed', 'phase': 'operation'}), file=sys.stderr)
        return 2
