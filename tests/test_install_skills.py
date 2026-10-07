"""Exercise actual installer filesystem operations only in temporary workspaces."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install_skills.py"
SPEC = importlib.util.spec_from_file_location("install_skills", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory(prefix="telegram-skills-test-")
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.sources = self.root / "sources"
        self.project = self.root / "project with spaces"
        self.sources.mkdir()
        self.project.mkdir()
        for name in ("telegram-alpha", "telegram-beta"):
            skill = self.sources / name
            (skill / "references").mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Test skill\n---\n"
                "[Reference](references/details.md)\n", encoding="utf-8",
            )
            (skill / "references" / "details.md").write_bytes(b"standalone reference\n")

    def test_copies_all_skills_and_references_byte_for_byte(self) -> None:
        destinations = installer.install_skills(self.sources, self.project)
        self.assertEqual(len(destinations), 2)
        for destination in destinations:
            for source in (self.sources / destination.name).rglob("*"):
                if source.is_file():
                    copied = destination / source.relative_to(self.sources / destination.name)
                    self.assertEqual(copied.read_bytes(), source.read_bytes())

    def test_selected_skill_does_not_copy_others(self) -> None:
        destinations = installer.install_skills(self.sources, self.project, ["telegram-beta"])
        self.assertEqual([path.name for path in destinations], ["telegram-beta"])
        self.assertFalse((self.project / ".agents" / "skills" / "telegram-alpha").exists())

    def test_dry_run_does_not_create_destination(self) -> None:
        destinations = installer.install_skills(self.sources, self.project, dry_run=True)
        self.assertEqual(len(destinations), 2)
        self.assertFalse((self.project / ".agents").exists())

    def test_existing_skill_blocks_entire_selection_and_preserves_content(self) -> None:
        existing = self.project / ".agents" / "skills" / "telegram-beta"
        existing.mkdir(parents=True)
        sentinel = existing / "user-content.txt"
        sentinel.write_bytes(b"keep this content")
        with self.assertRaises(installer.InstallError):
            installer.install_skills(self.sources, self.project)
        self.assertEqual(sentinel.read_bytes(), b"keep this content")
        self.assertFalse((existing.parent / "telegram-alpha").exists())

    def test_invalid_name_blocks_selection_before_any_write(self) -> None:
        with self.assertRaises(installer.InstallError):
            installer.install_skills(self.sources, self.project, ["telegram-alpha", "../escape"])
        self.assertFalse((self.project / ".agents").exists())

    def test_unknown_name_is_rejected(self) -> None:
        with self.assertRaises(installer.InstallError):
            installer.install_skills(self.sources, self.project, ["telegram-missing"])
        self.assertFalse((self.project / ".agents").exists())

    def test_missing_project_is_not_created(self) -> None:
        missing = self.root / "missing project"
        with self.assertRaises(installer.InstallError):
            installer.install_skills(self.sources, missing)
        self.assertFalse(missing.exists())

    def test_duplicate_selection_copies_once(self) -> None:
        destinations = installer.install_skills(
            self.sources, self.project, ["telegram-alpha", "telegram-alpha"],
        )
        self.assertEqual(len(destinations), 1)

    def test_destination_file_is_preserved(self) -> None:
        agent_path = self.project / ".agents"
        agent_path.write_bytes(b"user-owned file")
        with self.assertRaises(installer.InstallError):
            installer.install_skills(self.sources, self.project)
        self.assertEqual(agent_path.read_bytes(), b"user-owned file")

    def test_generated_python_cache_is_not_copied(self) -> None:
        cache = self.sources / "telegram-alpha" / "__pycache__"
        cache.mkdir()
        (cache / "helper.pyc").write_bytes(b"cache")
        destinations = installer.install_skills(self.sources, self.project, ["telegram-alpha"])
        self.assertFalse((destinations[0] / "__pycache__").exists())

    def test_claude_agent_installs_into_claude_skills_only(self) -> None:
        destinations = installer.install_skills(self.sources, self.project, ["telegram-alpha"], agent="claude")
        self.assertEqual(destinations, [self.project.resolve() / ".claude" / "skills" / "telegram-alpha"])
        self.assertEqual((destinations[0] / "SKILL.md").read_bytes(),
                         (self.sources / "telegram-alpha" / "SKILL.md").read_bytes())
        self.assertFalse((self.project / ".agents").exists())
        # Codex and Claude Code directories are independent: both can hold the same skill.
        installer.install_skills(self.sources, self.project, ["telegram-alpha"])
        self.assertTrue((self.project / ".agents" / "skills" / "telegram-alpha" / "SKILL.md").is_file())

    def test_unknown_agent_is_rejected_before_any_write(self) -> None:
        with self.assertRaises(installer.InstallError):
            installer.install_skills(self.sources, self.project, agent="unknown")
        self.assertEqual(list(self.project.iterdir()), [])

    def test_cli_agent_option(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--project", str(self.project), "--agent", "claude",
             "--skill", "telegram-bot-python", "--dry-run"],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(Path(".claude") / "skills" / "telegram-bot-python"), result.stdout)
        self.assertFalse((self.project / ".claude").exists())

    def make_symlink(self, link: Path, target: Path, *, directory: bool = True) -> None:
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            if os.name == "nt" and directory:
                environment = os.environ.copy()
                environment.update(TG_TEST_LINK=str(link), TG_TEST_TARGET=str(target))
                result = subprocess.run(
                    ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
                     "New-Item -ItemType Junction -Path $env:TG_TEST_LINK "
                     "-Target $env:TG_TEST_TARGET -ErrorAction Stop | Out-Null"],
                    env=environment, capture_output=True, timeout=15,
                )
                if result.returncode == 0:
                    return
            self.skipTest("Directory links are unavailable in this environment")

    def test_destination_link_cannot_redirect_installation(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        self.make_symlink(self.project / ".agents", outside)
        with self.assertRaises(installer.InstallError):
            installer.install_skills(self.sources, self.project)
        self.assertEqual(list(outside.iterdir()), [])

    def test_claude_destination_link_cannot_redirect_installation(self) -> None:
        outside = self.root / "outside claude"
        outside.mkdir()
        self.make_symlink(self.project / ".claude", outside)
        with self.assertRaises(installer.InstallError):
            installer.install_skills(self.sources, self.project, agent="claude")
        self.assertEqual(list(outside.iterdir()), [])

    def test_link_in_source_is_rejected_before_copy(self) -> None:
        outside = self.root / "private directory"
        outside.mkdir()
        (outside / "private.txt").write_bytes(b"private")
        self.make_symlink(self.sources / "telegram-alpha" / "linked-reference", outside)
        with self.assertRaises(installer.InstallError):
            installer.install_skills(self.sources, self.project)
        self.assertFalse((self.project / ".agents").exists())


if __name__ == "__main__":
    unittest.main()
