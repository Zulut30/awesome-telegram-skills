"""Check discovery and parameter extraction, including changed/error source layouts."""

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / ".agents/skills/telegram-bot-api/scripts/update_api_index.py"
SPEC = importlib.util.spec_from_file_location("api_index", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
indexer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(indexer)


HTML = """<h4>October 2, 2026</h4><p>Bot API 10.3</p>
<h3>Available types</h3><h4><a name="user"></a>User</h4>
<table><tr><th>Field</th><th>Type</th></tr><tr><td>id</td><td>Integer</td></tr></table>
<h4><a name="inlinekeyboardbutton"></a>InlineKeyboardButton</h4>
<table><tr><td>icon_custom_emoji_id</td><td>String</td></tr><tr><td>style</td><td>String</td></tr></table>
<h3>Available methods</h3><h4><a name="getme"></a>getMe</h4>
<h4><a name="sendmessage"></a>sendMessage</h4>
<table><tr><td><em>chat_id</em></td><td>Integer</td></tr><tr><td>text</td><td>String</td></tr></table>
<h4>Formatting options</h4><table><tr><td>unrelated</td><td>text</td></tr></table>
"""


class ApiIndexTests(unittest.TestCase):
    def test_discovers_methods_and_types_without_dates_or_prose_headings(self) -> None:
        result = indexer.parse_index(HTML)
        self.assertEqual([item["name"] for item in result["methods"]], ["getMe", "sendMessage"])
        self.assertEqual([item["name"] for item in result["types"]], ["InlineKeyboardButton", "User"])
        self.assertEqual(result["bot_api_version"], "10.3")

    def test_extracts_nested_parameter_names_and_correct_anchor(self) -> None:
        result = indexer.parse_index(HTML)
        method = next(item for item in result["methods"] if item["name"] == "sendMessage")
        self.assertEqual(method["fields"], ["chat_id", "text"])
        self.assertEqual(method["url"], "https://core.telegram.org/bots/api#sendmessage")

    def test_rejects_error_page_without_replacing_it_with_empty_index(self) -> None:
        with self.assertRaises(ValueError):
            indexer.parse_index("<h1>403 Forbidden</h1>")

    def test_rejects_duplicate_definitions(self) -> None:
        with self.assertRaises(ValueError):
            indexer.parse_index(HTML + "<h4>sendMessage</h4>")


if __name__ == "__main__":
    unittest.main()
