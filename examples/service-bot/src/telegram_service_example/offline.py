"""Closed synthetic Dispatcher phases; each phase runs as a separate process."""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import sys

from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from telegram_patterns import PermissionDenied
from telegram_patterns.testing import StubSession
from .bot import Application
from .service import Actor
from .storage import connection

BASE = datetime(2026,10,6,9,tzinfo=timezone.utc)
OWNER = User(id=42,is_bot=False,first_name='Fixture')
BOT_USER = User(id=100,is_bot=True,first_name='Fixture',username='service_fixture_bot')


def guards() -> list[int]:
    attempts=[0]
    def audit(event,args):
        if event not in {'socket.connect','socket.getaddrinfo'}:return
        host=args[1][0] if event=='socket.connect' and isinstance(args[1],tuple) else args[0] if event=='socket.getaddrinfo' else None
        if host in {'localhost','127.0.0.1','::1',None}:return
        try:
            if ipaddress.ip_address(host).is_loopback:return
        except ValueError:pass
        attempts[0]+=1;raise RuntimeError('External network forbidden in service fixture')
    sys.addaudithook(audit)
    from aiogram.client.session.aiohttp import AiohttpSession
    async def deny(*args,**kwargs):
        attempts[0]+=1;raise RuntimeError('Real Telegram HTTP forbidden')
    AiohttpSession.make_request=deny  # type: ignore[method-assign]  # Test-only transport refusal.
    return attempts


async def phase(database: Path, name: str) -> dict:
    attempts=guards()
    now=BASE.timestamp() + (2800 if name in {'reminder','crash-reminder','recover-reminder'} else 0)
    app=Application(database,100,now=lambda:now)
    session=StubSession()
    sent: list[tuple[SendMessage,Message]]=[]
    def response(method):
        reply=Message(message_id=20000+len(sent),date=BASE,chat=Chat(id=method.chat_id,type='private'),from_user=BOT_USER,text=method.text)
        sent.append((method,reply));return reply
    session.respond(SendMessage,response).respond(AnswerCallbackQuery,True)
    async with Bot('100:SERVICE_OFFLINE_FIXTURE',session=session) as bot:
        async def message(text: str, index: int, *, chat_id: int=42, user: User=OWNER, business: str | None=None):
            await app.dispatcher.feed_update(bot,Update(update_id=index,message=Message(message_id=index,date=BASE,
                chat=Chat(id=chat_id,type='private' if chat_id>0 else 'supergroup'),from_user=user,text=text,business_connection_id=business)))
        async def stored():
            state=app.dispatcher.fsm.get_context(bot=bot,chat_id=42,user_id=42)
            return state,(await state.get_data())['__telegram_patterns_form']
        async def confirm(index: int, user: User=OWNER):
            state,data=await stored()
            reply=Message(message_id=data['review_message_id'],date=BASE,chat=Chat(id=42,type='private'),from_user=BOT_USER)
            callback=f"form:booking:{data['operation_id']}:submit"
            await app.dispatcher.feed_update(bot,Update(update_id=index,callback_query=CallbackQuery(
                id=str(index),from_user=user,chat_instance='fixture',message=reply,data=callback)))
        try:
            checks=[]
            if name=='start':
                # Group and Business updates never open a private service form.
                await message('/book',1,chat_id=-100);await message('/book',2,business='fixture-business')
                assert not session.calls
                await message('/start',3);await message('/slots',4);await message('/reminders_on',5)
                await message('/book',6);await message('slot-1',7)
                state,data=await stored();assert data['index']==1 and data['values']=={'slot':'slot-1'}
                assert data['owner']==[100,42,42] and not data['submission_started']
                checks=['private-menu','group-business-refused','slot-selected','dialog-persisted']
            elif name=='review':
                state,data=await stored();assert data['index']==1
                await message('<b>Учебная консультация</b>',100)
                state,data=await stored();assert data['index']==2 and data['review_message_id'] is not None
                assert '<b>Учебная консультация</b>' in sent[0][0].text and sent[0][0].parse_mode is None
                await confirm(101,User(id=77,is_bot=False,first_name='Foreign'))
                assert not app.service.bookings(Actor(100,42,42))
                assert isinstance(session.calls[-2],AnswerCallbackQuery)
                checks=['dialog-resumed','plain-input','foreign-confirmation-refused','callback-ack']
            elif name=='crash-submit':
                original=app.service.once.run
                def crash_booking(*args,**kwargs):
                    result=original(*args,**kwargs)
                    assert isinstance(session.calls[-1],AnswerCallbackQuery) and attempts[0]==0
                    print(json.dumps({'phase':name,'committed':True,'ack_before_commit':True,'booking_id':result.value['id'],
                                      'external_network_attempts':attempts[0],'telegram_requests':False}),flush=True)
                    os._exit(73)
                app.service.once.run=crash_booking  # type: ignore[method-assign]  # Crash after actual commit.
                await confirm(200)
                raise AssertionError('Expected abrupt process exit')
            elif name=='recover':
                state,data=await stored();key=data['operation_id'];assert data['submission_started']
                for i,text in enumerate(('/book','/back','/cancel'),300):await message(text,i)
                state,data=await stored();assert data['operation_id']==key and data['submission_started']
                existing=app.service.bookings(Actor(100,42,42));assert len(existing)==1
                try:app.service.booking(Actor(100,77,77),existing[0]['id'])
                except PermissionDenied:pass
                else:raise AssertionError('Foreign object read allowed')
                await message('/cancel_booking '+str(existing[0]['id']),304,user=User(id=77,is_bot=False,first_name='Foreign'),chat_id=77)
                assert app.service.bookings(Actor(100,42,42))[0]['status']=='booked'
                await confirm(305)
                assert await state.get_state() is None and await state.get_data()=={}
                with connection(database) as db:
                    assert db.execute('SELECT count(*) FROM service_bookings').fetchone()[0]==1
                    assert db.execute('SELECT count(*) FROM service_notifications').fetchone()[0]==1
                    assert db.execute('SELECT count(*) FROM telegram_pattern_operations').fetchone()[0]==1
                await message('/status',306)
                checks=['unknown-dialog-preserved','owner-acl','same-operation-replayed','one-booking','one-reminder-intent','dialog-cleared-after-result','status-menu']
            elif name in {'reminder','crash-reminder'}:
                if name=='crash-reminder':
                    def crash_notification(job,status,message_id=None,delay=0):
                        assert status=='sent'
                        assert attempts[0]==0
                        print(json.dumps({'phase':name,'stub_transport_effect':True,'message_id':message_id,
                                          'external_network_attempts':attempts[0],'telegram_requests':False}),flush=True)
                        os._exit(74)
                    app.service.finish=crash_notification  # type: ignore[method-assign]  # Crash before receipt storage.
                result=await app.service.deliver_one(bot)
                assert result=='sent'
                assert await app.service.deliver_one(bot)=='idle'
                assert len([c for c in session.calls if isinstance(c,SendMessage)])==1
                checks=['reminder-restored','one-stub-delivery','sent-not-repeated']
            elif name=='recover-reminder':
                with connection(database) as db:
                    row=db.execute('SELECT status,attempts FROM service_notifications').fetchone()
                    assert tuple(row)==('unknown',1)
                assert app.recovered_notifications==1 and await app.service.deliver_one(bot)=='idle'
                assert not session.calls
                checks=['crashed-send-became-unknown','unknown-not-auto-resent']
            else:raise ValueError('Unknown phase')
            assert attempts[0]==0
        finally:await app.close()
    assert session.closed and app.storage.closed and app.lock.file.closed
    return {'passed':True,'phase':name,'checks':checks,'session_closed':True,'fsm_closed':True,'lock_released':True,
            'external_network_attempts':attempts[0],'telegram_requests':False}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--phase',choices=['start','review','crash-submit','recover','reminder','crash-reminder','recover-reminder'],required=True)
    args=parser.parse_args()
    print(json.dumps(asyncio.run(phase(args.database,args.phase))))


if __name__=='__main__':
    if not __debug__:raise SystemExit('Offline verification needs assertions enabled')
    main()
