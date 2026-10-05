"""Owner/version/history in one bot message; explicit recovery after unknown edit."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import User
from telegram_patterns.aiogram import (
    ActionButton, MessageNavigation, NavigationResult, NavigationScreen,
    NavigationState, navigation_router,
)
from telegram_patterns.testing import StubSession
from bot_fixture import TOKEN, callback, response


async def main() -> None:
    session = StubSession().respond(AnswerCallbackQuery, True).respond(SendMessage, response).respond(EditMessageText, response)
    dispatcher = Dispatcher()
    menu = MessageNavigation([
        NavigationScreen('home', 'Главная', [ActionButton('Каталог', 'catalog')]),
        NavigationScreen('catalog', 'Каталог'),
    ])
    results: list[NavigationResult] = []
    async def result(query, feedback: NavigationResult) -> None:
        results.append(feedback)
    dispatcher.include_router(navigation_router(menu, on_result=result))
    async with Bot(TOKEN, session=session) as bot:
        try:
            initial: NavigationState = await menu.open(bot, 42, 42)
            reply = response(SendMessage(chat_id=42, text='Главная'))
            def key(target: str) -> str:
                state = menu.get_state(bot.id, 42, 42)
                assert state is not None
                return f'{menu.prefix}{state.session_id}:{state.revision}:{target}'
            old = key('catalog')
            await dispatcher.feed_update(bot, callback(old, reply, index=1, actor=User(id=43, is_bot=False, first_name='Other')))
            assert results[-1].status == 'denied' and results[-1].state is None
            await dispatcher.feed_update(bot, callback(old, reply, index=2))
            assert results[-1].state is not None
            assert results[-1].state.history == ('home',)
            await dispatcher.feed_update(bot, callback(key('_back'), reply, index=3))
            assert results[-1].state is not None
            assert results[-1].state.screen == 'home'
            await dispatcher.feed_update(bot, callback(old, reply, index=4))
            assert results[-1].status == 'stale'
            def lost(request): raise TimeoutError('PRIVATE_FIXTURE')
            session.respond(EditMessageText, lost)
            await dispatcher.feed_update(bot, callback(key('catalog'), reply, index=5))
            assert results[-1].status == 'unknown'
            session.respond(EditMessageText, response)
            recovered = await menu.open(bot, 42, 42)
            assert (recovered.message_id, recovered.screen, recovered.phase) == (initial.message_id, 'home', 'ready')
            assert len([c for c in session.calls if isinstance(c, SendMessage)]) == 1
            assert await menu.discard(bot.id, 42, 42)
        finally:
            await dispatcher.fsm.close()
    assert session.closed
    print(json.dumps({'passed': True, 'case': 'bot_navigation', 'network': False}))


if __name__ == '__main__': asyncio.run(main())
