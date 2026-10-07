"""Rich message builder: InputRichMessage JSON, Telegram's limits and the plain-text fallback."""
import json
import unittest

from telegram_patterns import FormattedText, RichButton, RichMessageBuilder, RichSpan


def order() -> RichMessageBuilder:
    terms = RichSpan('url', 'условия', url='https://core.telegram.org/bots/api')
    return (RichMessageBuilder().heading('Заказ №42', size=1)
            .paragraph(['Статус: ', RichSpan('bold', 'оплачен'), ', ', terms])
            .table([['Товар', 'Цена'], ['Книга', '500 ₽']], compact=True, caption='Итого: 500 ₽')
            .checklist([('Оплата', True), ('Доставка', False)])
            .quote('Длинный комментарий', expandable=True, credit='Анна')
            .details('Подробнее', RichMessageBuilder().paragraph('Возврат 14 дней.'))
            .document('FIXTURE_DOCUMENT_ID', caption='Чек')
            .buttons([RichButton('Подтвердить', callback_data='order:confirm:42', style='success'),
                      RichButton('Отменить', callback_data='order:cancel:42', style='link')]))


class RichMessageTests(unittest.TestCase):
    def test_blocks_follow_the_bot_api_shapes(self):
        blocks = order().build().as_input()['blocks']
        self.assertEqual([block['type'] for block in blocks],
                         ['heading', 'paragraph', 'table', 'list', 'expandable_blockquote', 'details', 'document', 'buttons'])
        heading, paragraph, table, checklist, quote, details, document, buttons = blocks
        self.assertEqual(heading, {'type': 'heading', 'text': 'Заказ №42', 'size': 1})
        self.assertEqual(paragraph['text'][1], {'type': 'bold', 'text': 'оплачен'})
        self.assertEqual(paragraph['text'][3], {'type': 'url', 'text': 'условия', 'url': 'https://core.telegram.org/bots/api'})
        self.assertTrue(table['is_compact'] and table['is_bordered'] and 'is_striped' not in table)
        self.assertEqual(table['cells'][0][0], {'text': 'Товар', 'align': 'left', 'valign': 'top', 'is_header': True})
        self.assertNotIn('is_header', table['cells'][1][0])
        self.assertEqual(checklist['items'][0], {'blocks': [{'type': 'paragraph', 'text': 'Оплата'}], 'has_checkbox': True, 'is_checked': True})
        self.assertNotIn('is_checked', checklist['items'][1])
        self.assertEqual(quote, {'type': 'expandable_blockquote', 'text': 'Длинный комментарий', 'credit': 'Анна'})
        self.assertEqual(details['blocks'], [{'type': 'paragraph', 'text': 'Возврат 14 дней.'}])
        self.assertEqual(document, {'type': 'document', 'document': {'type': 'document', 'media': 'FIXTURE_DOCUMENT_ID'}, 'caption': {'text': 'Чек'}})
        self.assertEqual(buttons['buttons'][1], {'text': 'Отменить', 'callback_data': 'order:cancel:42', 'style': 'link'})

    def test_result_is_immutable_and_counts_blocks_like_telegram(self):
        message = order().build()
        first = message.as_input()
        first['blocks'].clear()
        self.assertEqual(len(message.as_input()['blocks']), 8, 'as_input returns a fresh copy')
        # heading, paragraph, table + 2 rows, list + 2 items + 2 paragraphs, quote, details + 1, document, buttons
        self.assertEqual((message.block_count, message.media_count), (15, 1))
        numbered = RichMessageBuilder().numbered(['a', 'b', 'c'], label='I').build().as_input()['blocks'][0]['items']
        self.assertEqual([(item['type'], item['value']) for item in numbered], [('I', 1), ('I', 2), ('I', 3)])
        flags = RichMessageBuilder(rtl=True, skip_entity_detection=True).paragraph('x').build().as_input()
        self.assertEqual((flags['is_rtl'], flags['skip_entity_detection']), (True, True))

    def test_published_limits_are_enforced(self):
        cases = {
            '501 blocks': lambda: RichMessageBuilder().bullets(['x'] * 250).build(),
            '17 levels': lambda: nested(16).build(),
            '51 documents': lambda: many_documents(51).build(),
            '21 columns': lambda: RichMessageBuilder().table([['x'] * 21]),
            '9 buttons': lambda: RichMessageBuilder().buttons([RichButton(str(i), callback_data=str(i)) for i in range(9)]),
            'too much text': lambda: RichMessageBuilder().paragraph('я' * 32769).build(),
            'heading size 7': lambda: RichMessageBuilder().heading('x', size=7),
            'empty message': lambda: RichMessageBuilder().build(),
        }
        for label, build in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                build()
        self.assertEqual(RichMessageBuilder().bullets(['x'] * 249).build().block_count, 499)
        self.assertEqual(nested(15).build().as_input()['blocks'][0]['type'], 'details')
        self.assertEqual(many_documents(50).build().media_count, 50)
        RichMessageBuilder().paragraph('я' * 32768).build()

    def test_buttons_and_spans_are_checked(self):
        for label, make in {'two actions': lambda: RichButton('x', url='https://example.org', callback_data='x'),
                            'no action': lambda: RichButton('x'),
                            'long callback': lambda: RichButton('x', callback_data='я' * 33),
                            'link style on url': lambda: RichButton('x', url='https://example.org', style='link'),
                            'unknown style': lambda: RichButton('x', callback_data='x', style='red'),
                            'tg link span': lambda: RichSpan('url', 'x', url='tg://user?id=1'),
                            'url on bold': lambda: RichSpan('bold', 'x', url='https://example.org'),
                            'blank text': lambda: RichMessageBuilder().paragraph('  ')}.items():
            with self.subTest(label), self.assertRaises((ValueError, TypeError)):
                make()

    def test_fallback_keeps_the_content_as_text_entities_and_keyboard(self):
        message = order().build()
        fallback = message.fallback()
        self.assertIsInstance(fallback, FormattedText)
        for text in ('Заказ №42', 'Товар | Цена', '☑ Оплата', '☐ Доставка', 'Длинный комментарий\n— Анна', 'Подробнее', '📎 Чек'):
            self.assertIn(text, fallback.text)
        self.assertFalse(fallback.text.endswith('\n'))
        kinds = {entity.kind for entity in fallback.entities}
        self.assertTrue({'bold', 'text_link', 'expandable_blockquote'} <= kinds)
        payload = fallback.split()[0].as_kwargs()
        self.assertIsNone(payload['parse_mode'])
        self.assertEqual(message.fallback_keyboard(), [[
            {'text': 'Подтвердить', 'callback_data': 'order:confirm:42', 'style': 'success'},
            {'text': 'Отменить', 'callback_data': 'order:cancel:42'}]], "inline keyboards have no 'link' style")
        json.dumps(message.as_input(), ensure_ascii=False)


def nested(levels: int) -> RichMessageBuilder:
    builder = RichMessageBuilder().paragraph('дно')
    for _ in range(levels):
        builder = RichMessageBuilder().details('уровень', builder)
    return builder


def many_documents(count: int) -> RichMessageBuilder:
    builder = RichMessageBuilder()
    for index in range(count):
        builder.document(f'FIXTURE_{index}')
    return builder


if __name__ == '__main__':
    unittest.main()
