"""SDK UI over a server-owned draft; effect hook is application-owned."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, EditMessageText
from telegram_patterns import SelectionContext, SelectionMenu, SelectionOption, SelectionResult, SelectionSpec
from telegram_patterns.aiogram import selection_keyboard, selection_router
from telegram_patterns.testing import StubSession
from bot_fixture import TOKEN, callback, response


async def main() -> None:
    menu = SelectionMenu(SelectionSpec([SelectionOption('a','Alpha'),SelectionOption('b','Beta')],
        toggles={'notify':'Уведомлять'},min_selected=1), SelectionContext(100,42,42,100))
    initial = selection_keyboard(menu.state)
    assert len(initial.inline_keyboard[0]) == 2
    results: list[SelectionResult] = []
    intents: list[str] = []
    async def feedback(query, result: SelectionResult) -> None:
        results.append(result)
        if result.status == 'confirmed':
            assert result.state is not None and result.state.operation_id is not None
            intents.append(result.state.operation_id)  # Local fixture, no dangerous business effect.
    dispatcher = Dispatcher()
    dispatcher.include_router(selection_router(menu,on_result=feedback))
    session = StubSession().respond(AnswerCallbackQuery,True).respond(EditMessageText,response)
    async with Bot(TOKEN,session=session) as bot:
        try:
            reply = response(EditMessageText(text='Fixture',chat_id=42,message_id=100))
            for index,action in enumerate(('s:a','t:notify','q:inc','ask'),start=1):
                await dispatcher.feed_update(bot,callback(menu.state.callback(action),reply,index=index))
            state=menu.state
            assert state.confirmation_id is not None
            data=state.callback('y:'+state.confirmation_id)
            await dispatcher.feed_update(bot,callback(data,reply,index=5))
            await dispatcher.feed_update(bot,callback(data,reply,index=6))
            assert results[-2].status=='confirmed' and results[-1].status=='stale' and len(intents)==1
            assert len([m for m in session.calls if isinstance(m,EditMessageText)])==5
            assert selection_keyboard(menu.state).inline_keyboard==[]
        finally:
            await dispatcher.fsm.close()
    assert session.closed
    print(json.dumps({'passed':True,'case':'bot_selection','network':False,'business_effects':0}))


if __name__=='__main__':
    asyncio.run(main())
