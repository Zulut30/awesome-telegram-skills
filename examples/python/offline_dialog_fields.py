"""Actual Dispatcher, seven fields and one file-SQLite effect; no Telegram HTTP."""
import asyncio
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import Update
from telegram_patterns.testing import StubSession
from dialog_fields_bot import Requests, attach_dialog


async def main():
    with tempfile.TemporaryDirectory(prefix='dialog fields fixture ') as temporary:
        database=Path(temporary)/'requests.sqlite'
        service=Requests(database);received=[];lost_receipt=True
        class UnknownRequests:
            async def submit(self,submission):
                nonlocal lost_receipt
                assert isinstance(session.calls[-1],AnswerCallbackQuery),'Business work before ACK'
                received.append(submission)
                result=await service.submit(submission)
                if lost_receipt:
                    lost_receipt=False;raise TimeoutError('Fixture lost receipt after SQLite commit')
                return result
        dispatcher=Dispatcher(events_isolation=SimpleEventIsolation())
        existing=Router()
        @existing.message(Command('help'))
        async def help(message): await message.answer('Existing help preserved',parse_mode=None)
        dispatcher.include_router(existing);attach_dialog(dispatcher,UnknownRequests())
        replies=[];index=0
        def response(method):
            reply={'message_id':1000+len(replies),'date':1,'chat':{'id':method.chat_id,'type':'private'},
                'from':{'id':100,'is_bot':True,'first_name':'Fixture'},'text':method.text}
            replies.append((method,reply));return reply
        session=StubSession().respond(SendMessage,response).respond(AnswerCallbackQuery,True)
        bot=Bot('100:DIALOG_FIXTURE',session=session,default=DefaultBotProperties(parse_mode='HTML'))
        state=dispatcher.fsm.get_context(bot=bot,chat_id=42,user_id=42)
        async def send(text=None,*,reply=True,actor=42,**media):
            nonlocal index
            index+=1
            message={'message_id':index,'date':1,'chat':{'id':42,'type':'private'},
                'from':{'id':actor,'is_bot':False,'first_name':'Owner'},**media}
            if text is not None:message['text']=text
            if reply and replies:message['reply_to_message']=replies[-1][1]
            await dispatcher.feed_update(bot,Update.model_validate({'update_id':index,'message':message}))
        def button():
            method,message=replies[-1]
            return message,method.reply_markup.inline_keyboard[0][0].callback_data
        async def click(chosen=None,*,actor=42):
            nonlocal index
            index+=1;message,data=chosen or button()
            await dispatcher.feed_update(bot,Update.model_validate({'update_id':index,'callback_query':{'id':str(index),
                'from':{'id':actor,'is_bot':False,'first_name':'Owner'},'chat_instance':'fixture','message':message,'data':data}}))
        async def data():return (await state.get_data())['__telegram_patterns_dialog']
        try:
            await state.update_data(host='preserved')
            await send('/collect');question=replies[-1][1]
            await send('1',reply=False);assert (await data())['index']==0
            await send('/collect');current=replies[-1]
            replies.append((current[0],question));await send('1');assert (await data())['index']==0
            replies.append(current);await send('1',actor=99);assert (await data())['index']==0
            await send('1');await send('invalid');assert (await data())['index']==1
            await send('Case@EXAMPLE.COM');await send('+48 (123) 456-789');await send('2026-10-06')
            await send(document={'file_id':'opaque','file_unique_id':'unique','file_name':'report.pdf','file_size':128,'mime_type':'application/pdf'})
            assert (await data())['index']==5
            contact={'phone_number':'+48123456789','first_name':'Owner','user_id':42}
            await send(contact=contact|{'user_id':99});assert (await data())['candidate'] is None
            await send(contact=contact);assert (await data())['index']==5
            candidate=button();await click(candidate,actor=99);assert (await data())['index']==5
            await send(contact=contact|{'phone_number':'+48111111111'});fresh=button()
            await click(candidate);assert (await data())['index']==5
            await click(fresh);assert (await data())['index']==6
            await send(location={'latitude':52.2,'longitude':21.0});assert (await data())['index']==6
            await click();assert (await data())['index']==7
            stale=button();key=(await data())['operation_id']
            await send('/back');assert (await data())['index']==6 and 'location' not in (await data())['values']
            assert (await data())['operation_id']!=key
            await click(stale);assert not received
            await send(location={'latitude':52.3,'longitude':21.1});await click();review=button()
            try:await click(review)
            except TimeoutError:pass
            else:raise AssertionError('Unknown host receipt was swallowed')
            pending=await data();assert pending['submission_started']
            for text in ('/back','/cancel','/collect'):await send(text)
            assert await data()==pending
            await click(review);await click(review)
            assert len(received)==2 and received[0].operation_id==received[1].operation_id
            with closing(sqlite3.connect(database)) as connection:rows=connection.execute('SELECT actor,body FROM requests').fetchall()
            assert len(rows)==1 and rows[0][0]==42
            values=json.loads(rows[0][1]);assert values['email']=='Case@example.com' and values['location']['latitude']==52.3
            assert values['amount']=='1' and values['phone']=='+48123456789' and values['date']=='2026-10-06'
            assert values['file']['file_id']=='opaque' and values['contact']['user_id']==42
            assert await state.get_state() is None and await state.get_data()=={'host':'preserved'}
            await send('/help');assert replies[-1][0].text=='Existing help preserved'
            await send('/collect');await send('/cancel')
            assert await state.get_state() is None and await state.get_data()=={'host':'preserved'}
            assert all(method.parse_mode is None for method,_ in replies)
        finally:
            await dispatcher.fsm.close();await bot.session.close()
    print(json.dumps({'passed':True,'network':False,'session_closed':session.closed,'business_effects':len(rows),
        'field_types':7,'owner_step_guards':True,'native_candidate_confirmation':True,'back_cancel':True,
        'unknown_receipt_same_intent':True,'existing_dispatcher_preserved':True,'host_data_preserved':True}))


if __name__=='__main__':asyncio.run(main())
