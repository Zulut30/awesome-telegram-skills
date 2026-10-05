"""Real SDK Dispatcher, owned menu/history/replay and uncertain edit; no HTTP."""
import asyncio
import json

from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import Update
from telegram_patterns.testing import StubSession
from navigation_bot import build_menu


async def check() -> dict:
    session = StubSession().respond(AnswerCallbackQuery, True)
    dp = Dispatcher()
    menu, router = build_menu()
    dp.include_router(router)
    serial = 0
    def response(method):
        nonlocal serial
        if isinstance(method, SendMessage): serial += 1
        return {'message_id': serial if isinstance(method, SendMessage) else method.message_id,
                'date': 1, 'chat': {'id': method.chat_id, 'type': 'private'},
                'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'},
                'text': method.text, 'reply_markup': method.reply_markup.model_dump(exclude_none=True)}
    session.respond(SendMessage, response).respond(EditMessageText, response)
    bot = Bot('100:NAVIGATION_OFFLINE_FIXTURE', session=session)
    uid = 0

    async def command(text='/menu'):
        nonlocal uid
        uid += 1
        update = Update.model_validate({'update_id': uid, 'message': {'message_id': 99, 'date': 1,
            'chat': {'id': 7, 'type': 'private'}, 'from': {'id': 7, 'is_bot': False, 'first_name': 'Owner'},
            'text': text, 'entities': [{'type': 'bot_command', 'offset': 0, 'length': len(text)}]}}, context={'bot': bot})
        await dp.feed_update(bot, update)

    def data(target):
        state = menu.get_state(100, 7, 7)
        return f'{menu.prefix}{state.session_id}:{state.revision}:{target}'

    async def click(payload, actor=7):
        nonlocal uid
        uid += 1
        state = menu.get_state(100, 7, 7)
        update = Update.model_validate({'update_id': uid, 'callback_query': {'id': str(uid),
            'from': {'id': actor, 'is_bot': False, 'first_name': 'Actor'}, 'chat_instance': 'fixture', 'data': payload,
            'message': {'message_id': state.message_id, 'date': 1, 'chat': {'id': 7, 'type': 'private'},
                        'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'}}}}, context={'bot': bot})
        await dp.feed_update(bot, update)

    try:
        await command('/start')
        initial = menu.get_state(100, 7, 7)
        old = data('catalog')
        await click(old, actor=8)
        assert menu.get_state(100, 7, 7) == initial
        await click(old)
        assert menu.get_state(100, 7, 7).screen == 'catalog'
        await click(data('delivery'))
        assert menu.get_state(100, 7, 7).history == ('home', 'catalog')
        await click(data('_back'))
        assert menu.get_state(100, 7, 7).screen == 'catalog'
        confirmed = menu.get_state(100, 7, 7)
        await click(old)
        assert menu.get_state(100, 7, 7) == confirmed
        def lost(method): raise TimeoutError('FIXTURE_PRIVATE')
        session.respond(EditMessageText, lost)
        await click(data('pickup'))
        assert menu.get_state(100, 7, 7).phase == 'unknown'
        edits_before = len([c for c in session.calls if isinstance(c, EditMessageText)])
        await click(data('pickup'))
        assert len([c for c in session.calls if isinstance(c, EditMessageText)]) == edits_before
        session.respond(EditMessageText, response)
        await command()
        recovered = menu.get_state(100, 7, 7)
        assert (recovered.screen, recovered.history, recovered.phase, recovered.message_id) == ('home', (), 'ready', initial.message_id)
        await click(data('help'))
        assert menu.get_state(100, 7, 7).screen == 'help'
        edits = [c for c in session.calls if isinstance(c, EditMessageText)]
        assert len([c for c in session.calls if isinstance(c, SendMessage)]) == 1
        assert all(c.chat_id == 7 and c.message_id == initial.message_id and c.parse_mode is None for c in edits)
        preview = next(c for c in edits if c.text == 'Каталог услуг').reply_markup.model_dump(exclude_none=True)
        return {'passed': True, 'network': False, 'owner_guard': True, 'stale_guard': True, 'history_back': True,
                'unknown_edit_recovery': True, 'single_message': True, 'edits': len(edits), 'preview': preview}
    finally:
        await dp.fsm.close()
        await bot.session.close()
        assert session.closed


async def main() -> None:
    result = await check()
    result['session_closed'] = True
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': asyncio.run(main())
