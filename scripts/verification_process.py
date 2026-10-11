"""Bounded subprocesses for local verification, including owned descendant cleanup."""
from __future__ import annotations

import os
import signal
import shutil
import subprocess
from pathlib import Path
from typing import Mapping, Sequence


def save_consumer_diagnostics(consumers: Path, destination: Path) -> None:
    """Preserve nested failure logs/screenshots, without copying installed environments."""
    for directory, names, files in os.walk(consumers, followlinks=False):
        parent = Path(directory)
        names[:] = sorted(name for name in names
                          if name not in {'core', 'sdk', 'selected-sdk', '.venv', 'node_modules', '.mypy_cache', '__pycache__'}
                          and not (parent / name).is_symlink()
                          and not bool(getattr(parent / name, 'is_junction', lambda: False)()))
        for name in files:
            source = parent / name
            if source.is_symlink() or not (source.suffix in {'.log', '.png'}
                                          or name in {'report.json', 'stage-report.json'}):
                continue
            target = destination / source.relative_to(consumers)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def stop_process_tree(process: subprocess.Popen) -> None:
    """Stop only the tree/session created by run_command, never other test runs."""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       capture_output=True, timeout=20, check=False)
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_command(command: Sequence[str | Path], *, cwd: Path, env: Mapping[str, str],
                timeout: float) -> subprocess.CompletedProcess[str]:
    """Capture both streams; retain partial output after timeout or interruption."""
    process = subprocess.Popen(list(map(str, command)), cwd=cwd, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='replace',
                               start_new_session=os.name != 'nt')
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        stop_process_tree(process)
        stdout, stderr = process.communicate(timeout=20)
        raise subprocess.TimeoutExpired(command, error.timeout, output=stdout, stderr=stderr) from None
    except BaseException:
        stop_process_tree(process)
        process.communicate(timeout=20)
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
