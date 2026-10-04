"""Validate skill packaging, metadata, links and Python syntax without executing skills."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

try:
    import yaml
except ImportError:
    raise SystemExit(
        'PyYAML is required: uv run --with "PyYAML>=6,<7" python scripts/validate_skills.py'
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.DOTALL)
NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
LINK_PATTERN = re.compile(r"!?\[[^\]\n]+\]\(([^)\n]+)\)")
ALLOWED_FIELDS = {"name", "description", "license", "metadata", "allowed-tools"}


def load_mapping(text: str, label: Path, errors: list[str]) -> dict:
    try:
        result = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        errors.append(f"{label}: invalid YAML: {exc}")
        return {}
    if not isinstance(result, dict):
        errors.append(f"{label}: YAML must be a mapping")
        return {}
    return result


def validate(root: Path) -> tuple[int, list[str]]:
    errors: list[str] = []
    skills_root = root / ".agents" / "skills"
    if not skills_root.is_dir():
        return 0, [f"Missing skill directory: {skills_root}"]
    folders = sorted(path for path in skills_root.iterdir() if path.is_dir())
    if not folders:
        return 0, ["No skill folders found"]
    seen: set[str] = set()
    for folder in folders:
        entry = folder / "SKILL.md"
        if not entry.is_file():
            errors.append(f"{folder}: missing SKILL.md")
            continue
        text = entry.read_text(encoding="utf-8")
        match = FRONTMATTER.match(text)
        if not match:
            errors.append(f"{entry}: missing or malformed YAML frontmatter")
            continue
        data = load_mapping(match.group(1), entry, errors)
        unknown = set(data) - ALLOWED_FIELDS
        if unknown:
            errors.append(f"{entry}: unsupported frontmatter fields: {sorted(unknown)}")
        name = data.get("name")
        if not isinstance(name, str) or len(name) > 64 or not NAME_PATTERN.fullmatch(name):
            errors.append(f"{entry}: invalid skill name")
        elif name != folder.name:
            errors.append(f"{entry}: name does not match directory")
        elif name in seen:
            errors.append(f"{entry}: duplicate name")
        else:
            seen.add(name)
        description = data.get("description")
        if not isinstance(description, str) or not description.strip() or len(description) > 1024:
            errors.append(f"{entry}: description must be a nonempty string of at most 1024 chars")
        elif "<" in description or ">" in description:
            errors.append(f"{entry}: description contains angle brackets")
        if not text[match.end():].strip():
            errors.append(f"{entry}: empty skill instructions")
        if "[TODO:" in text:
            errors.append(f"{entry}: unfinished scaffold")

        metadata_path = folder / "agents" / "openai.yaml"
        if not metadata_path.is_file():
            errors.append(f"{folder}: missing UI metadata")
        else:
            ui = load_mapping(metadata_path.read_text(encoding="utf-8"), metadata_path, errors)
            interface = ui.get("interface", {})
            if not isinstance(interface, dict):
                errors.append(f"{metadata_path}: interface must be a mapping")
                interface = {}
            display = interface.get("display_name", "")
            short = interface.get("short_description", "")
            prompt = interface.get("default_prompt", "")
            if not isinstance(display, str) or not display.strip():
                errors.append(f"{metadata_path}: missing display_name")
            if not isinstance(short, str) or not 25 <= len(short) <= 64:
                errors.append(f"{metadata_path}: short_description must be 25-64 chars")
            if not isinstance(prompt, str) or f"${folder.name}" not in prompt:
                errors.append(f"{metadata_path}: default_prompt must mention ${folder.name}")

    # Validate local links everywhere; skill-local links must stay standalone.
    for document in root.rglob("*.md"):
        if any(part in {".git", ".venv", "node_modules"} for part in document.parts):
            continue
        text = document.read_text(encoding="utf-8")
        skill_folder = next((folder for folder in folders if document.is_relative_to(folder)), None)
        for raw in LINK_PATTERN.findall(text):
            target = raw.strip()
            if target.startswith("<"):
                target = target[1:target.find(">")]
            elif ' "' in target:
                target = target.split(' "', 1)[0]
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith(("#", "//")):
                continue
            if not parsed.path:
                continue
            destination = (document.parent / unquote(parsed.path)).resolve()
            if not destination.exists():
                errors.append(f"{document}: broken local link: {raw}")
            if skill_folder is not None and not destination.is_relative_to(skill_folder.resolve()):
                errors.append(f"{document}: skill link escapes standalone folder: {raw}")
    for script in root.rglob("*.py"):
        if any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in script.parts):
            continue
        try:
            ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
        except SyntaxError as exc:
            errors.append(f"{script}: {exc}")
    return len(folders), errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="Collection root")
    args = parser.parse_args()
    try:
        count, errors = validate(args.root.resolve())
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        print(f"FAILED: {len(errors)} packaging error(s)")
        return 1
    print(f"PASS: {count} skills; metadata, standalone links and Python syntax checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
