"""SDK-free SQLite snapshots and restore-to-new-file; never switch a running service."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import sqlite3
import stat
import time
import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Operation = Literal["backup", "restore-new"]
RecoveryCode = Literal[
    "invalid-arguments",
    "invalid-path",
    "unsafe-path",
    "source-target-conflict",
    "destination-exists",
    "source-missing",
    "invalid-database",
    "foreign-key-invalid",
    "database-busy",
    "deadline-exceeded",
    "permission-denied",
    "unsupported-filesystem",
    "io-failed",
    "publication-unknown",
]


class SQLiteRecoveryError(Exception):
    """Only fixed codes/phases are diagnostic. Never include SQLite error text or supplied paths."""

    def __init__(self, code: RecoveryCode, phase: str) -> None:
        self.code = code
        self.phase = phase
        super().__init__(f"SQLite recovery refused: {code} ({phase})")


@dataclass(frozen=True, slots=True)
class SQLiteRecoveryResult:
    operation: Operation
    destination: Path = field(repr=False)
    sha256: str
    bytes: int
    pages: int
    directory_synced: bool
    cleanup_complete: bool


@dataclass(frozen=True, slots=True)
class _Directory:
    path: Path
    descriptor: int | None
    identity: tuple[int, int]


def _identity(info: os.stat_result) -> tuple[int, int]:
    if info.st_ino == 0:
        raise SQLiteRecoveryError("unsupported-filesystem", "pin-path")
    return info.st_dev, info.st_ino


def _unsafe(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _effective_uid() -> int:
    getter = getattr(os, "geteuid", None)
    if not callable(getter):
        raise SQLiteRecoveryError("unsupported-filesystem", "pin-path")
    value = getter()
    if type(value) is not int:
        raise SQLiteRecoveryError("unsupported-filesystem", "pin-path")
    return value


def _parts_safe(path: Path) -> None:
    if ".." in path.parts or any(ord(char) < 32 for char in str(path)):
        raise SQLiteRecoveryError("invalid-path", "paths")
    if os.name == "nt":
        if str(path).startswith(("\\\\", "//")):
            raise SQLiteRecoveryError("invalid-path", "paths")
        devices = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
        devices |= {prefix + number for prefix in ("COM", "LPT") for number in "123456789¹²³"}
        for part in path.parts[1:] if path.anchor else path.parts:
            if ":" in part or part.endswith((" ", ".")) or part.split(".")[0].upper() in devices:
                raise SQLiteRecoveryError("invalid-path", "paths")


def _absolute(path: str | Path) -> Path:
    if not isinstance(path, (str, Path)):
        raise SQLiteRecoveryError("invalid-path", "paths")
    candidate = Path(path)
    _parts_safe(candidate)
    return candidate.absolute()


def _within(path: str | Path, root: Path) -> Path:
    if not isinstance(path, (str, Path)):
        raise SQLiteRecoveryError("invalid-path", "paths")
    raw = Path(path)
    _parts_safe(raw)
    candidate = _absolute(raw if raw.is_absolute() else root / raw)
    if not candidate.is_relative_to(root) or candidate == root:
        raise SQLiteRecoveryError("invalid-path", "paths")
    return candidate


@contextmanager
def _hold_windows(path: Path, *, directory: bool) -> Iterator[None]:
    """A native non-delete-sharing handle pins each checked component until the operation ends."""
    from ctypes import wintypes

    class _FileInfo(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("creation", wintypes.FILETIME),
            ("access", wintypes.FILETIME),
            ("write", wintypes.FILETIME),
            ("volume", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("index_high", wintypes.DWORD),
            ("index_low", wintypes.DWORD),
        ]

    load_library = getattr(ctypes, "WinDLL", None)
    if not callable(load_library):
        raise SQLiteRecoveryError("unsupported-filesystem", "pin-path")
    kernel = load_library("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_FileInfo),
    ]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(
        str(path),
        0x80 if directory else 0x80000000,
        1 if directory else 3,
        None,
        3,
        0x00200000 | (0x02000000 if directory else 0),
        None,
    )
    if handle is None or handle == ctypes.c_void_p(-1).value:
        raise SQLiteRecoveryError("permission-denied", "pin-path")
    try:
        info = _FileInfo()
        if not kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise SQLiteRecoveryError("io-failed", "pin-path")
        if int(info.attributes) & 0x400:
            raise SQLiteRecoveryError("unsafe-path", "pin-path")
        if bool(int(info.attributes) & 0x10) != directory:
            raise SQLiteRecoveryError("invalid-path", "pin-path")
        yield
    finally:
        kernel.CloseHandle(handle)


def _pin_directory(path: Path, stack: ExitStack, *, protected_root: Path) -> _Directory:
    info = path.lstat()
    if _unsafe(info) or not stat.S_ISDIR(info.st_mode):
        raise SQLiteRecoveryError("unsafe-path", "pin-path")
    descriptor: int | None = None
    if os.name == "nt":
        stack.enter_context(_hold_windows(path, directory=True))
    elif os.name == "posix" and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"):
        # Roots/subdirectories must be service-owner protected; another UID cannot replace path components.
        if path.is_relative_to(protected_root) and (info.st_uid != _effective_uid() or info.st_mode & 0o022):
            raise SQLiteRecoveryError("unsafe-path", "pin-path")
        descriptor = os.open(
            path,
            os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
        )
        stack.callback(os.close, descriptor)
        if _identity(os.fstat(descriptor)) != _identity(info):
            raise SQLiteRecoveryError("unsafe-path", "pin-path")
    else:
        raise SQLiteRecoveryError("unsupported-filesystem", "pin-path")
    current = path.lstat()
    if _identity(current) != _identity(info) or _unsafe(current):
        raise SQLiteRecoveryError("unsafe-path", "pin-path")
    return _Directory(path, descriptor, _identity(info))


def _pin_chain(path: Path, root: Path, stack: ExitStack, cache: dict[Path, _Directory]) -> _Directory:
    chain = list(reversed(path.parents)) + [path]
    for part in chain:
        if part not in cache:
            cache[part] = _pin_directory(part, stack, protected_root=root)
        elif os.name == "posix" and part.is_relative_to(root):
            info = part.lstat()
            if info.st_uid != _effective_uid() or info.st_mode & 0o022:
                raise SQLiteRecoveryError("unsafe-path", "pin-path")
    return cache[path]


def _verify_directory(directory: _Directory) -> None:
    current = directory.path.lstat()
    if _unsafe(current) or _identity(current) != directory.identity:
        raise SQLiteRecoveryError("unsafe-path", "verify-path")


def _deadline(seconds: float) -> float:
    if type(seconds) not in (int, float) or not 0 < seconds <= 300:
        raise SQLiteRecoveryError("invalid-arguments", "arguments")
    return time.monotonic() + seconds


def _check(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise SQLiteRecoveryError("deadline-exceeded", "snapshot")


def _check_source(source: Path, source_fd: int) -> None:
    info = source.lstat()
    if _unsafe(info) or not stat.S_ISREG(info.st_mode) or _identity(info) != _identity(os.fstat(source_fd)):
        raise SQLiteRecoveryError("unsafe-path", "verify-source")


def _snapshot(source: Path, prepared: Path, deadline: float) -> int:
    source_db: sqlite3.Connection | None = None
    copied_db: sqlite3.Connection | None = None
    try:
        source_db = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=0, isolation_level=None)
        source_db.execute("PRAGMA query_only=ON")
        source_db.execute("PRAGMA trusted_schema=OFF")
        copied_db = sqlite3.connect(prepared.as_uri() + "?mode=rw", uri=True, timeout=0, isolation_level=None)
        copied_db.execute("PRAGMA trusted_schema=OFF")
        copied_db.execute("PRAGMA synchronous=FULL")
        copied_db.execute("PRAGMA journal_mode=DELETE")

        def progress(_status: int, _remaining: int, _total: int) -> None:
            _check(deadline)

        source_db.backup(copied_db, pages=64, progress=progress, sleep=0.01)
        _check(deadline)
        # Standalone snapshots must not need a prepared sidecar to be opened later.
        if copied_db.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
            raise SQLiteRecoveryError("invalid-database", "verify-copy")
        expired = False

        def query_progress() -> int:
            nonlocal expired
            expired = time.monotonic() >= deadline
            return int(expired)

        copied_db.set_progress_handler(query_progress, 1000)
        try:
            if copied_db.execute("PRAGMA integrity_check(1)").fetchall() != [("ok",)]:
                raise SQLiteRecoveryError("invalid-database", "integrity-check")
            if copied_db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise SQLiteRecoveryError("foreign-key-invalid", "foreign-key-check")
            pages = copied_db.execute("PRAGMA page_count").fetchone()
            if pages is None or type(pages[0]) is not int or pages[0] <= 0:
                raise SQLiteRecoveryError("invalid-database", "verify-copy")
            _check(deadline)
            return int(pages[0])
        except sqlite3.Error:
            if expired:
                raise SQLiteRecoveryError("deadline-exceeded", "integrity-check") from None
            raise
        finally:
            copied_db.set_progress_handler(None, 0)
    finally:
        if copied_db is not None:
            copied_db.close()
        if source_db is not None:
            source_db.close()


def _publish_new_file(prepared: Path, destination: Path, stage: _Directory, parent: _Directory) -> None:
    """Atomic exclusive namespace operation: never replace or write into the destination file."""
    if os.name == "posix":
        os.link(
            prepared.name,
            destination.name,
            src_dir_fd=stage.descriptor,
            dst_dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
    else:
        os.link(prepared, destination)


def _cleanup_stage(stage: Path, identity: tuple[int, int], prepared_identity: tuple[int, int] | None) -> bool:
    try:
        if _identity(stage.lstat()) != identity or _unsafe(stage.lstat()):
            return False
        for name in (
            "snapshot.sqlite",
            "snapshot.sqlite-journal",
            "snapshot.sqlite-wal",
            "snapshot.sqlite-shm",
        ):
            file = stage / name
            try:
                info = file.lstat()
            except FileNotFoundError:
                continue
            if _unsafe(info) or not stat.S_ISREG(info.st_mode):
                return False
            if name == "snapshot.sqlite" and _identity(info) != prepared_identity:
                return False
            file.unlink()
        stage.rmdir()  # Unknown caller-created entries are retained rather than removed recursively.
        return True
    except OSError:
        return False


def _copy_new(
    operation: Operation,
    source: str | Path,
    destination: str | Path,
    *,
    source_root: str | Path,
    destination_root: str | Path,
    deadline_seconds: float,
) -> SQLiteRecoveryResult:
    deadline = _deadline(deadline_seconds)
    phase = "paths"
    published = False
    stage_path: Path | None = None
    stage_identity: tuple[int, int] | None = None
    prepared_identity: tuple[int, int] | None = None
    try:
        source_boundary, destination_boundary = (
            _absolute(source_root),
            _absolute(destination_root),
        )
        source_path, destination_path = (
            _within(source, source_boundary),
            _within(destination, destination_boundary),
        )
        if source_path == destination_path:
            raise SQLiteRecoveryError("source-target-conflict", phase)
        with ExitStack() as pins:
            cache: dict[Path, _Directory] = {}
            _pin_chain(source_boundary, source_boundary, pins, cache)
            _pin_chain(destination_boundary, destination_boundary, pins, cache)
            source_parent = _pin_chain(source_path.parent, source_boundary, pins, cache)
            destination_parent = _pin_chain(destination_path.parent, destination_boundary, pins, cache)
            try:
                source_info = source_path.lstat()
            except FileNotFoundError:
                raise SQLiteRecoveryError("source-missing", phase) from None
            if _unsafe(source_info) or not stat.S_ISREG(source_info.st_mode):
                raise SQLiteRecoveryError("unsafe-path", phase)
            try:
                destination_info = destination_path.lstat()
            except FileNotFoundError:
                pass
            else:
                if _identity(destination_info) == _identity(source_info):
                    raise SQLiteRecoveryError("source-target-conflict", phase)
                raise SQLiteRecoveryError("destination-exists", phase)
            if os.name == "nt":
                pins.enter_context(_hold_windows(source_path, directory=False))
            source_fd = os.open(
                source_path,
                os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            pins.callback(os.close, source_fd)
            _check_source(source_path, source_fd)
            if os.read(source_fd, 16) != b"SQLite format 3\x00":
                raise SQLiteRecoveryError("invalid-database", "source-header")
            _check(deadline)
            phase = "prepare"
            stage_path = destination_parent.path / (".sqlite-recovery-" + uuid.uuid4().hex)
            stage_path.mkdir(mode=0o700)
            stage_identity = _identity(stage_path.lstat())
            cleanup = False
            try:
                with ExitStack() as preparation_pins:
                    stage = _pin_directory(
                        stage_path,
                        preparation_pins,
                        protected_root=destination_boundary,
                    )
                    prepared = stage_path / "snapshot.sqlite"
                    descriptor = os.open(
                        prepared,
                        os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                    )
                    try:
                        prepared_identity = _identity(os.fstat(descriptor))
                        phase = "snapshot"
                        pages = _snapshot(source_path, prepared, deadline)
                        _check_source(source_path, source_fd)
                        if _identity(prepared.lstat()) != prepared_identity or _unsafe(prepared.lstat()):
                            raise SQLiteRecoveryError("unsafe-path", "verify-copy")
                        os.fsync(descriptor)
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        digest = hashlib.sha256()
                        while chunk := os.read(descriptor, 65536):
                            _check(deadline)
                            digest.update(chunk)
                        size = os.fstat(descriptor).st_size
                        _verify_directory(source_parent)
                        _verify_directory(destination_parent)
                        _verify_directory(stage)
                        _check(deadline)
                        phase = "publish"
                        _publish_new_file(prepared, destination_path, stage, destination_parent)
                        published = True
                        directory_synced = False
                        if destination_parent.descriptor is not None:
                            phase = "sync-directory"
                            os.fsync(destination_parent.descriptor)
                            directory_synced = True
                    finally:
                        os.close(descriptor)
            finally:
                cleanup = _cleanup_stage(stage_path, stage_identity, prepared_identity)
            return SQLiteRecoveryResult(
                operation,
                destination_path,
                digest.hexdigest(),
                size,
                pages,
                directory_synced,
                cleanup,
            )
    except SQLiteRecoveryError:
        raise
    except FileExistsError:
        raise SQLiteRecoveryError("destination-exists", phase) from None
    except PermissionError:
        raise SQLiteRecoveryError("publication-unknown" if published else "permission-denied", phase) from None
    except sqlite3.Error as error:
        code = getattr(error, "sqlite_errorcode", 0) & 0xFF
        raise SQLiteRecoveryError(
            "database-busy" if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) else "invalid-database",
            phase,
        ) from None
    except (OSError, ValueError, UnicodeError, NotImplementedError) as error:
        unsupported = isinstance(error, NotImplementedError) or getattr(error, "errno", None) in (
            errno.EXDEV,
            errno.ENOTSUP,
            errno.EOPNOTSUPP,
        )
        raise SQLiteRecoveryError(
            "publication-unknown" if published else "unsupported-filesystem" if unsupported else "io-failed",
            phase,
        ) from None


def backup_sqlite(
    source: str | Path,
    destination: str | Path,
    *,
    source_root: str | Path,
    destination_root: str | Path,
    deadline_seconds: float = 30,
) -> SQLiteRecoveryResult:
    """Online snapshot into a complete, checked new file. Roots already exist and are service-owner protected."""
    return _copy_new(
        "backup",
        source,
        destination,
        source_root=source_root,
        destination_root=destination_root,
        deadline_seconds=deadline_seconds,
    )


def restore_sqlite_new(
    source: str | Path,
    destination: str | Path,
    *,
    source_root: str | Path,
    destination_root: str | Path,
    deadline_seconds: float = 30,
) -> SQLiteRecoveryResult:
    """Restore only to an absent path; leave the running DB, services, queues and financial intents untouched."""
    return _copy_new(
        "restore-new",
        source,
        destination,
        source_root=source_root,
        destination_root=destination_root,
        deadline_seconds=deadline_seconds,
    )
