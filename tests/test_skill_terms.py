"""Skills explain their jargon on first use and do not hide meaning in glued English phrases."""
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from _glossary import TERMS, explained, terms_line, used_terms, with_terms_line  # noqa: E402

WORD = r"[A-Za-z][A-Za-z0-9'\-]*"
# "host-verified native disabled grid": four English words in a row read as an untranslated phrase.
PHRASE = re.compile(WORD + r'(?: ' + WORD + r'){3,}')
# "owner/bot/chat/thread/message/session/revision": six glued words are a list the reader has to decode.
GLUED = re.compile(WORD + r'(?:[ ,/]+' + WORD + r'){5,}')


def skill_files():
    for path in sorted((ROOT / '.agents/skills').rglob('*.md')):
        text = path.read_text(encoding='utf-8')
        yield path.relative_to(ROOT).as_posix(), re.sub(r'\A---\n.*?\n---\n', '', text, flags=re.S)


def reader_prose(text: str) -> str:
    """Words a reader parses as sentences: no code, links, quoted interface labels or the sources section."""
    text = re.split(r'^## Источники\s*$', text, flags=re.M)[0]
    text = re.sub(r'^```.*?^```', '\n', text, flags=re.S | re.M)
    for pattern in (r'`[^`\n]+`', r'\[[^\]]*\]\([^)]*\)', r'https?://\S+', r'«[^»\n]*»'):
        text = re.sub(pattern, ' | ', text)
    return text


class SkillTermTests(unittest.TestCase):
    def test_every_term_is_explained_where_the_reader_meets_it(self):
        mentions = 0
        for name, text in skill_files():
            for term in TERMS:
                if re.search(TERMS[term][0], text):
                    mentions += 1
                with self.subTest(file=name, term=term):
                    self.assertTrue(explained(text, term), 'explain the term at its first mention or refresh the '
                                    '«Термины:» line with scripts/add_terms_lines.py')
        self.assertGreater(mentions, 50)

    def test_reference_term_lines_are_current(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/add_terms_lines.py'), '--check'],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_untranslated_phrases_in_skill_prose(self):
        for name, text in skill_files():
            prose = reader_prose(text)
            for pattern in (PHRASE, GLUED):
                for match in pattern.finditer(prose):
                    with self.subTest(file=name, text=match.group(0)):
                        self.fail('rewrite as a Russian sentence; identifiers go in backticks, interface labels in «»')

    def test_rules_catch_the_old_forms_and_allow_identifiers(self):
        for sample in ('Используйте host-verified native disabled grid.',
                       'связывайте действие с owner/bot/chat/thread/message/session/revision;'):
            with self.subTest(sample=sample):
                self.assertTrue(PHRASE.search(reader_prose(sample)) or GLUED.search(reader_prose(sample)))
        for sample in ('Статусы `queued`, `running`, `ready`, `failed`, `canceled`.',
                       'Откройте «Login to another account».', 'Смотрите [Bot API changelog and more](x.md).'):
            with self.subTest(sample=sample):
                self.assertIsNone(PHRASE.search(reader_prose(sample)) or GLUED.search(reader_prose(sample)))

    def test_terms_line_explains_terms_that_explanations_use(self):
        text = '# Заголовок\n\nНазад к сверке через CAS.\n'
        self.assertEqual(used_terms(text), ['CAS', 'сверка'])
        updated = with_terms_line(text)
        self.assertTrue(updated.startswith('# Заголовок\n\n' + terms_line(['CAS', 'сверка']) + '\n\n'))
        self.assertEqual(with_terms_line(updated), updated)
        self.assertTrue(explained('Повтор после ACK (ответ на нажатие кнопки).', 'ACK'))
        self.assertFalse(explained('Повтор после ACK без пояснения.', 'ACK'))


if __name__ == '__main__':
    unittest.main()
