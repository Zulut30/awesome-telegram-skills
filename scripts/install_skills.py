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
# Skill directories each agent reads, from its documentation (checked 2026-10-07). The same
# relative path is used in a project and, with --user, in the home directory, except Copilot,
# whose personal skills live in ~/.copilot/skills while project skills use .github/skills.
#   Codex: .agents/skills, ~/.agents/skills.  Claude Code: .claude/skills, ~/.claude/skills only.
#   Copilot: .github/skills (.claude/.agents too), ~/.copilot/skills (~/.agents/skills too).
#   Cursor: .cursor/skills (.agents/.claude/.codex too), ~/.cursor/skills.
#   Gemini CLI: .gemini/skills (.agents/skills alias), ~/.gemini/skills.
AGENT_DIRECTORIES = {
    "codex": {"project": (".agents", "skills"), "user": (".agents", "skills")},
    "claude": {"project": (".claude", "skills"), "user": (".claude", "skills")},
    "copilot": {"project": (".github", "skills"), "user": (".copilot", "skills")},
    "cursor": {"project": (".cursor", "skills"), "user": (".cursor", "skills")},
    "gemini": {"project": (".gemini", "skills"), "user": (".gemini", "skills")},
}
# .agents/skills is read by Codex, Copilot, Cursor and Gemini CLI; Claude Code needs .claude/skills.
ALL_AGENTS = ("codex", "claude")


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


def skill_roots(agent: str, *, user: bool = False) -> list[tuple[str, str]]:
    """Relative (parent, leaf) skill directories for an agent or for "all"."""
    if agent != "all" and agent not in AGENT_DIRECTORIES:
        choices = ", ".join([*AGENT_DIRECTORIES, "all"])
        raise InstallError(f"Unknown agent: {agent}; choose one of {choices}")
    scope = "user" if user else "project"
    agents = ALL_AGENTS if agent == "all" else (agent,)
    return list(dict.fromkeys(AGENT_DIRECTORIES[name][scope] for name in agents))


def install_skills(
    source_root: Path,
    project: Path,
    names: list[str] | None = None,
    *,
    dry_run: bool = False,
    agent: str = "codex",
    user: bool = False,
) -> list[Path]:
    """Copy skills into every directory the agent reads; project is the home directory with user=True."""
    roots = skill_roots(agent, user=user)
    if not source_root.is_dir():
        raise InstallError(f"Skill source directory does not exist: {source_root}")
    if is_link(source_root):
        raise InstallError(f"Source links are unsupported: {source_root}")
    if not project.is_dir():
        raise InstallError(f"Target {'home' if user else 'project'} directory must already exist: {project}")
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

    destination_roots = []
    for base, leaf in roots:
        destination_root = project / base / leaf
        for parent in (project / base, destination_root):
            if is_link(parent):
                raise InstallError(f"Destination links are unsupported: {parent}")
            if parent.exists() and not parent.is_dir():
                raise InstallError(f"Destination parent is not a directory: {parent}")
        if not destination_root.resolve().is_relative_to(project):
            raise InstallError("Destination escapes the target directory")
        destination_roots.append(destination_root)

    # Every conflict in every agent directory is checked before the first write.
    plan = [(root, name, root / name) for root in destination_roots for name in selected]
    conflicts = [path for _, _, path in plan if path.exists() or is_link(path)]
    if conflicts:
        joined = ", ".join(str(path) for path in conflicts)
        raise InstallError(f"Refusing to overwrite existing skills: {joined}")
    destinations = [path for _, _, path in plan]
    if dry_run:
        return destinations

    for root, name, destination in plan:
        root.mkdir(parents=True, exist_ok=True)
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
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--project", type=Path, help="Existing target project")
    target.add_argument("--user", action="store_true",
                        help="Install into your home directory for every project instead")
    parser.add_argument("--skill", action="append", dest="names", help="Skill to copy; repeatable")
    parser.add_argument("--dry-run", action="store_true", help="Check selection without writing")
    parser.add_argument(
        "--agent", choices=[*AGENT_DIRECTORIES, "all"], default="codex",
        help="codex .agents/skills (default), claude .claude/skills, copilot .github/skills "
             "(--user: ~/.copilot/skills), cursor .cursor/skills, gemini .gemini/skills; "
             "all = .agents/skills + .claude/skills, read by every agent above",
    )
    args = parser.parse_args()
    target_dir = Path.home() if args.user else args.project.expanduser()
    try:
        destinations = install_skills(
            SOURCE_ROOT, target_dir, args.names, dry_run=args.dry_run, agent=args.agent, user=args.user,
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
