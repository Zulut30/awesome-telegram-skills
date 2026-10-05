"""Actual own-poll composition with temporary durable host SQLite and SDK transport."""
import asyncio
import json
from pathlib import Path
import sqlite3
import tempfile
from aiogram import Bot, Dispatcher, F, Router
from aiogram.methods import GetMe, SendMessage, SendPoll
from aiogram.types import Poll, Update
from telegram_patterns.aiogram import PollBinding, PollOptionAddition, PollState, PollVote
from telegram_patterns.testing import StubSession
from polls_bot import polls_router


async def main():
    with tempfile.TemporaryDirectory(prefix='own-polls-fixture-') as temporary:
        database=Path(temporary)/'host.sqlite3'; connection=sqlite3.connect(database)
        connection.executescript('CREATE TABLE intents (key TEXT PRIMARY KEY, request TEXT, status TEXT);'
            'CREATE TABLE polls (poll_id TEXT PRIMARY KEY, binding TEXT); CREATE TABLE receipts (bot_id INTEGER, update_id INTEGER, PRIMARY KEY(bot_id,update_id));')
        revoked=set(); observations=[]; replies=[]; sent_responses=[]; send_count=0
        def key(message): return json.dumps([message.bot.id,message.chat.id,message.message_thread_id,message.business_connection_id,message.message_id])
        async def authorize(actor,chat,operation): return actor==42 and chat==42 and actor not in revoked
        async def claim(message,request):
            with connection:
                # Resolve SDK Default sentinels using the host Bot before storing
                # this synthetic, file-free request; model_dump_json cannot do it.
                payload=message.bot.session.prepare_value(request.model_dump(warnings=False),message.bot,{})
                result=connection.execute('INSERT OR IGNORE INTO intents VALUES (?, ?, ?)',(key(message),payload,'pending'))
                return result.rowcount==1
        async def confirm(message,binding):
            data={field:getattr(binding,field) for field in ('bot_id','poll_id','chat_id','message_id','is_anonymous','kind','message_thread_id','business_connection_id')}
            with connection:
                connection.execute('INSERT INTO polls VALUES (?,?)',(binding.poll_id,json.dumps(data)))
                connection.execute("UPDATE intents SET status='confirmed' WHERE key=?",(key(message),))
        async def unknown(message):
            with connection: connection.execute("UPDATE intents SET status='unknown' WHERE key=?",(key(message),))
        async def lookup(locator):
            if revoked: return None  # Fresh host policy can revoke observation.
            rows=connection.execute('SELECT binding FROM polls').fetchall()
            for (raw,) in rows:
                binding=PollBinding(**json.loads(raw))
                if binding.bot_id != locator.bot_id: continue
                if locator.poll_id is not None and binding.poll_id != locator.poll_id: continue
                if locator.chat_id is not None and (binding.chat_id,binding.message_id)!=(locator.chat_id,locator.message_id): continue
                return binding
            return None
        async def observe(event):
            with connection:
                accepted=connection.execute('INSERT OR IGNORE INTO receipts VALUES (?,?)',(event.binding.bot_id,event.update_id))
                if accepted.rowcount: observations.append(event.observation)
        session=StubSession().respond(GetMe,{'id':100,'is_bot':True,'first_name':'Bot','username':'poll_fixture_bot'})
        def sent(request):
            nonlocal send_count
            send_count+=1
            response={'message_id':10+send_count,'date':1780000000,'from':{'id':100,'is_bot':True,'first_name':'Bot'},
                'chat':{'id':request.chat_id,'type':'private'},'poll':{'id':f'poll-{send_count}','question':request.question,
                    'options':[{'text':choice.text,'voter_count':0,'persistent_id':f'stable-{index}'} for index,choice in enumerate(request.options)],
                    'total_voter_count':0,'is_closed':False,'is_anonymous':request.is_anonymous,'type':request.type,
                    'allows_multiple_answers':request.allows_multiple_answers,'allows_revoting':request.allows_revoting if request.allows_revoting is not None else request.type!='quiz',
                    'members_only':False,'correct_option_ids':request.correct_option_ids}}
            sent_responses.append(response)
            return response
        def reply(request):
            replies.append(request.text)
            return {'message_id':1000+len(replies),'date':1780000000,'chat':{'id':request.chat_id,'type':'private'},'text':request.text}
        session.respond(SendPoll,sent).respond(SendMessage,reply)
        bot=Bot('100:POLL_COMPOSITION_FIXTURE',session=session); dispatcher=Dispatcher(); helped=[]
        host=Router()
        async def help(message): helped.append(message.text)
        host.message.register(help,F.text=='/help')
        dispatcher.include_router(polls_router(authorize,claim,confirm,unknown,lookup,observe)); dispatcher.include_router(host)
        def incoming(number,text,actor=42):
            return Update.model_validate({'update_id':number,'message':{'message_id':number,'date':1780000000,
                'chat':{'id':actor,'type':'private'},'from':{'id':actor,'is_bot':False,'first_name':'User'},'text':text}})
        try:
            await dispatcher.feed_update(bot,incoming(1,'/poll')); await dispatcher.feed_update(bot,incoming(1,'/poll'))
            assert send_count==1 and 'уже принят' in replies[-1]
            await dispatcher.feed_update(bot,incoming(2,'/quiz'))
            quizzes=[call for call in session.calls if isinstance(call,SendPoll) and call.type=='quiz']
            assert quizzes[0].correct_option_ids==[0,2] and quizzes[0].allows_multiple_answers
            answer={'poll_id':'poll-1','option_ids':[1],'option_persistent_ids':['stable-1'],
                    'user':{'id':42,'is_bot':False,'first_name':'User'}}
            update=Update.model_validate({'update_id':10,'poll_answer':answer})
            await dispatcher.feed_update(bot,update); await dispatcher.feed_update(bot,update)
            assert len(observations)==1 and isinstance(observations[-1],PollVote)
            await dispatcher.feed_update(bot,Update.model_validate({'update_id':11,'poll_answer':{**answer,'option_ids':[],'option_persistent_ids':[]}}))
            assert observations[-1].retracted
            await dispatcher.feed_update(bot,Update.model_validate({'update_id':12,'poll_answer':{**answer,'poll_id':'poll-2'}}))
            assert len(observations)==2  # Anonymous quiz does not reveal voters.
            original=json.loads(json.dumps(sent_responses[0]))
            service=incoming(13,'').message.model_copy(update={'poll_option_added':None})
            service_payload=service.model_dump(mode='json',by_alias=True)
            service_payload['poll_option_added']={'option_persistent_id':'stable-added','option_text':'Позже','poll_message':{
                'chat':{'id':42,'type':'private'},'message_id':11,'date':0}}
            await dispatcher.feed_update(bot,Update.model_validate({'update_id':13,'message':service_payload}))
            assert isinstance(observations[-1],PollOptionAddition) and observations[-1].poll_id is None
            service_payload['poll_option_added']['poll_message']=None
            count=len(observations); await dispatcher.feed_update(bot,Update.model_validate({'update_id':14,'message':service_payload}))
            assert len(observations)==count
            state=original['poll']; state.update(type='regular',is_anonymous=False,is_closed=True,correct_option_ids=None,total_voter_count=1)
            await dispatcher.feed_update(bot,Update(update_id=15,poll=Poll.model_validate(state)))
            assert isinstance(observations[-1],PollState) and observations[-1].is_closed
            revoked.add(42); count=len(observations)
            await dispatcher.feed_update(bot,Update.model_validate({'update_id':16,'poll_answer':answer}))
            assert len(observations)==count
            before=sum(isinstance(call,SendPoll) for call in session.calls)
            await dispatcher.feed_update(bot,incoming(17,'/poll',actor=43))
            assert sum(isinstance(call,SendPoll) for call in session.calls)==before
            revoked.clear()
            def lost(request): raise TimeoutError('DO_NOT_LOG_PRIVATE_PAYLOAD')
            session.respond(SendPoll,lost)
            await dispatcher.feed_update(bot,incoming(18,'/poll')); await dispatcher.feed_update(bot,incoming(18,'/poll'))
            assert sum(isinstance(call,SendPoll) for call in session.calls)==before+1
            assert connection.execute("SELECT status FROM intents WHERE key=?",(json.dumps([100,42,None,None,18]),)).fetchone()==('unknown',)
            assert not any('DO_NOT_LOG_PRIVATE_PAYLOAD' in text for text in replies)
            connection.close(); connection=sqlite3.connect(database)
            await dispatcher.feed_update(bot,incoming(18,'/poll'))
            assert sum(isinstance(call,SendPoll) for call in session.calls)==before+1
            await dispatcher.feed_update(bot,incoming(19,'/help')); assert helped==['/help'] and not session.closed
        finally:
            await dispatcher.fsm.close(); await bot.session.close(); connection.close()
    print(json.dumps({'passed':True,'network':False,'session_closed':session.closed,'modern_quiz':True,
        'own_poll_binding':True,'persistent_vote_ids':True,'anonymous_limits':True,'unknown_addition_not_guessed':True,
        'durable_host_dedup':True,'unknown_send_no_retry':True,'fresh_acl':True,'existing_dispatcher_preserved':True}))


if __name__=='__main__': asyncio.run(main())
