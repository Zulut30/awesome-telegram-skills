"""Seven real SDK/Dispatcher compositions with host SQLite, without Telegram HTTP."""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile

from aiogram import Bot, Dispatcher, F, Router, methods as m
from aiogram.types import BufferedInputFile, ReactionTypeEmoji, Update
from telegram_patterns.aiogram import (PlatformAction, PlatformPermit, PlatformScope, StoryPhotoUpload,
    platform_contracts, managed_bot_link)
from telegram_patterns.testing import StubSession
from platform_bot import PlatformJournal, platform_router


async def main():
    with tempfile.TemporaryDirectory(prefix='platform-composition-') as temporary:
        db=sqlite3.connect(Path(temporary)/'host.sqlite3')
        async def policy(action):
            # Artificial host facts. Live adapters must verify current message,
            # gift/child ownership, recent chat activity and actual media content.
            return PlatformPermit(allowed=True,business_chat_eligible=True,join_request_active=True,
                join_received_at=datetime.now(timezone.utc),financial_authorized=True,star_cost=20,max_stars=20,
                managed_bot_bound=True,story_media_verified=True)
        journal=PlatformJournal(db,policy)
        db.execute('INSERT INTO platform_actors VALUES (100,42,0,1)')
        db.execute('INSERT INTO platform_budgets VALUES (100,42,1000)')
        db.execute('CREATE TABLE observed (bot_id INTEGER,update_id INTEGER,PRIMARY KEY(bot_id,update_id))');db.commit()
        bot_user={'id':100,'is_bot':True,'first_name':'Bot','username':'fixture_bot','supports_join_request_queries':True,'can_manage_bots':True,'has_topics_enabled':True}
        user={'id':42,'is_bot':False,'first_name':'User'}
        gift_types={'unlimited_gifts':True,'limited_gifts':True,'unique_gifts':True,'premium_subscription':True,'gifts_from_channels':True}
        def chat(request):return {'id':request.chat_id,'type':'private' if request.chat_id>0 else 'supergroup','title':'Fixture group',
            'is_forum':request.chat_id<0,'accent_color_id':0,'max_reaction_count':1,'accepted_gift_types':gift_types}
        sticker={'file_id':'f','file_unique_id':'u','type':'custom_emoji','width':512,'height':512,'is_animated':False,'is_video':False}
        gift={'id':'gift-a','sticker':sticker,'star_count':20}
        session=StubSession().respond(m.GetMe,bot_user).respond(m.GetChat,chat).respond(m.GetChatMember,{'status':'creator','user':bot_user,'is_anonymous':False})
        session.respond(m.GetBusinessConnection,{'id':'business-a','user':user,'user_chat_id':42,'date':1780000000,'is_enabled':True,
            'rights':{'can_read_messages':True,'can_manage_stories':True}})
        session.respond(m.GetAvailableGifts,{'gifts':[gift]})
        session.respond(m.CreateForumTopic,{'message_thread_id':17,'name':'Topic','icon_color':7322096})
        session.respond(m.SetMessageReaction,True).respond(m.AnswerChatJoinRequestQuery,True).respond(m.ReadBusinessMessage,True)
        session.respond(m.PostStory,{'id':1,'chat':{'id':42,'type':'private'}}).respond(m.SendGift,True).respond(m.SetManagedBotAccessSettings,True)
        replies=[];results=[];observations=[];helped=[]
        def reply(request):
            replies.append(request.text)
            return {'message_id':1000+len(replies),'date':1780000000,'chat':{'id':request.chat_id,'type':'private'},'text':request.text}
        session.respond(m.SendMessage,reply)
        bot=Bot('100:PLATFORM_OFFLINE_FIXTURE',session=session)
        async def resolve(message):
            command=(message.text or '').split()[0].removeprefix('/')
            fields={};request=None
            if command=='topic':fields={'chat_id':-100};request=m.CreateForumTopic(chat_id=-100,name='Topic')
            elif command=='reaction':fields={'chat_id':-100,'message_id':10};request=m.SetMessageReaction(chat_id=-100,message_id=10,reaction=[ReactionTypeEmoji(emoji='👍')])
            elif command=='join':fields={'chat_id':-100,'subject_user_id':42,'join_query_id':'query-a'};request=m.AnswerChatJoinRequestQuery(chat_join_request_query_id='query-a',result='queue')
            elif command=='business':fields={'chat_id':77,'message_id':10,'business_connection_id':'business-a','owner_id':42};request=m.ReadBusinessMessage(business_connection_id='business-a',chat_id=77,message_id=10)
            elif command=='story':
                fields={'business_connection_id':'business-a','owner_id':42}
                request=m.PostStory(business_connection_id='business-a',content=StoryPhotoUpload(photo=BufferedInputFile(b'NOT_REAL_MEDIA','story.jpg')),active_period=21600,caption='<b>literal</b>',parse_mode=None)
            elif command=='gift':fields={'subject_user_id':42};request=m.SendGift(gift_id='gift-a',user_id=42,text='Literal',text_parse_mode=None)
            elif command=='managed':fields={'child_bot_id':500,'owner_id':42};request=m.SetManagedBotAccessSettings(user_id=500,is_access_restricted=True,added_user_ids=[42])
            return None if request is None else PlatformAction(PlatformScope(bot.id,message.from_user.id,f'command-{message.message_id}',**fields),request)
        async def lookup(event):
            row=db.execute('SELECT enabled FROM platform_actors WHERE bot_id=? AND actor_id=?',(bot.id,42)).fetchone()
            if row!=(1,) or event.chat_id not in (None,-100,42,77):return None
            return PlatformScope(bot.id,42,f'event-{event.update_id}',chat_id=event.chat_id,message_thread_id=event.message_thread_id,
                message_id=event.message_id,business_connection_id=event.business_connection_id,owner_id=event.owner_id or (42 if event.business_connection_id else None),
                child_bot_id=event.child_bot_id,join_query_id=event.join_query_id)
        async def observe(event,scope):
            with db:
                result=db.execute('INSERT OR IGNORE INTO observed VALUES (?,?)',(bot.id,event.update_id))
                if result.rowcount:observations.append(event.kind)
        async def on_result(action,result):results.append(action.contract.family)
        dispatcher=Dispatcher();dispatcher.include_router(platform_router(resolve,journal,lookup,observe,on_result))
        host=Router()
        async def help(message):helped.append(message.text)
        host.message.register(help,F.text=='/help');dispatcher.include_router(host)
        def incoming(number,text):return Update.model_validate({'update_id':number,'message':{'message_id':number,'date':1780000000,
            'chat':{'id':42,'type':'private'},'from':user,'text':text}})
        try:
            for index,command in enumerate(('topic','reaction','join','business','story','gift','managed'),1):
                await dispatcher.feed_update(bot,incoming(index,'/'+command))
            assert set(results)=={'topics','reactions','join','business','stories','gifts','managed'} and len(results)==7
            assert db.execute("SELECT COUNT(*) FROM platform_intents WHERE status='succeeded'").fetchone()==(7,)
            await dispatcher.feed_update(bot,incoming(1,'/topic'))
            assert len([r for r in session.calls if isinstance(r,m.CreateForumTopic)])==1
            def lost(request):raise OSError('SYNTHETIC LOST ANSWER')
            session.respond(m.CreateForumTopic,lost)
            await dispatcher.feed_update(bot,incoming(20,'/topic'));await dispatcher.feed_update(bot,incoming(20,'/topic'))
            assert db.execute("SELECT status FROM platform_intents WHERE operation_id='command-20'").fetchone()==('unknown',)
            assert len([r for r in session.calls if isinstance(r,m.CreateForumTopic)])==2
            assert db.execute('SELECT remaining FROM platform_budgets').fetchone()==(980,)
            values=[{'message_reaction_count':{'chat':{'id':-100,'type':'supergroup'},'message_id':10,'date':1780000000,'reactions':[]}},
                {'chat_join_request':{'chat':{'id':-100,'type':'supergroup'},'from':user,'user_chat_id':42,'date':1780000000,'query_id':'query-a'}},
                {'business_connection':{'id':'business-a','user':user,'user_chat_id':42,'date':1780000000,'is_enabled':False}},
                {'managed_bot':{'user':user,'bot_user':{'id':500,'is_bot':True,'first_name':'Child'}}}]
            for number,value in enumerate(values,100):
                update=Update.model_validate({'update_id':number,**value});await dispatcher.feed_update(bot,update);await dispatcher.feed_update(bot,update)
            assert len(observations)==4 and db.execute('SELECT COUNT(*) FROM observed').fetchone()==(4,)
            db.execute('UPDATE platform_actors SET enabled=0');db.commit()
            before=len(session.calls);await dispatcher.feed_update(bot,incoming(21,'/gift'))
            assert not any(isinstance(r,m.SendGift) for r in session.calls[before:])
            await dispatcher.feed_update(bot,incoming(22,'/help'));assert helped==['/help']
            link=managed_bot_link('ManagerBot','ExampleBot',name='Example & Bot');assert '%26' in link
        finally:
            await dispatcher.fsm.close();await bot.session.close();db.close()
        print(json.dumps({'passed':True,'network':False,'session_closed':session.closed,'families':7,
            'confirmed_operations':7,'durable_intents':True,'unknown_send_no_retry':True,'current_actor_acl':True,
            'fresh_native_rights':True,'financial_quote_budget':True,'scoped_event_dedup':True,
            'existing_dispatcher_preserved':True,'user_confirmed_managed_link':True,
            'contracts':len(platform_contracts()),'limits':'SDK/mock SQLite author evidence; no live permissions/media/Stars/owner/device proof'}))


if __name__=='__main__':asyncio.run(main())
