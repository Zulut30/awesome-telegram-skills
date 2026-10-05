"""Explicit loopback fixture. Payments arrive via private stdin SDK updates only."""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import json
from pathlib import Path
import os
import sys
import time
from urllib.parse import urlencode
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.methods import AnswerPreCheckoutQuery, CreateInvoiceLink, SendMessage
from aiogram.types import Update
from telegram_patterns.testing import StubSession
from .api import create_app
from .payments import payment_router
from .storage import ProcessLock, connection
from .store import Store

TOKEN='100:OFFLINE_FIXTURE'
TERMS='Учебный пример, не оферта рабочего магазина. Одноразовые цифровые памятки, доступ после server receipt. Для запуска нужны ваши реальные условия и поддержка.'
SUPPORT='Учебная поддержка: обратитесь к владельцу тестового проекта через /paysupport. Telegram support не обслуживает покупки этого магазина.'


def signed(actor: int, *, timestamp: int | None = None, token: str = TOKEN) -> str:
    fields={'auth_date':str(int(time.time()) if timestamp is None else timestamp),'query_id':'offline-launch','user':json.dumps({'id':actor,'first_name':'Fixture'},separators=(',',':'))}
    key=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
    fields['hash']=hmac.new(key,'\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(),hashlib.sha256).hexdigest()
    return urlencode(fields)


def guards() -> list[int]:
    attempts=[0]
    def audit(event,args):
        if event in {'socket.connect','socket.getaddrinfo','socket.gethostbyname'}:
            address=args[1] if event=='socket.connect' else args[0]
            address=address[0] if isinstance(address,tuple) else address
            try:allowed=ipaddress.ip_address(str(address)).is_loopback
            except ValueError:allowed=False
            if not allowed:attempts[0]+=1;raise PermissionError('External network disabled in fixture')
    sys.addaudithook(audit)
    async def no_http(self,bot,method,timeout=None):raise AssertionError('Real SDK HTTP disabled')
    AiohttpSession.make_request=no_http  # type: ignore[method-assign]
    return attempts


def update(store: Store, row: dict, *, actor: int = 42, kind: str = 'paid', charge: str = 'fixture-charge', amount: int | None = None, currency: str = 'XTR', query_id: str = 'fixture-checkout') -> Update:
    user={'id':actor,'is_bot':False,'first_name':'Fixture'}
    payment={'invoice_payload':store.payload(row['id']),'currency':currency,'total_amount':row['total'] if amount is None else amount}
    if kind=='precheckout':return Update.model_validate({'update_id':1,'pre_checkout_query':{'id':query_id,'from':user,**payment}})
    return Update.model_validate({'update_id':2,'message':{'message_id':5,'date':int(time.time()),'chat':{'id':actor,'type':'private'},'from':user,'successful_payment':{**payment,'telegram_payment_charge_id':charge,'provider_payment_charge_id':''}}})


def stub() -> StubSession:
    session=StubSession().respond(AnswerPreCheckoutQuery,True)
    def link(method):
        assert method.currency=='XTR' and method.provider_token=='' and len(method.prices)==1
        return 'https://t.me/$fixture_'+method.payload.rsplit(':',1)[1].replace('-','')
    session.respond(CreateInvoiceLink,link)
    def reply(method):
        assert isinstance(method,SendMessage)
        return {'message_id':10,'date':int(time.time()),'chat':{'id':method.chat_id,'type':'private'},'text':method.text}
    session.respond(SendMessage,reply)
    return session


async def run(args) -> None:
    attempts=guards();lock=ProcessLock(args.database)
    session=stub();bot=Bot(TOKEN,session=session);dp=Dispatcher();runner=None
    try:
        store=Store(args.database,TOKEN,terms_version='demo-v1');recovered=store.recover()
        dp.include_router(payment_router(store,shop_url='https://fixture.invalid/',terms=TERMS,support=SUPPORT))
        app=create_app(store,bot,args.frontend,origin=f'http://127.0.0.1:{args.port}',terms=TERMS,support=SUPPORT,loopback_dev=True)
        runner=web.AppRunner(app,access_log=None,shutdown_timeout=5);await runner.setup();await web.TCPSite(runner,'127.0.0.1',args.port).start()
        print(json.dumps({'phase':'ready','launch':{str(actor):signed(actor) for actor in (42,77)},'recovered':recovered}),flush=True)
        while line:=await asyncio.to_thread(sys.stdin.readline):
            command=json.loads(line);action=command['action']
            if action=='stop':break
            if action=='receipt' or action=='precheckout':
                row=store.order(command.get('owner',42),command['id'])
                before=len(session.calls)
                await dp.feed_update(bot,update(store,row,actor=command.get('actor',42),kind=action if action=='precheckout' else 'paid',charge=command.get('charge','fixture-'+row['id']),amount=command.get('amount'),currency=command.get('currency','XTR'),query_id=command.get('query','query-'+row['id'])))
                checkout=[c.ok for c in session.calls[before:] if isinstance(c,AnswerPreCheckoutQuery)]
                result={'action':action,'passed':True,'checkout':checkout,'order':store.view(store.order(command.get('owner',42),command['id']))}
            elif action=='crash-invoice':
                def crash(actor,order_id,url):
                    assert url is not None and attempts[0]==0
                    with connection(store.database) as db:assert db.execute('SELECT invoice_state FROM shop_orders WHERE id=?',(order_id,)).fetchone()[0]=='creating'
                    print(json.dumps({'phase':'crash-invoice','invoice_called':True,'external_network_attempts':0,'telegram_requests':False}),flush=True)
                    os._exit(75)
                store.finish_invoice=crash  # type: ignore[method-assign]
                result={'action':action,'passed':True,'armed':True}
            elif action=='crash-receipt':
                original_paid=store.paid
                def crash_receipt(bot_id,actor,payload,currency,amount,charge):
                    result=original_paid(bot_id,actor,payload,currency,amount,charge)
                    assert not result['replayed'] and attempts[0]==0
                    print(json.dumps({'phase':'crash-receipt','committed':True,'external_network_attempts':0,'telegram_requests':False}),flush=True)
                    os._exit(76)
                store.paid=crash_receipt  # type: ignore[method-assign]
                result={'action':action,'passed':True,'armed':True}
            elif action=='stats':
                with connection(store.database) as db:
                    result={'action':action,'passed':True,'orders':db.execute('SELECT count(*) FROM shop_orders').fetchone()[0],'receipts':db.execute('SELECT count(*) FROM shop_receipts').fetchone()[0],'access':db.execute('SELECT count(*) FROM shop_access').fetchone()[0],'invoice_requests':sum(isinstance(c,CreateInvoiceLink) for c in session.calls),'external_network_attempts':attempts[0],'telegram_requests':False}
            else:raise ValueError('Unknown fixture action')
            print(json.dumps(result),flush=True)
    finally:
        if runner is not None:await runner.cleanup()
        await dp.fsm.close();await session.close();lock.close()
    print(json.dumps({'phase':'closed','passed':True,'session_closed':session.closed,'lock_released':lock.file.closed,'external_network_attempts':attempts[0],'telegram_requests':False}),flush=True)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--frontend',type=Path,required=True)
    parser.add_argument('--port',type=int,required=True)
    asyncio.run(run(parser.parse_args()))


if __name__=='__main__':main()
