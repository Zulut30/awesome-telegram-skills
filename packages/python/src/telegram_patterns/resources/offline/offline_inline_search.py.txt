"""Actual Dispatcher composition with synthetic transport, never Telegram HTTP."""
import asyncio
import json
from aiogram import Bot, Dispatcher, F, Router
from aiogram.methods import AnswerInlineQuery
from aiogram.types import Update
from telegram_patterns.aiogram import InlineItem
from telegram_patterns.testing import StubSession
from inline_search_bot import inline_search_router


async def main():
    items = [InlineItem('a', 'Заметка A', 'Можно отправить A', shareable=True),
             InlineItem('private', 'Личная заметка', 'PRIVATE_PAYLOAD'),
             InlineItem('b', 'Заметка B', 'Можно отправить B', shareable=True),
             InlineItem('c', 'Заметка C', 'Можно отправить C', shareable=True)]
    owners = {'a':42, 'b':42, 'c':43}; revoked = set(); feedback = []; loaded = []
    async def catalog(actor): loaded.append(actor); return 'catalog-v1', items
    async def authorize(actor,item): return owners.get(item.id) == actor and actor not in revoked
    async def revision(actor): return 'revoked' if actor in revoked else 'active'
    async def chosen(result): feedback.append(result.result_id)
    session = StubSession().respond(AnswerInlineQuery,True)
    bot = Bot('100:INLINE_COMPOSITION_FIXTURE',session=session); dispatcher = Dispatcher()
    helped = []; host = Router()
    async def help(message): helped.append(message.text)
    host.message.register(help,F.text=='/help')
    dispatcher.include_router(inline_search_router(catalog,authorize,revision,cursor_secret=b'host-persistent-secret-32bytes-long',page_size=1,feedback=chosen))
    dispatcher.include_router(host)
    def incoming(number,actor=42,offset='',text=''):
        return Update.model_validate({'update_id':number,'inline_query':{'id':str(number),
            'from':{'id':actor,'is_bot':False,'first_name':'User'},'query':text,'offset':offset,'chat_type':'private'}})
    try:
        await dispatcher.feed_update(bot,incoming(1))
        first=session.calls[-1]; assert [item.id for item in first.results]==['a']
        assert first.is_personal is True and first.cache_time==0 and len(first.next_offset.encode())<=64
        assert not feedback  # A valid answer does not require chosen feedback.
        await dispatcher.feed_update(bot,incoming(2,offset=first.next_offset))
        assert [item.id for item in session.calls[-1].results]==['b'] and session.calls[-1].next_offset==''
        await dispatcher.feed_update(bot,incoming(3,actor=43,offset=first.next_offset))
        assert session.calls[-1].results==[]  # Never restart another actor's cursor.
        await dispatcher.feed_update(bot,incoming(4,actor=43))
        assert [item.id for item in session.calls[-1].results]==['c']
        await dispatcher.feed_update(bot,incoming(5,text='PRIVATE_PAYLOAD'))
        assert session.calls[-1].results==[]
        revoked.add(42); await dispatcher.feed_update(bot,incoming(6))
        assert session.calls[-1].results==[]
        await dispatcher.feed_update(bot,Update.model_validate({'update_id':7,'chosen_inline_result':{
            'result_id':'c','from':{'id':43,'is_bot':False,'first_name':'User'},'query':''}}))
        assert feedback==['c'] and len(session.calls)==6
        def lost(request): raise TimeoutError('DO_NOT_LOG_PRIVATE_PAYLOAD')
        session.respond(AnswerInlineQuery,lost); count=len(session.calls)
        try: await dispatcher.feed_update(bot,incoming(8,actor=43))
        except TimeoutError: pass
        else: raise AssertionError('Unknown native confirmation must propagate to host')
        assert len(session.calls)==count+1 and not session.closed
        await dispatcher.feed_update(bot,Update.model_validate({'update_id':9,'message':{
            'message_id':9,'date':1780000000,'chat':{'id':42,'type':'private'},'text':'/help'}}))
        assert helped==['/help'] and loaded==[42,42,43,43,42,42,43]
    finally:
        await dispatcher.fsm.close(); await bot.session.close()
    print(json.dumps({'passed':True,'network':False,'session_closed':session.closed,
        'personal_cache':True,'scoped_pagination':True,'fresh_acl':True,'private_items_excluded':True,
        'unknown_answer_no_retry':True,'existing_dispatcher_preserved':True,'feedback_is_optional':True}))


if __name__=='__main__': asyncio.run(main())
