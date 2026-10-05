"""Real Dispatcher/SDK, synthetic transport; no HTTP or destructive operation."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import Update
from telegram_patterns.testing import StubSession
from selection_bot import build_selection_router, demo_spec


async def main() -> None:
    rules = [demo_spec()]
    results = []
    intents = []
    async def feedback(query, result):
        results.append(result)
        if result.status == 'confirmed':
            intents.append(result.state.operation_id)  # Demo receipt, no business effect.
    router, menus = build_selection_router(current_spec=lambda: rules[0], on_result=feedback)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    session = StubSession().respond(AnswerCallbackQuery, True)
    def response(method):
        return {'message_id': 100 if isinstance(method, SendMessage) else method.message_id, 'date': 1,
                'chat': {'id': method.chat_id, 'type': 'private'}, 'from': {'id': 100, 'is_bot': True, 'first_name': 'Fixture'},
                'text': method.text, 'reply_markup': method.reply_markup.model_dump(exclude_none=True) if method.reply_markup else None}
    session.respond(SendMessage, response).respond(EditMessageText, response)
    bot = Bot('100:SELECTION_FIXTURE', session=session, default=DefaultBotProperties(parse_mode='HTML'))
    index = 0
    async def command():
        nonlocal index
        index += 1
        await dispatcher.feed_update(bot, Update.model_validate({'update_id':index, 'message':{'message_id':index,'date':1,
            'chat':{'id':42,'type':'private'},'from':{'id':42,'is_bot':False,'first_name':'Owner'},'text':'/choose'}}))
    async def feed(action=None, *, data=None, actor=42):
        nonlocal index
        index += 1
        payload = data if data is not None else menus[42].state.callback(action)
        await dispatcher.feed_update(bot, Update.model_validate({'update_id':index,'callback_query':{
            'id':str(index),'from':{'id':actor,'is_bot':False,'first_name':'Owner'},'chat_instance':'fixture','data':payload,
            'message':{'message_id':100,'date':1,'chat':{'id':42,'type':'private'},
                       'from':{'id':100,'is_bot':True,'first_name':'Fixture'}}}}))
        return results[-1]
    try:
        await command()
        old = menus[42].state.callback('s:alpha')
        assert (await feed(data=old, actor=43)).status == 'denied'
        assert (await feed(data=old)).status == 'accepted'
        assert (await feed(data=old)).status == 'stale'
        await feed('s:beta'); await feed('t:notify'); await feed('q:inc'); await feed('f:basic')
        assert (await feed('s:beta')).status == 'invalid'
        assert menus[42].state.selected == ('alpha', 'beta')
        await feed('f:all'); await feed('ask')
        pending = menus[42].state
        assert pending.confirmation_id is not None
        stale_confirm = pending.callback('y:' + pending.confirmation_id)
        rules[0] = replace(rules[0], resource_version='2')
        assert (await feed(data=stale_confirm)).status == 'stale'
        assert not intents
        # Reopening explicitly recovers the current draft/rules in the same message.
        await command(); await feed('ask')
        await feed('back'); await feed('ask')
        pending = menus[42].state
        assert pending.confirmation_id is not None
        confirmed = pending.callback('y:' + pending.confirmation_id)
        assert (await feed(data=confirmed)).status == 'confirmed'
        assert (await feed(data=confirmed)).status == 'stale'
        assert len(intents) == 1
        state = menus[42].state
        assert state.quantity == 2 and dict(state.toggles)['notify']
        assert sum(isinstance(m, SendMessage) for m in session.calls) == 1
        assert all(m.message_id == 100 and m.parse_mode is None for m in session.calls if isinstance(m, EditMessageText))
    finally:
        await dispatcher.fsm.close()
        await bot.session.close()
    print(json.dumps({'passed':True, 'network':False,'session_closed':session.closed,'single_message':True,
        'toggle':True,'multiselect':True,'quantity':True,'filters':True,'owner_guard':True,'stale_guard':True,
        'fresh_rules':True,'confirmation_once':True,'confirmation_intents':len(intents),
        'edits':sum(isinstance(m,EditMessageText) for m in session.calls),'business_effects':0}))


if __name__ == '__main__':
    asyncio.run(main())
