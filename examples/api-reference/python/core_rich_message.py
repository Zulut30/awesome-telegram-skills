"""SDK-free rich message blocks and their text fallback; no network and no Telegram rendering proof."""
import json
from telegram_patterns import (FormattedText, RichButton, RichButtonStyle, RichMessage, RichMessageBuilder, RichSpan,
                               RichText)

style: RichButtonStyle = 'success'
status: RichText = ['Статус: ', RichSpan('bold', 'оплачен')]
details = RichMessageBuilder().paragraph('Возврат в течение 14 дней.')
message: RichMessage = (RichMessageBuilder().heading('Заказ №42', size=1).paragraph(status)
                        .table([['Товар', 'Цена'], ['Книга', '500 ₽']], compact=True)
                        .checklist([('Оплата', True), ('Доставка', False)])
                        .quote('Длинный комментарий', expandable=True).details('Подробнее', details)
                        .document('FIXTURE_FILE_ID', caption='Чек')
                        .buttons([RichButton('Подтвердить', callback_data='order:confirm:42', style=style)]).build())
payload = message.as_input()  # rich_message для sendRichMessage; SDK модели проверяют ее перед отправкой
assert [block['type'] for block in payload['blocks']][:3] == ['heading', 'paragraph', 'table']
assert payload['blocks'][2]['is_compact'] is True and message.media_count == 1
fallback: FormattedText = message.fallback()  # тот же текст для sendMessage, где rich-сообщение недоступно
assert 'Товар | Цена' in fallback.text and fallback.split()[0].as_kwargs()['parse_mode'] is None
assert message.fallback_keyboard()[0][0]['callback_data'] == 'order:confirm:42'
try:
    RichMessageBuilder().table([['x'] * 21])
except ValueError:
    pass
else:
    raise AssertionError('Telegram allows at most 20 table columns')
print(json.dumps({'case': 'core_rich_message', 'passed': True, 'network': False, 'blocks': message.block_count}))
