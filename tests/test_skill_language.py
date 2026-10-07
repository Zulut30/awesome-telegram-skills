"""Skill text is Russian prose addressed with «вы»; English stays in code, identifiers and names.

Latin share: letters of lowercase English words in prose divided by all letters, where prose
excludes the frontmatter, the «Источники» section, code blocks, inline code, link targets,
links whose text is a path, hyphenated or library names and capitalized names (Telegram, Mini App).
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 0.15
LIBRARIES = {'aiogram', 'python', 'npm', 'pip', 'uv', 'tsc', 'vite', 'pytest', 'mypy', 'node', 'git', 'telethon'}
# Singular imperatives once used in skills; the plural «вы» form is the project's single address.
SINGULAR = set("""
адаптируй анимируй бери валидируй верифицируй верни вкладывай включай включи внедряй внеси возвращай
воспроизведи восстанавливай встрой выбери выбирай выводи выдавай выдели выделяй выдумывай вызови вызывай
вынеси выполни выполняй вычисляй дай действуй делай дели держи добавляй добавь доверяй допускай журналируй
завершай загружай задай задерживай закрой закрывай заменяй записывай запиши заполни заполняй запрашивай
запускай запусти зафиксируй защити заявляй избегай извлекай измени изменяй измерь измеряй изобретай изолируй
изучи имитируй импортируй инициализируй исключи исполняй используй исправляй исправь испытай ищи классифицируй
контролируй копируй лечи логируй маршрутизируй маскируй меняй мигрируй моделируй навязывай назначь назови
называй найди нарисуй настрой начни нормализуй обеспечь обещай обнови обновляй обозначай обоснуй обрабатывай
обработай обрезай обходи объявляй объясни объясняй ограничивай ограничь описывай опиши определи определяй
ориентируй оставь отвечай отдели отделяй отклоняй отключай открой отменяй отметь отмечай отправляй отсортируй
оцени очисти очищай парси переведи переводи передавай передай переиспользуй переноси перепроверяй перехватывай
перечисляй печатай пиши повтори повторяй подбирай подготовь поддерживай подключай подключи подменяй подпиши
подтверди подтверждай позволяй покажи показывай покрой получай получи пометь помещай понижай посмотри построй
преврати превращай предложи предполагай предпочти представь предусмотри привяжи привязывай придумывай применяй
принимай приписывай приравнивай проверь проверяй продвигай пройди прокручивай проследи прочитай прячь публикуй
путай работай разбери раздели разделяй различай разрешай раскрывай рассмотри рассчитывай растягивай расширяй
реализуй регистрируй резервируй сверь сверяй своди свяжи связывай сериализуй складывай скрывай следуй смешивай
смоделируй смотри снимай сними собери собирай соблюдай согласуй соедини создавай создай сокращай сообщи
сопоставляй сопоставь составь сохрани сохраняй сравни сравнивай ставь считай теряй тестируй трактуй требуй
убирай увеличивай удаляй укажи устанавливай установи уточни уточняй учитывай учти фиксируй форматируй формируй
храни читай экранируй вернись дождись обращайся ограничивайся опирайся переносись подписывайся полагайся
пользуйся пытайся убедись
""".split())


def prose(text: str) -> str:
    text = re.sub(r'\A---\n.*?\n---\n', '', text.replace('\r\n', '\n'), flags=re.S)
    text = text.split('\n## Источники')[0]
    text = re.sub(r'^```.*?^```', ' ', text, flags=re.S | re.M)
    text = re.sub(r'`[^`\n]+`', ' ', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', lambda m: ' ' if re.search(r'[/.]', m.group(1)) else m.group(1), text)
    return re.sub(r'https?://\S+', ' ', text)


def latin_share(text: str) -> float:
    body = prose(text)
    words = [word for word in re.findall(r'(?<![\w/.-])([A-Za-z][A-Za-z-]*)(?![\w/.])', body)
             if word[0].islower() and '-' not in word and word.lower() not in LIBRARIES and not re.search(r'[A-Z]', word[1:])]
    latin = sum(map(len, words))
    return latin / max(1, latin + len(re.findall(r'[А-Яа-яЁё]', body)))


class SkillLanguageTests(unittest.TestCase):
    def test_skill_prose_is_mostly_russian(self):
        for path in sorted((ROOT / '.agents/skills').glob('*/SKILL.md')):
            with self.subTest(skill=path.parent.name):
                self.assertLessEqual(round(latin_share(path.read_text(encoding='utf-8')), 3), LIMIT)

    def test_metric_counts_english_prose_only(self):
        self.assertGreater(latin_share('Проверьте backend и frontend payload перед webhook.\n'), 0.3)
        self.assertEqual(latin_share('Проверьте `backend_url` и [docs/x.md](docs/x.md) в Telegram Mini App.\n'), 0)

    def test_one_form_of_address(self):
        for path in sorted((ROOT / '.agents/skills').rglob('*.md')):
            text = re.sub(r'^```.*?^```', ' ', path.read_text(encoding='utf-8'), flags=re.S | re.M)
            text = re.sub(r'`[^`\n]+`', ' ', text)
            found = sorted({word.lower() for word in re.findall(r'[А-Яа-яЁё]+', text)} & SINGULAR)
            with self.subTest(file=path.relative_to(ROOT).as_posix()):
                self.assertEqual(found, [], 'use the «вы» form: проверьте, используйте')


if __name__ == '__main__':
    unittest.main()
