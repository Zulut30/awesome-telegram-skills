"""Validate skill packaging, metadata, links and Python syntax without executing skills."""

from __future__ import annotations

import argparse
import ast
from datetime import date, timedelta
import json
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
BOUNDARY = re.compile(r"(?:^|[.;] )Не для ")
LINK_PATTERN = re.compile(r"!?\[[^\]\n]+\]\(([^)\n]+)\)")
# Agent Skills specification (agentskills.io/specification), checked 2026-10-07.
ALLOWED_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
SOURCES_HEADING = "## Источники"
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".txt"}
# Repository-style paths named in inline code or code blocks. A skill is copied on its own, so
# SKILL.md may only name files inside its folder; references may also name repository files.
REPO_PATH = re.compile(r"(?<![\w./-])((?:scripts|docs|output|catalog|packages|examples|tests|recipes|gallery|site)"
                       r"/[\w./-]*[\w-]|components\.json)")
VERSIONED_OUTPUT = re.compile(r"(?:pattern-library-|awesome[_-]telegram[_-]patterns-)(\d+\.\d+\.\d+)")
SKILL_NAME = re.compile(r"(?<![\w@/.-])(telegram-[a-z0-9]+(?:-[a-z0-9]+)*)")
# Identifiers that look like skill names but are a CLI, SDK id, script or distribution.
NOT_SKILLS = {"telegram-patterns", "telegram-environment", "telegram-first-run", "telegram-group-example",
              "telegram-service-example", "telegram-shop-example", "telegram-web-app", "telegram-webapp"}


def code_spans(text: str) -> list[str]:
    blocks = re.findall(r"^```[^\n]*\n(.*?)^```", text, re.MULTILINE | re.DOTALL)
    inline = re.findall(r"`([^`\n]+)`", re.sub(r"^```[^\n]*\n.*?^```", "", text, flags=re.MULTILINE | re.DOTALL))
    return blocks + inline


def check_skill_files(root: Path, folder: Path, skills: set[str], library_version: str | None) -> list[str]:
    """LF endings, paths that exist where a reader will look, and neighbour names that are real skills."""
    errors = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES or "__pycache__" in path.parts:
            continue
        raw = path.read_bytes()
        if b"\r\n" in raw:
            errors.append(f"{path}: CRLF line endings; skill files use LF")
        text = raw.decode("utf-8", errors="replace")
        for name in sorted(set(SKILL_NAME.findall(text)) - skills - NOT_SKILLS):
            errors.append(f"{path}: names unknown skill {name}")
        if path.suffix != ".md":
            continue
        for span in code_spans(text):
            for target in REPO_PATH.findall(span):
                version = VERSIONED_OUTPUT.search(target)
                if version and library_version and version.group(1) != library_version:
                    errors.append(f"{path}: {target} points at version {version.group(1)}, not {library_version}")
                if (folder / target).exists():
                    continue
                if path.name == "SKILL.md":
                    errors.append(f"{path}: SKILL.md names {target}, which is not inside the skill folder")
                elif not (target.startswith("output/") or target.endswith("/.env") or (root / target).exists()):
                    errors.append(f"{path}: {target} exists neither in the skill nor in the repository")
    return errors
CHECKED = re.compile(r"^Проверено: (\d{4}-\d{2}-\d{2}), \S.*$", re.MULTILINE)


def check_sources(body: str, today: date | None = None) -> str | None:
    """The last section names its sources and the ISO date they were checked against the skill."""
    headings = [line.strip() for line in re.findall(r"^## .*$", body, re.MULTILINE)]
    if SOURCES_HEADING not in headings:
        return f"missing '{SOURCES_HEADING}' section"
    if headings[-1] != SOURCES_HEADING:
        return f"'{SOURCES_HEADING}' must be the last section"
    section = body[body.rindex(SOURCES_HEADING):]
    if not re.search(r"\]\(https?://", section):
        return f"'{SOURCES_HEADING}' needs at least one source link"
    checked = CHECKED.findall(section)
    if len(checked) != 1:
        return f"'{SOURCES_HEADING}' needs exactly one line 'Проверено: YYYY-MM-DD, <что проверено>'"
    try:
        value = date.fromisoformat(checked[0])
    except ValueError:
        return f"invalid check date: {checked[0]}"
    if value > (today or date.today()) + timedelta(days=1):  # one day of slack for time zones
        return f"check date is in the future: {checked[0]}"
    return None


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
    try:
        expected_version = json.loads((root / "components.json").read_text(encoding="utf-8"))["library_version"]
    except (OSError, ValueError, KeyError):
        expected_version = None
        errors.append(f"{root / 'components.json'}: library_version is needed for metadata.version")
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
        if isinstance(description, str):
            boundary = BOUNDARY.search(description)
            targets = re.findall(r"→ (telegram-[a-z0-9-]+)", description[boundary.start():]) if boundary else []
            if not targets:
                errors.append(f"{entry}: description must say when not to use the skill: 'Не для ... → telegram-<skill>'")
            for target in targets:
                if target == folder.name or not (skills_root / target / "SKILL.md").is_file():
                    errors.append(f"{entry}: boundary points to unknown or same skill: {target}")
        license_value = data.get("license")
        if not isinstance(license_value, str) or not license_value.strip():
            errors.append(f"{entry}: license must name the skill license")
        compatibility = data.get("compatibility")
        if compatibility is not None and (not isinstance(compatibility, str) or not 1 <= len(compatibility) <= 500):
            errors.append(f"{entry}: compatibility must be a string of 1-500 chars")
        tools = data.get("allowed-tools")
        if tools is not None and (not isinstance(tools, str) or not tools.strip()):
            errors.append(f"{entry}: allowed-tools must be a space-separated string")
        metadata = data.get("metadata")
        if not isinstance(metadata, dict) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()):
            errors.append(f"{entry}: metadata must map string keys to string values")
        elif expected_version is not None and metadata.get("version") != expected_version:
            errors.append(f"{entry}: metadata.version must be \"{expected_version}\" (components.json library_version)")
        if not text[match.end():].strip():
            errors.append(f"{entry}: empty skill instructions")
        if "[TODO:" in text:
            errors.append(f"{entry}: unfinished scaffold")
        sources_error = check_sources(text[match.end():])
        if sources_error:
            errors.append(f"{entry}: {sources_error}")
        errors.extend(check_skill_files(root, folder, {path.name for path in folders}, expected_version))

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
