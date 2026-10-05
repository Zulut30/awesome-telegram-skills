"""Real SDK Dispatcher + file SQLite; no HTTP. Installed fixture acceptance."""
from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import Update
from telegram_patterns import SQLiteSlotStore, TimeSlot, resolve_local_time
from telegram_patterns.testing import StubSession
from calendar_bot import build_calendar_router


async def main() -> None:
    now = datetime(2026, 10, 5, 8, tzinfo=timezone.utc)
    start = resolve_local_time(datetime(2026, 10, 6, 10), 'Europe/Warsaw')
    with tempfile.TemporaryDirectory(prefix='calendar fixture ') as temporary:
        database = Path(temporary) / 'bookings.sqlite3'
        store = SQLiteSlotStore(database, authorize=lambda c, actor, resource: actor in (42,43) and resource == 'room')
        store.initialize()
        original = [TimeSlot('morning',start,start+timedelta(minutes=30)),
                    TimeSlot('later',start+timedelta(hours=1),start+timedelta(hours=1,minutes=30)),
                    TimeSlot('blocked',start+timedelta(days=1),start+timedelta(days=1,minutes=30),False)]
        store.publish('room',original,expected_revision=0)
        results = []
        async def feedback(query,result): results.append(result)
        router, sessions = build_calendar_router(store,'room',time_zone='Europe/Warsaw',clock=lambda: now,on_result=feedback)
        existing=Router()
        @existing.message(Command('help'))
        async def help(message): await message.answer('Calendar help preserved',parse_mode=None)
        dispatcher=Dispatcher(); dispatcher.include_router(existing); dispatcher.include_router(router)
        def response(method):
            return {'message_id':100 if isinstance(method,SendMessage) else method.message_id,'date':1,
                    'chat':{'id':method.chat_id,'type':'private'},'from':{'id':100,'is_bot':True,'first_name':'Fixture'},
                    'text':method.text,'reply_markup':method.reply_markup.model_dump(exclude_none=True) if method.reply_markup else None}
        session=StubSession().respond(SendMessage,response).respond(EditMessageText,response).respond(AnswerCallbackQuery,True)
        bot=Bot('100:CALENDAR_FIXTURE',session=session,default=DefaultBotProperties(parse_mode='HTML'))
        index=0
        async def command(text='/book'):
            nonlocal index
            index+=1
            await dispatcher.feed_update(bot,Update.model_validate({'update_id':index,'message':{'message_id':index,'date':1,
                'chat':{'id':42,'type':'private'},'from':{'id':42,'is_bot':False,'first_name':'Owner'},'text':text}}))
        async def click(action=None, *, data=None, actor=42):
            nonlocal index
            index+=1
            payload=data if data is not None else sessions[42].menu.state.callback(action)
            await dispatcher.feed_update(bot,Update.model_validate({'update_id':index,'callback_query':{'id':str(index),
                'from':{'id':actor,'is_bot':False,'first_name':'Owner'},'chat_instance':'fixture','data':payload,
                'message':{'message_id':100,'date':1,'chat':{'id':42,'type':'private'},'from':{'id':100,'is_bot':True,'first_name':'Fixture'}}}}))
            return results[-1]
        try:
            await command()
            old=sessions[42].menu.state.callback('s:d20261006')
            assert (await click(data=old,actor=43)).status=='denied'
            assert (await click('s:d20261007')).status=='invalid'
            await click('f:prev'); assert sessions[42].month==9
            await click('f:next'); assert sessions[42].month==10
            assert (await click(data=old)).status=='stale'
            await click('s:d20261006')
            assert sessions[42].selected_date is not None and sessions[42].selected_date.isoformat()=='2026-10-06'
            await click('f:dates'); assert sessions[42].selected_date is None
            await click('s:d20261006'); await click('s:morning')
            assert sessions[42].menu.state.phase=='confirming'
            await click('back'); assert sessions[42].menu.state.selected==()
            await click('s:later')
            pending=sessions[42].menu.state
            assert pending.confirmation_id is not None
            obsolete=pending.callback('y:'+pending.confirmation_id)
            store.publish('room',original,expected_revision=1)
            assert (await click(data=obsolete)).status=='stale'
            assert sessions[42].receipt is None
            await command()
            assert sessions[42].menu.state.selected==('later',)
            await click('ask')
            pending=sessions[42].menu.state
            assert pending.confirmation_id is not None
            confirmation=pending.callback('y:'+pending.confirmation_id)
            async def lost(method): raise TimeoutError('fixture edit response lost')
            session.respond(EditMessageText,lost)
            try: await click(data=confirmation)
            except TimeoutError: pass
            else: raise AssertionError('Lost edit after commit was swallowed')
            receipt=sessions[42].receipt
            assert receipt is not None
            assert (await click(data=confirmation)).status=='stale'
            session.respond(EditMessageText,response)
            await command()
            assert sessions[42].receipt==receipt and sessions[42].menu.state.phase=='confirmed'
            assert receipt['booking_id'] in session.calls[-1].text
            # Reopen the storage object as after a process restart, preserving receipt.
            restarted=SQLiteSlotStore(database,authorize=lambda c,actor,resource: actor==42 and resource=='room')
            replay=restarted.reserve('room','later',actor_id=42,expected_revision=2,
                operation_id=sessions[42].request['operation_id'],now=now+timedelta(days=5))
            assert replay.replayed and replay.value==receipt
            assert restarted.booking('room',receipt['booking_id'],actor_id=42).status=='active'
            with closing(sqlite3.connect(database)) as connection:
                business_effects=connection.execute('SELECT count(*) FROM telegram_slot_bookings').fetchone()[0]
            assert business_effects==1
            session.respond(EditMessageText,lost)
            try: await command('/book new')
            except TimeoutError: pass
            else: raise AssertionError('Lost edit was swallowed')
            known=sessions[42].menu.state.context.message_id
            session.respond(EditMessageText,response)
            await command()
            assert sessions[42].menu.state.context.message_id==known
            await click('cancel'); assert sessions[42].menu.state.phase=='cancelled'
            await command('/help'); assert session.calls[-1].text=='Calendar help preserved'
            assert sum(isinstance(m,SendMessage) and m.text!='Calendar help preserved' for m in session.calls)==1
            assert all(m.message_id==100 and m.parse_mode is None for m in session.calls if isinstance(m,EditMessageText))
        finally:
            await dispatcher.fsm.close(); await bot.session.close()
        print(json.dumps({'passed':True,'network':False,'session_closed':session.closed,'single_message':True,
            'date_time_back':True,'unavailable_date':True,'month_navigation':True,'owner_stale_guards':True,
            'schedule_confirmation_guard':True,'durable_replay':True,'existing_dispatcher_preserved':True,
            'unknown_edit_recovery':True,'business_effects':business_effects,
            'edits':sum(isinstance(m,EditMessageText) for m in session.calls)}))


if __name__ == '__main__': asyncio.run(main())
