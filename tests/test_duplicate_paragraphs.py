"""SKILL.md files point to shared references instead of restating each other's paragraphs."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_duplicate_paragraphs', ROOT / 'scripts/check_duplicate_paragraphs.py')
checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)

LONG = ('Первое предложение про компонент. Второе предложение про права и повтор. '
        'Третье предложение про проверку в проекте. Четвертое предложение про ограничения.')


class DuplicateParagraphTests(unittest.TestCase):
    def tree(self, first, second):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        for name, body in (('telegram-a', first), ('telegram-b', second)):
            skill = root / '.agents/skills' / name; skill.mkdir(parents=True)
            (skill / 'SKILL.md').write_text(f'---\nname: {name}\n---\n\n# T\n\n{body}\n', encoding='utf-8')
        return root

    def test_copies_and_near_copies_are_found(self):
        self.assertEqual(len(checker.duplicates(self.tree(LONG, LONG))), 1)
        near = LONG.replace('проверку в проекте', 'проверку в вашем проекте')
        self.assertEqual(len(checker.duplicates(self.tree(LONG, near))), 1)

    def test_short_pointers_and_different_text_pass(self):
        pointer = 'С библиотекой: [операции](references/platform-operations.md).'
        self.assertEqual(checker.duplicates(self.tree(pointer, pointer)), [])
        other = 'Совсем другой текст. Он о другом. И третье предложение тоже. Четвертое здесь.'
        self.assertEqual(checker.duplicates(self.tree(LONG, other)), [])

    def test_repository_has_no_repeated_paragraphs(self):
        self.assertEqual(checker.duplicates(ROOT), [])


if __name__ == '__main__':
    unittest.main()
