"""Every troubleshooting situation has a cause, a runnable check and a fix."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / 'docs/troubleshooting.md'
COPY = ROOT / '.agents/skills/telegram-debugging/references/troubleshooting.md'


class TroubleshootingTests(unittest.TestCase):
    def setUp(self):
        self.text = PAGE.read_text(encoding='utf-8')

    def test_at_least_thirty_situations_with_check_and_fix(self):
        sections = re.split(r'^### ', self.text, flags=re.M)[1:]
        self.assertGreaterEqual(len(sections), 30)
        for number, section in enumerate(sections, 1):
            title = section.splitlines()[0]
            with self.subTest(section=title):
                self.assertTrue(title.startswith(f'{number}. '), 'situations are numbered in order')
                self.assertIn('**Причина.**', section)
                check = section.split('**Проверка.**', 1)[1].split('**Решение.**', 1)
                self.assertEqual(len(check), 2, 'check comes before the fix')
                self.assertRegex(check[0], r'```(bash|python)\n', 'every check is a command or code')
                self.assertTrue(check[1].strip())

    def test_named_problems_are_covered(self):
        for phrase in ('409 Conflict', 'privacy mode', 'initData', 'message is not modified', '429 Too Many Requests',
                       'can_read_all_group_messages', 'answerCallbackQuery', 'BUTTON_DATA_INVALID', 'pre_checkout_query'):
            self.assertIn(phrase, self.text)

    def test_read_only_tool_never_includes_updates_or_secrets(self):
        code = re.search(r'<!-- troubleshooting:tg.py -->\n```python\n(.*?)\n```', self.text, re.S).group(1)
        compile(code, 'tg.py', 'exec')
        safe = set(re.findall(r"'(get[A-Za-z]+)'", code.split('if len(sys.argv)')[0]))
        self.assertIn('getMe', safe); self.assertIn('getWebhookInfo', safe)
        self.assertNotIn('getUpdates', safe); self.assertNotIn('getManagedBotToken', safe)
        self.assertNotIn('print(token', code)

    def test_skill_copy_is_identical(self):
        self.assertEqual(COPY.read_bytes(), PAGE.read_bytes())


if __name__ == '__main__':
    unittest.main()
