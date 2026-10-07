"""Copy selected standalone skills into the skill directory an agent reads in an existing project."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import stat
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1] / ".agents" / "skills"
NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
# Project skill directory per agent. Claude Code reads .claude/skills and never .agents/skills.
AGENT_DIRECTORIES = {
    "codex": (".agents", "skills"),
    "claude": (".claude", "skills"),
}


class InstallError(ValueError):
    """Invalid selection or unsafe destination; no overwrite is attempted."""


def is_link(path: Path) -> bool:
    """Include Windows junctions and other reparse points, even when dangling."""
    if path.is_symlink():
        return True
    try:
        attrs = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def check_source_tree(path: Path) -> None:
    if is_link(path):
        raise InstallError(f"Source links are unsupported: {path}")
    for directory, subdirs, files in os.walk(path, followlinks=False):
        for entry in subdirs + files:
            candidate = Path(directory) / entry
            if is_link(candidate):
                raise InstallError(f"Source links are unsupported: {candidate}")


def install_skills(
    source_root: Path,
    project: Path,
    names: list[str] | None = None,
    *,
    dry_run: bool = False,
    agent: str = "codex",
) -> list[Path]:
    if agent not in AGENT_DIRECTORIES:
        raise InstallError(f"Unknown agent: {agent}; choose one of {', '.join(AGENT_DIRECTORIES)}")
    if not source_root.is_dir():
        raise InstallError(f"Skill source directory does not exist: {source_root}")
    if is_link(source_root):
        raise InstallError(f"Source links are unsupported: {source_root}")
    if not project.is_dir():
        raise InstallError(f"Target project must already exist: {project}")
    project = project.resolve(strict=True)

    available = {
        path.name: path
        for path in source_root.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    selected = list(dict.fromkeys(names)) if names else sorted(available)
    if not selected:
        raise InstallError("No skills found or selected")
    for name in selected:
        if len(name) > 64 or not NAME_PATTERN.fullmatch(name) or name not in available:
            raise InstallError(f"Unknown or invalid skill name: {name}")
        check_source_tree(available[name])

    base, leaf = AGENT_DIRECTORIES[agent]
    destination_root = project / base / leaf
    for parent in (project / base, destination_root):
        if is_link(parent):
            raise InstallError(f"Destination links are unsupported: {parent}")
        if parent.exists() and not parent.is_dir():
            raise InstallError(f"Destination parent is not a directory: {parent}")
    if not destination_root.resolve().is_relative_to(project):
        raise InstallError("Destination escapes the target project")

    destinations = [destination_root / name for name in selected]
    conflicts = [path for path in destinations if path.exists() or is_link(path)]
    if conflicts:
        joined = ", ".join(str(path) for path in conflicts)
        raise InstallError(f"Refusing to overwrite existing skills: {joined}")
    if dry_run:
        return destinations

    destination_root.mkdir(parents=True, exist_ok=True)
    for name, destination in zip(selected, destinations):
        try:
            # copytree creates the destination exclusively; no dirs_exist_ok.
            shutil.copytree(
                available[name], destination,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
        except OSError as exc:
            raise InstallError(
                f"Copy failed; earlier skills or partial files may remain at "
                f"{destination}. No existing skill is overwritten. {exc}"
            ) from exc
    return destinations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path, help="Existing target project")
    parser.add_argument("--skill", action="append", dest="names", help="Skill to copy; repeatable")
    parser.add_argument("--dry-run", action="store_true", help="Check selection without writing")
    parser.add_argument("--agent", choices=sorted(AGENT_DIRECTORIES), default="codex",
                        help="codex: .agents/skills (default); claude: .claude/skills for Claude Code")
    args = parser.parse_args()
    try:
        destinations = install_skills(
            SOURCE_ROOT, args.project.expanduser(), args.names, dry_run=args.dry_run, agent=args.agent,
        )
    except (InstallError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    action = "Would install" if args.dry_run else "Installed"
    for destination in destinations:
        print(f"{action}: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
