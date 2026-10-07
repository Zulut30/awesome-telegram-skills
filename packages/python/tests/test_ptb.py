import asyncio
import importlib.util
import unittest

from telegram_patterns import (ValidationFailure, force_reply_markup, inline_button, inline_markup, remove_markup, reply_button,
                               reply_markup)

HAS_PTB = importlib.util.find_spec('telegram') is not None


@unittest.skipUnless(HAS_PTB, 'python-telegram-bot is not installed (extra "ptb")')
class PTBAdapterTests(unittest.TestCase):
    def test_markup_json_round_trips_through_ptb_objects(self):
        from telegram import ForceReply, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
        from telegram_patterns.ptb import ptb_markup
        cases = [(inline_markup([[inline_button('Готово', callback_data='ok', style='success'), inline_button('Нет', disabled=True)],
                                 [inline_button('Код', copy_text='READY'), inline_button('Сайт', url='https://example.com')]]), InlineKeyboardMarkup),
                 (reply_markup([[reply_button('Контакт', request_contact=True)], ['Помощь']], one_time=True, placeholder='Выберите'), ReplyKeyboardMarkup),
                 (remove_markup(), ReplyKeyboardRemove), (force_reply_markup('Имя'), ForceReply)]
        for markup, kind in cases:
            converted = ptb_markup(markup)
            self.assertIsInstance(converted, kind)
            self.assertEqual(converted.to_dict(), markup, 'fields unknown to PTB, like disabled, are kept')
        from telegram_patterns.ptb import ptb_inline_markup
        self.assertIsInstance(ptb_inline_markup(cases[0][0]), InlineKeyboardMarkup)
        with self.assertRaises(ValidationFailure):
            ptb_inline_markup(remove_markup())
        for broken in ({}, {'inline_keyboard': [], 'keyboard': []}, {'inline_keyboard': []}):
            with self.assertRaises(ValidationFailure):
                ptb_markup(broken)

    def test_application_runs_offline_and_records_wire_parameters(self):
        from telegram import Update
        from telegram.error import BadRequest, NetworkError
        from telegram.ext import CallbackQueryHandler, CommandHandler
        from telegram_patterns.ptb import offline_application, ptb_markup
        menu = ptb_markup(inline_markup([[inline_button('Каталог', callback_data='menu:catalog')]]))

        async def scenario():
            app, stub = offline_application()
            stub.respond('sendMessage', lambda p: {'message_id': 9, 'date': 1, 'chat': {'id': p['chat_id'], 'type': 'private'}, 'text': p['text']})
            stub.respond('answerCallbackQuery', True)
            seen = []

            async def start(update, context):
                await update.effective_message.reply_text('Меню', reply_markup=menu)

            async def pressed(update, context):
                seen.append(update.callback_query.data)
                await update.callback_query.answer()
            app.add_handler(CommandHandler('start', start))
            app.add_handler(CallbackQueryHandler(pressed, pattern='^menu:'))
            await app.initialize()
            user = {'id': 7, 'is_bot': False, 'first_name': 'A'}
            await app.process_update(Update.de_json({'update_id': 1, 'message': {
                'message_id': 1, 'date': 1, 'chat': {'id': 7, 'type': 'private'}, 'from': user, 'text': '/start',
                'entities': [{'type': 'bot_command', 'offset': 0, 'length': 6}]}}, app.bot))
            await app.process_update(Update.de_json({'update_id': 2, 'callback_query': {
                'id': 'q1', 'from': user, 'chat_instance': 'c', 'data': 'menu:catalog',
                'message': {'message_id': 9, 'date': 1, 'chat': {'id': 7, 'type': 'private'}, 'text': 'Меню'}}}, app.bot))
            with self.assertRaises(NetworkError):
                await app.bot.get_chat(7)  # nothing registered: no silent fallback to the network
            stub.fail('sendMessage', 'Bad Request: chat not found')
            with self.assertRaises(BadRequest):
                await app.bot.send_message(7, 'x')
            await app.shutdown()
            return stub, seen
        stub, seen = asyncio.run(scenario())
        self.assertEqual(stub.calls[0], ('sendMessage', {'chat_id': 7, 'text': 'Меню', 'reply_markup': {
            'inline_keyboard': [[{'text': 'Каталог', 'callback_data': 'menu:catalog'}]]}}))
        self.assertEqual((stub.calls[1][0], seen), ('answerCallbackQuery', ['menu:catalog']))
        self.assertTrue(stub.closed)


if __name__ == '__main__':
    unittest.main()
