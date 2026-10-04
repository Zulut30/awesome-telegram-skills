"""MemoryStorage fixture: ввод, проверка, review и защита от чужой кнопки."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import User
from telegram_patterns.aiogram import FormSubmission, InvalidField, TextField, text_form_router
from telegram_patterns.testing import StubSession
from bot_fixture import TOKEN, callback, message, response

async def main() -> None:
    replies = []
    def respond(request):
        result = response(request); replies.append((request, result)); return result
    submissions: list[FormSubmission] = []
    def validate(value: str) -> str:
        if value.lower() not in {'python', 'typescript'}: raise InvalidField('Выберите Python или TypeScript.')
        return value.lower()
    field = TextField('topic', 'Тема', 'Python или TypeScript?', validate=validate)
    assert field.read(' Python ') == 'python'
    async def submit(value: FormSubmission) -> str:
        assert value.actor_id == value.chat_id == 42 and value.bot_id == 100
        submissions.append(value); return 'Fixture проверена; заявка не сохранялась.'
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    dispatcher.include_router(text_form_router([field], submit, name='reference'))
    session = StubSession().respond(SendMessage, respond).respond(AnswerCallbackQuery, True)
    async with Bot(TOKEN, session=session) as bot:
        try:
            for index, text in enumerate(('/apply', 'wrong', 'Python'), 1):
                await dispatcher.feed_update(bot, message(text, index=index))
            request, reply = replies[-1]
            data = request.reply_markup.inline_keyboard[0][0].callback_data
            outsider = User(id=43, is_bot=False, first_name='Other')
            await dispatcher.feed_update(bot, callback(data, reply, index=4, actor=outsider))
            assert not submissions
            await dispatcher.feed_update(bot, callback(data, reply, index=5))
            await dispatcher.feed_update(bot, callback(data, reply, index=6))
            assert len(submissions) == 1 and submissions[0].values['topic'] == 'python'
        finally: await dispatcher.fsm.close()
    assert session.closed
    print(json.dumps({'passed': True, 'case': 'bot_form', 'network': False}))

if __name__ == '__main__': asyncio.run(main())
