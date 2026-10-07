"""Actual host Dispatcher plus SDK serialization of sendRichMessage and its text fallback; HTTP is disabled."""
import asyncio
from datetime import datetime, timezone
import json

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.methods import AnswerCallbackQuery, SendMessage, SendRichMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from telegram_patterns import RichButton, RichMessageBuilder
from telegram_patterns.testing import StubSession
from rich_message_bot import attach_order_cards, order_card

RECEIPT = 'FIXTURE_RECEIPT_FILE_ID'


async def main():
    session = StubSession()
    bot = Bot('100:RICH_MESSAGE_FIXTURE', session=session, default=DefaultBotProperties(parse_mode='HTML'))
    dispatcher = Dispatcher()
    help_router, helped = Router(name='existing-help'), []

    @help_router.message(Command('help'))
    async def help_handler(message: Message): helped.append(message.text)
    dispatcher.include_router(help_router)
    rich_chats = {42}
    attach_order_cards(dispatcher, receipt_file_id=RECEIPT, rich_supported=lambda message: message.chat.id in rich_chats)
    rich, plain, answers = [], [], []

    def sent_rich(method):
        rich.append(json.loads(session.prepare_value(method.rich_message, bot=bot, files={})))
        return {'message_id': 100 + len(rich), 'date': 1, 'chat': {'id': method.chat_id, 'type': 'private'}}

    def sent_plain(method):
        assert method.parse_mode is None and session.prepare_value(method.parse_mode, bot=bot, files={}) is None
        markup = method.reply_markup
        plain.append({'text': method.text, 'entities': [entity.type for entity in method.entities or []],
                      'keyboard': None if markup is None else json.loads(session.prepare_value(markup, bot=bot, files={}))})
        return {'message_id': 200 + len(plain), 'date': 1, 'chat': {'id': method.chat_id, 'type': 'private'}, 'text': method.text}

    session.respond(SendRichMessage, sent_rich).respond(SendMessage, sent_plain)
    session.respond(AnswerCallbackQuery, lambda method: answers.append(method.text) or True)
    actor = User(id=7, is_bot=False, first_name='Анна')

    def incoming(chat_id, text, index):
        return Update(update_id=index, message=Message(message_id=index, date=datetime(2026, 10, 7, tzinfo=timezone.utc),
                                                        chat=Chat(id=chat_id, type='private'), from_user=actor, text=text))
    try:
        expected = order_card(42, [('Книга', 1, '500 ₽'), ('Ручка', 2, '100 ₽')], '700 ₽', RECEIPT)
        await dispatcher.feed_update(bot, incoming(42, '/order', 1))
        # aiogram fills the host default parse_mode into the document object; Telegram ignores a rich document's caption.
        assert len(rich) == 1 and rich[0]['blocks'][6]['document'].pop('parse_mode') == 'HTML'
        assert rich == [expected.as_input()], 'otherwise the SDK sends exactly the JSON the builder produced'
        blocks = rich[0]['blocks']
        types = [block['type'] for block in blocks]
        assert types == ['heading', 'paragraph', 'table', 'list', 'expandable_blockquote', 'details', 'document', 'buttons']
        assert blocks[2]['is_compact'] and blocks[6]['document']['media'] == RECEIPT and len(blocks[7]['buttons']) == 2

        await dispatcher.feed_update(bot, incoming(43, '/order', 2))
        assert len(rich) == 1 and plain, 'a chat without rich messages gets the text fallback'
        text = ''.join(part['text'] for part in plain)
        assert all(line in text for line in ('Заказ №42', 'Книга | 1 | 500 ₽', '☑ Оплата получена', 'Как проходит доставка', '📎 Чек'))
        assert {'bold', 'text_link', 'expandable_blockquote'} <= {kind for part in plain for kind in part['entities']}
        keyboard = plain[-1]['keyboard']['inline_keyboard'][0]
        assert [button['callback_data'] for button in keyboard] == ['order:confirm:42', 'order:cancel:42']
        assert 'style' not in keyboard[1], "an inline keyboard has no 'link' style"

        query = CallbackQuery(id='q1', from_user=actor, chat_instance='ci', data='order:confirm:42',
                              message=Message(message_id=101, date=datetime(2026, 10, 7, tzinfo=timezone.utc), chat=Chat(id=42, type='private')))
        await dispatcher.feed_update(bot, Update(update_id=3, callback_query=query))
        assert answers == ['Запрос принят']
        await dispatcher.feed_update(bot, incoming(42, '/help', 4))
        assert helped == ['/help']

        limits = 0
        for build in (lambda: RichMessageBuilder().bullets(['x'] * 250).build(),
                      lambda: RichMessageBuilder().table([['x'] * 21]),
                      lambda: RichMessageBuilder().buttons([RichButton(str(i), callback_data=str(i)) for i in range(9)])):
            try:
                build()
            except ValueError:
                limits += 1
        assert limits == 3
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed': True, 'network': False, 'session_closed': session.closed, 'blocks': expected.block_count,
                      'sdk_wire_matches_builder': True, 'compact_table': True, 'collapsible_quote': True, 'details_block': True,
                      'document_block': True, 'button_row': True, 'fallback_text_and_keyboard': True, 'limits_enforced': True,
                      'callback_acknowledged': True, 'existing_dispatcher_preserved': bool(helped)}))


if __name__ == '__main__':
    asyncio.run(main())
