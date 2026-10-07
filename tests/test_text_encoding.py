"""В отслеживаемых текстовых файлах нет UTF-8, ошибочно прочитанного как CP1251."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Частые буквы и тире, записанные в UTF-8 и прочитанные как CP1251, дают пары символов,
# которых нет в обычном русском тексте. Шаблон строится здесь, чтобы не содержать их буквально.
MOJIBAKE = re.compile('|'.join(re.escape(ch.encode('utf-8').decode('cp1251')[:2]) for ch in '—анлосиет'))
TEXT_SUFFIXES = {'.py', '.md', '.json', '.ts', '.mjs', '.js', '.txt', '.yaml', '.yml', '.html', '.css', '.toml'}
# План описывает саму ошибку и намеренно цитирует пример.
DOCUMENTED_EXAMPLES = {'docs/excellence-plan-100.md'}


class TextEncodingTests(unittest.TestCase):
    def test_tracked_text_has_no_mojibake(self):
        files = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, check=True, capture_output=True).stdout.decode().split('\0')
        found = []
        for name in files:
            path = ROOT / name
            if not name or name in DOCUMENTED_EXAMPLES or path.suffix not in TEXT_SUFFIXES or not path.is_file():
                continue
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if MOJIBAKE.search(line):
                    found.append(f'{name}:{number}')
        self.assertEqual(found, [])


if __name__ == '__main__':
    unittest.main()
