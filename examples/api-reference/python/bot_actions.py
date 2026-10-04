"""Тот же Dispatcher: команды и callback ACK до owner-bound сервиса."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, GetMe, SendMessage
from telegram_patterns.aiogram import Action, ActionResult, callback_router, start_router, CommandReply, command_menu, command_router
from telegram_patterns.testing import Responder, StubSession
from bot_fixture import BOT_USER, TOKEN, callback, message, response

async def main() -> None:
    responder: Responder = response
    session = StubSession().respond(GetMe, BOT_USER).respond(SendMessage, responder).respond(AnswerCallbackQuery, True)
    dispatcher = Dispatcher()
    replies = [CommandReply('help', 'Справка', 'Публичная справка')]
    assert command_menu(replies)[0].command == 'help'
    async def execute(action: Action) -> ActionResult:
        assert isinstance(session.calls[-1], AnswerCallbackQuery)  # Spinner ACK уже отправлен.
        return ActionResult('accepted' if action.actor_id == 42 and action.key == 'catalog' else 'denied', 'Публичный ответ')
    async def notify(query, result: ActionResult) -> None:
        assert query.message is not None
        await query.message.answer(result.text, parse_mode=None)
    dispatcher.include_router(start_router('Публичное начало'))
    dispatcher.include_router(command_router(replies))
    dispatcher.include_router(callback_router(execute, notify))
    async with Bot(TOKEN, session=session) as bot:
        try:
            await dispatcher.feed_update(bot, message('/start'))
            await dispatcher.feed_update(bot, message('/help', index=2))
            reply = response(SendMessage(chat_id=42, text='Меню'))
            await dispatcher.feed_update(bot, callback('act:catalog', reply, index=3))
            assert [type(c).__name__ for c in session.calls][-2:] == ['AnswerCallbackQuery', 'SendMessage']
        finally: await dispatcher.fsm.close()
    assert session.closed
    stream = session.stream_content('https://fixture.invalid')
    try: await anext(stream)
    except AssertionError: pass
    else: raise AssertionError('File streaming should have no fallback')
    finally: await stream.aclose()
    print(json.dumps({'passed': True, 'case': 'bot_actions', 'network': False}))

if __name__ == '__main__': asyncio.run(main())
