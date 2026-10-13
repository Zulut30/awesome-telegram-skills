"""A long skill reference lists its sections near the top, so a partial read (head -100) shows what it covers."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('_contents', ROOT / 'scripts/_contents.py')
contents = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contents)


def page(lines: int, sections: list[str], head: str = '# Title\n\n') -> str:
    body = ''.join(f'## {name}\n\n' + 'text\n' * (lines // max(len(sections), 1)) for name in sections)
    return head + body


class ReferenceContentsTests(unittest.TestCase):
    def test_line_follows_title_label_and_terms_and_is_stable(self):
        head = '# Title\n\nДоступно с 0.21.0, проверено на 0.24.0.\n\nТермины: **ACK** — ответ.\n\n'
        text = contents.with_contents_line(page(120, ['Один', 'Два'], head))
        self.assertTrue(text.startswith(head + 'Разделы: Один; Два.\n\n## Один'), text[:200])
        self.assertEqual(contents.with_contents_line(text), text)

    def test_short_or_single_section_pages_have_no_line_and_stale_lines_go(self):
        short = page(40, ['Один', 'Два'])
        self.assertEqual(contents.with_contents_line(short), short)
        single = page(150, ['Один'])
        self.assertEqual(contents.with_contents_line(single), single)
        self.assertEqual(contents.with_contents_line(short.replace('# Title\n\n', '# Title\n\nРазделы: Старый.\n\n')), short)

    def test_headings_inside_code_blocks_are_not_sections(self):
        text = page(120, ['Один', 'Два']) + '```markdown\n## Не раздел\n```\n'
        self.assertIn('Разделы: Один; Два.\n', contents.with_contents_line(text))

    def test_every_skill_reference_has_a_current_line(self):
        listed = 0
        for path in sorted((ROOT / '.agents/skills').glob('*/references/*.md')):
            text = path.read_text(encoding='utf-8')
            listed += contents.LINE_PREFIX in text
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                # add_terms_lines.py writes the line; build_api_reference.py, for the generated API pages.
                self.assertEqual(contents.with_contents_line(text), text)
        self.assertGreaterEqual(listed, 10)


if __name__ == '__main__':
    unittest.main()
