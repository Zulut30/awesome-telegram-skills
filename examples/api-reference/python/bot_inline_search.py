"""All public inline symbols with personal pagination and one native answer."""
import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerInlineQuery
from aiogram.types import InlineQuery, InputTextMessageContent, Update, User
from telegram_patterns.aiogram import (InlineChatType, InlineAuthorizer, InlineSearchProvider, InlineCachePolicy,
                                      InlineItem, InlinePage, InlineSearch, inline_articles, inline_query_router)
from telegram_patterns.testing import StubSession


async def main():
    context: InlineChatType='sender'
    native=InlineQuery(id='q1',from_user=User(id=42,is_bot=False,first_name='Reader'),query='',offset='',chat_type=context)
    catalog=InlineSearch([InlineItem('a','A','Shared A',shareable=True),InlineItem('b','B','Shared B',shareable=True),
                         InlineItem('private','Private','Never sent')],secret=b'host-persistent-reference-secret32',revision='v1',
                        page_size=1,cache=InlineCachePolicy())
    async def allow(actor:int,item:InlineItem)->bool: return actor==42
    authorize: InlineAuthorizer=allow
    async def load(query:InlineQuery)->InlineSearch: return catalog
    provider: InlineSearchProvider=load
    page: InlinePage=await catalog.page(native,bot_id=100,authorize=authorize)
    assert [item.id for item in page.items]==['a'] and len(page.next_offset.encode())<=64
    articles=inline_articles(page)
    content=articles[0].input_message_content
    assert isinstance(content,InputTextMessageContent) and content.parse_mode is None
    following=native.model_copy(update={'id':'q2','offset':page.next_offset})
    assert (await catalog.page(following,bot_id=100,authorize=authorize)).items[0].id=='b'
    session=StubSession().respond(AnswerInlineQuery,True); bot=Bot('100:INLINE_REFERENCE',session=session)
    dispatcher=Dispatcher(); dispatcher.include_router(inline_query_router(provider,authorize=authorize))
    try:
        await dispatcher.feed_update(bot,Update(update_id=1,inline_query=native))
        answer=session.calls[0]
        assert isinstance(answer,AnswerInlineQuery) and answer.is_personal and answer.cache_time==0
    finally:
        await dispatcher.fsm.close(); await bot.session.close()
    print(json.dumps({'case':'bot_inline_search','passed':True,'network':False,'session_closed':session.closed}))


if __name__=='__main__': asyncio.run(main())
