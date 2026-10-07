import json
import random
import unittest

from telegram_patterns import (
    FormattedText,
    MessageBuilder,
    TextEntity,
    escape_html,
    escape_markdown_v2,
    split_formatted,
    utf16_length,
)


def covered(value):
    """Independent UTF-16 unit coverage oracle for formatting after partition/rebase."""
    result = {}
    for entity in value.entities:
        key = (entity.kind, entity.url, entity.language, entity.custom_emoji_id)
        for unit in range(entity.offset, entity.offset + entity.length):
            result.setdefault(unit, set()).add(key)
    return result


class MessageTextTests(unittest.TestCase):
    def test_html_literal_and_quotes(self):
        self.assertEqual(escape_html('<b>"A&B"</b>\'&amp;'), '&lt;b&gt;&quot;A&amp;B&quot;&lt;/b&gt;&#x27;&amp;amp;')
        self.assertEqual(escape_html('😀 текст\n'), '😀 текст\n')

    def test_markdown_all_reserved_and_backslash(self):
        literal = '\\_*[]()~`>#+-=|{}.!'
        self.assertEqual(escape_markdown_v2(literal), ''.join('\\' + c for c in literal))
        self.assertEqual(escape_markdown_v2('name 😀\n'), 'name 😀\n')

    def test_markdown_contexts_do_not_escape_like_text(self):
        self.assertEqual(escape_markdown_v2('a_*`\\', context='code'), 'a_*\\`\\\\')
        self.assertEqual(
            escape_markdown_v2('https://example.com/(x)\\', context='link'), 'https://example.com/(x\\)\\\\'
        )
        for context in ('html', None, []):
            with self.assertRaises(ValueError):
                escape_markdown_v2('x', context=context)

    def test_utf16_scalar_length_and_invalid_text(self):
        self.assertEqual(utf16_length('A😀e\u0301'), 5)
        self.assertEqual(utf16_length('👨‍👩‍👧‍👦'), 11)
        for value in ('\ud800', '\udc00', '\x00', '\x01', 'x' * 262145, '😀' * 131073):
            with self.subTest(value=repr(value[:12])), self.assertRaises(ValueError):
                utf16_length(value)
        for value in (None, True, 123, b'bytes'):
            with self.assertRaises(TypeError):
                escape_html(value)

    def test_builder_shifts_by_units_and_preserves_raw_literals(self):
        base = MessageBuilder().text('😀 ')
        built = base.style('<b>untrusted_*</b>', 'bold').text(' done').build()
        self.assertEqual(base.build().text, '😀 ')
        self.assertEqual(built.entities[0].offset, 3)
        self.assertEqual(built.text, '😀 <b>untrusted_*</b> done')
        self.assertEqual(built.as_kwargs()['parse_mode'], None)

    def test_deep_snapshot_entities_and_payload(self):
        supplied = [TextEntity('bold', 0, 2)]
        value = FormattedText('ok', supplied)
        supplied.clear()
        self.assertEqual(len(value.entities), 1)
        first = value.as_kwargs()
        first['entities'][0]['offset'] = 999
        first['entities'].clear()
        self.assertEqual(value.as_kwargs()['entities'], [{'type': 'bold', 'offset': 0, 'length': 2}])
        with self.assertRaises((AttributeError, TypeError)):
            value.entities[0].offset = 5

    def test_reject_surrogate_middle_and_out_of_bounds(self):
        for entity in (TextEntity('bold', 0, 1), TextEntity('bold', 1, 1), TextEntity('bold', 0, 4)):
            with self.assertRaises(ValueError):
                FormattedText('😀x', (entity,))
        self.assertEqual(FormattedText('😀x', (TextEntity('bold', 0, 2),)).entities[0].length, 2)

    def test_invalid_descriptors_and_wrong_metadata(self):
        bad = [
            ('bold', True, 1),
            ('bold', 0, True),
            ('bold', -1, 1),
            ('bold', 0, 0),
            ('bold', 262144, 1),
            ('html', 0, 1),
        ]
        for args in bad:
            with self.subTest(args=args), self.assertRaises(ValueError):
                TextEntity(*args)
        for kwargs in ({'url': 'https://example.com'}, {'language': 'python'}, {'custom_emoji_id': '123'}):
            with self.assertRaises(ValueError):
                TextEntity('bold', 0, 1, **kwargs)
        with self.assertRaises(TypeError):
            FormattedText('x', ('bold',))

    def test_http_links_checked_without_network_or_url_sanitization(self):
        valid = 'https://example.com/a?x=%22&b=(x)'
        entity = TextEntity('text_link', 0, 4, url=valid)
        self.assertEqual(entity.as_dict()['url'], valid)
        for url in (
            None,
            'javascript:alert(1)',
            'tg://user?id=42',
            '//example.com',
            'https://',
            'https://u:p@example.com',
            'https://example.com:bad',
            'https://example.com:0',
            'https://a\n.example.com',
            'https://example.com\\x',
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                TextEntity('text_link', 0, 1, url=url)

    def test_code_language_and_non_overlap(self):
        self.assertEqual(TextEntity('pre', 0, 2, language='c++').as_dict()['language'], 'c++')
        for language in ('', 'python\n', 'a' * 65):
            with self.assertRaises(ValueError):
                TextEntity('pre', 0, 2, language=language)
        for entities in (
            (TextEntity('pre', 0, 4), TextEntity('bold', 1, 2)),
            (TextEntity('bold', 0, 4), TextEntity('code', 1, 2)),
        ):
            with self.assertRaises(ValueError):
                FormattedText('text', entities)

    def test_crossing_duplicate_and_non_style_nesting(self):
        bad = [
            (TextEntity('bold', 0, 3), TextEntity('italic', 2, 2)),
            (TextEntity('bold', 0, 4), TextEntity('bold', 0, 4)),
            (TextEntity('blockquote', 0, 4), TextEntity('expandable_blockquote', 1, 2)),
            (
                TextEntity('text_link', 0, 4, url='https://example.com'),
                TextEntity('custom_emoji', 1, 2, custom_emoji_id='123'),
            ),
        ]
        for entities in bad:
            with self.subTest(entities=entities), self.assertRaises(ValueError):
                FormattedText('abcd', entities)

    def test_valid_nested_styles_and_same_ranges(self):
        entities = (
            TextEntity('bold', 0, 4),
            TextEntity('italic', 0, 4),
            TextEntity('text_link', 1, 2, url='https://example.com'),
        )
        self.assertEqual(len(FormattedText('text', entities).entities), 3)

    def test_custom_emoji_fallback_default_and_explicit_capability(self):
        value = MessageBuilder().text('Done ').custom_emoji('👍🏽', '123456789').build()
        self.assertEqual(value.as_kwargs()['entities'], [])
        native = value.as_kwargs(custom_emoji_entitlement_verified=True)
        self.assertEqual(
            native['entities'][0], {'type': 'custom_emoji', 'offset': 5, 'length': 4, 'custom_emoji_id': '123456789'}
        )
        self.assertEqual(native['text'], 'Done 👍🏽')
        for identifier in ('', '0', '-1', '123a', '1' * 33, True):
            with self.assertRaises(ValueError):
                MessageBuilder().custom_emoji('👍', identifier)
        with self.assertRaises(ValueError):
            MessageBuilder().custom_emoji('x' * 33, '123')
        with self.assertRaises(TypeError):
            value.as_kwargs(custom_emoji_entitlement_verified=1)

    def test_message_and_caption_limits_and_empty(self):
        self.assertEqual(FormattedText('x' * 4096).as_kwargs()['text'], 'x' * 4096)
        self.assertEqual(FormattedText('😀' * 512).as_kwargs(limit=1024)['text'], '😀' * 512)
        for value, limit in (
            (FormattedText('x' * 4097), 4096),
            (FormattedText('x' * 1025), 1024),
            (FormattedText(''), 4096),
        ):
            with self.assertRaises(ValueError):
                value.as_kwargs(limit=limit)
        with self.assertRaises(ValueError):
            FormattedText(' \n').as_kwargs()
        self.assertEqual(FormattedText('').split(), ())
        for limit in (0, 4097, True, 1.0):
            with self.assertRaises(ValueError):
                FormattedText('x').split(limit=limit)

    def test_long_styled_partition_keeps_exact_coverage(self):
        value = FormattedText('😀abc' * 1500, (TextEntity('bold', 0, 7500), TextEntity('italic', 3, 7497)))
        chunks = value.split()
        self.assertEqual(''.join(c.text for c in chunks), value.text)
        after = {}
        shift = 0
        for chunk in chunks:
            self.assertLessEqual(utf16_length(chunk.text), 4096)
            after.update({unit + shift: styles for unit, styles in covered(chunk).items()})
            shift += utf16_length(chunk.text)
        self.assertEqual(covered(value), after)

    def test_pre_partition_preserves_language(self):
        value = MessageBuilder().style('print(1)\n' * 700, 'pre', language='python').build()
        chunks = split_formatted(value, limit=1024)
        self.assertEqual(''.join(c.text for c in chunks), value.text)
        self.assertTrue(
            all(c.entities[0].language == 'python' and c.entities[0].length == utf16_length(c.text) for c in chunks)
        )

    def test_atomic_link_and_custom_emoji_move_whole(self):
        value = (
            MessageBuilder()
            .text('1234567')
            .style('LINK', 'text_link', url='https://example.com')
            .custom_emoji('👨‍👩‍👧‍👦', '123')
            .build()
        )
        chunks = value.split(limit=12)
        self.assertEqual([c.text for c in chunks], ['1234567LINK', '👨‍👩‍👧‍👦'])
        self.assertEqual(chunks[1].entities[0].offset, 0)
        self.assertEqual(chunks[1].entities[0].length, 11)
        with self.assertRaises(ValueError):
            value.split(limit=10)

    def test_atomic_quotes_and_overlarge_fail_without_loss(self):
        value = MessageBuilder().text('abc').style('quoted', 'expandable_blockquote').text('xyz').build()
        self.assertEqual([c.text for c in value.split(limit=8)], ['abc', 'quotedxy', 'z'])
        with self.assertRaises(ValueError):
            value.split(limit=5)
        with self.assertRaises(ValueError):
            MessageBuilder().style('x' * 4097, 'text_link', url='https://example.com').build().split()

    def test_common_unicode_sequences_not_cut(self):
        sequences = ['e\u0301', '👨‍👩‍👧‍👦', '👍🏽', '🇵🇱', '1\ufe0f\u20e3', '🏴\U000e0067\U000e0062\U000e007f']
        # CRLF is never cut; alone it would be an unsendable whitespace-only part.
        self.assertEqual([p.text for p in FormattedText('a\r\nb').split(limit=3)], ['a\r\n', 'b'])
        with self.assertRaises(ValueError):
            FormattedText('a\r\nb').split(limit=2)
        for sequence in sequences:
            with self.subTest(sequence=sequence):
                limit = utf16_length(sequence)
                parts = FormattedText('a' + sequence + 'b').split(limit=limit)
                self.assertEqual([p.text for p in parts], ['a', sequence, 'b'])
                if limit > 1:
                    with self.assertRaises(ValueError):
                        FormattedText(sequence).split(limit=limit - 1)

    def test_scalar_never_split_and_unsplittable_error(self):
        self.assertEqual([c.text for c in FormattedText('a😀b').split(limit=2)], ['a', '😀', 'b'])
        with self.assertRaises(ValueError):
            FormattedText('😀').split(limit=1)
        with self.assertRaises(ValueError):
            FormattedText('a' + '\u0301' * 4096).split()
        with self.assertRaises(ValueError):
            FormattedText('x' * 257).split(limit=1)

    def test_entity_count_bound_never_silently_drops(self):
        entities = tuple(TextEntity('bold', i, 1) for i in range(101))
        value = FormattedText('x' * 101, entities)
        with self.assertRaises(ValueError):
            value.as_kwargs()
        with self.assertRaises(ValueError):
            value.split()
        self.assertEqual(len(value.split(limit=50)), 3)
        with self.assertRaises(ValueError):
            FormattedText('x' * 513, tuple(TextEntity('bold', i, 1) for i in range(513)))

    def test_seeded_partition_oracle_over_styles_and_unicode(self):
        rng = random.Random(26005)
        for case in range(150):
            text = ''.join(
                rng.choice(('a', '😀', 'e\u0301', '👍🏽', '🇵🇱', '👨‍👩‍👧‍👦')) for _ in range(rng.randint(1, 60))
            )
            length = utf16_length(text)
            value = FormattedText(text, (TextEntity('bold', 0, length), TextEntity('spoiler', 0, length)))
            chunks = value.split(limit=rng.randint(12, 40))
            self.assertEqual(''.join(c.text for c in chunks), text, case)
            after = {}
            shift = 0
            for chunk in chunks:
                json.dumps(chunk.as_kwargs(), ensure_ascii=False).encode('utf-8')
                after.update({unit + shift: styles for unit, styles in covered(chunk).items()})
                shift += utf16_length(chunk.text)
            self.assertEqual(covered(value), after, case)

    def test_clipped_nested_same_style_is_deduplicated(self):
        for entities in (
            (TextEntity('bold', 0, 10), TextEntity('bold', 0, 5)),
            (TextEntity('bold', 0, 10), TextEntity('bold', 5, 5)),
        ):
            value = FormattedText('a' * 10, entities)
            chunks = value.split(limit=5)
            self.assertEqual([c.text for c in chunks], ['a' * 5, 'a' * 5])
            self.assertTrue(all(c.entities == (TextEntity('bold', 0, 5),) for c in chunks))

    def test_breaks_prefer_newline_then_space_and_never_send_whitespace_only(self):
        self.assertEqual([c.text for c in FormattedText('hello world foo').split(limit=8)], ['hello ', 'world ', 'foo'])
        self.assertEqual([c.text for c in FormattedText('ab\ncd ef gh').split(limit=8)], ['ab\ncd ', 'ef gh'])
        self.assertEqual(
            [c.text for c in FormattedText('line one\nline two').split(limit=12)], ['line one\n', 'line two']
        )
        parts = FormattedText('x' * 4096 + '\n').split()
        self.assertEqual([utf16_length(p.text) for p in parts], [4095, 2])
        self.assertTrue(all(p.as_kwargs() for p in parts))
        self.assertEqual([p.text for p in FormattedText('\n' + 'x' * 4096).split()], ['\n' + 'x' * 4095, 'x'])
        self.assertEqual([utf16_length(p.text) for p in FormattedText('x' + ' ' * 5000 + 'y').split()], [4096, 906])
        for impossible in (' ' * 5000 + 'x', 'x' + ' ' * 5000, 'x' + ' ' * 9000 + 'y'):
            with self.subTest(size=len(impossible)), self.assertRaises(ValueError):
                FormattedText(impossible).split()
        # A whitespace part next to an atomic link moves into a neighbour without cutting the link.
        value = MessageBuilder().text('abc  ').style('LINK', 'text_link', url='https://example.com').build()
        self.assertEqual([c.text for c in value.split(limit=5)], ['abc  ', 'LINK'])
        value = MessageBuilder().text('abcd  ').style('LINKS', 'text_link', url='https://example.com').build()
        self.assertEqual([c.text for c in value.split(limit=5)], ['abc', 'd  ', 'LINKS'])

    def test_ten_thousand_random_compositions_split_into_sendable_lossless_parts(self):
        rng = random.Random(70001)
        alphabet = ('a', 'b', 'Я', '😀', 'e\u0301', '👍🏽', ' ', ' ', '\n', '\t')
        for case in range(10_000):
            limit = rng.randint(8, 48)
            words = []
            while sum(map(len, words)) < rng.randint(1, 180):
                token = ''.join(rng.choice(alphabet[:6]) for _ in range(rng.randint(1, 6)))
                words.append(token + rng.choice((' ', '\n', ' \n', '  ', '')))
            text = ''.join(words)
            size = utf16_length(text)
            entities = []
            for _ in range(rng.randint(0, 6)):
                offset = rng.randint(0, max(0, size - 1))
                length = rng.randint(1, size - offset)
                candidate = TextEntity(rng.choice(('bold', 'italic', 'spoiler', 'bold')), offset, length)
                try:
                    FormattedText(text, tuple(entities + [candidate]))
                except ValueError:
                    continue
                entities.append(candidate)
            value = FormattedText(text, tuple(entities))
            chunks = value.split(limit=limit)
            self.assertEqual(''.join(c.text for c in chunks), text, case)
            after = {}
            shift = 0
            for chunk in chunks:
                self.assertLessEqual(utf16_length(chunk.text), limit, case)
                chunk.as_kwargs(limit=limit)  # sendable: content, size and entity bounds
                after.update({unit + shift: styles for unit, styles in covered(chunk).items()})
                shift += utf16_length(chunk.text)
            self.assertEqual(covered(value), after, case)

    def test_failed_append_preserves_original_builder(self):
        original = MessageBuilder().text('original')
        with self.assertRaises(ValueError):
            original.style('bad', 'pre', language='invalid language')
        self.assertEqual(original.build().text, 'original')
        with self.assertRaises(TypeError):
            original.append('raw')


if __name__ == '__main__':
    unittest.main()
