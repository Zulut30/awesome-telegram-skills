"""Index names and field names from official Bot API HTML; no credentials or API calls."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen


SOURCE = "https://core.telegram.org/bots/api"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "references" / "api-index.json"


class IndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: dict[str, dict] = {}
        self.heading: list[str] | None = None
        self.anchor = ""
        self.current: dict | None = None
        self.first_cell: list[str] | None = None
        self.column = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h4":
            self.heading = []
            self.anchor = ""
            self.current = None
        elif tag in {"h1", "h2", "h3"}:
            self.current = None
        elif tag == "a" and self.heading is not None:
            values = dict(attrs)
            self.anchor = values.get("name") or values.get("id") or self.anchor
        elif tag == "tr":
            self.column = 0
        elif tag in {"td", "th"}:
            self.column += 1
            if tag == "td" and self.column == 1 and self.current is not None:
                self.first_cell = []

    def handle_data(self, data: str) -> None:
        if self.heading is not None:
            self.heading.append(data)
        if self.first_cell is not None:
            self.first_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h4" and self.heading is not None:
            name = "".join(self.heading).strip()
            self.heading = None
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
                return
            if name in self.entries:
                raise ValueError(f"Duplicate API entry: {name}")
            entry = {
                "name": name,
                "kind": "method" if name[0].islower() else "type",
                "url": f"{SOURCE}#{self.anchor or name.lower()}",
                "fields": [],
            }
            self.entries[name] = entry
            self.current = entry
        elif tag == "td" and self.first_cell is not None:
            field = "".join(self.first_cell).strip()
            self.first_cell = None
            if self.current is not None and re.fullmatch(r"[a-z][a-z0-9_]*", field):
                if field not in self.current["fields"]:
                    self.current["fields"].append(field)


def parse_index(html: str) -> dict:
    parser = IndexParser()
    parser.feed(html)
    parser.close()
    if not {"getMe", "sendMessage", "User", "InlineKeyboardButton"}.issubset(parser.entries):
        raise ValueError("Unexpected documentation layout; required API entries are missing")
    version = re.search(r"Bot API (\d+\.\d+)", html)
    return {
        "source": SOURCE,
        "bot_api_version": version.group(1) if version else None,
        "source_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "scope": "Documented h4 method/type headings and first-column field names; no descriptions",
        "methods": sorted(
            (item for item in parser.entries.values() if item["kind"] == "method"),
            key=lambda item: item["name"],
        ),
        "types": sorted(
            (item for item in parser.entries.values() if item["kind"] == "type"),
            key=lambda item: item["name"],
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--html-file", type=Path, help="Parse saved official HTML instead of fetching")
    args = parser.parse_args()
    if args.html_file:
        html = args.html_file.read_text(encoding="utf-8")
    else:
        request = Request(SOURCE, headers={"User-Agent": "AwesomeTelegramSkills/1.0"})
        with urlopen(request, timeout=30) as response:
            html = response.read(10_000_001)
            if len(html) > 10_000_000:
                raise ValueError("Documentation exceeds the fetch size limit")
            html = html.decode("utf-8")
    index = parse_index(html)
    index["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    index["retrieval"] = "saved_html" if args.html_file else "official_https"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(args.output)
    print(f"Bot API {index['bot_api_version']}: {len(index['methods'])} methods, "
          f"{len(index['types'])} types; wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
