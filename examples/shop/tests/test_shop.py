import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import socket
import sqlite3
import tempfile
import time
import unittest
import uuid
from aiohttp import ClientSession, CookieJar, web
from aiogram import Bot, Dispatcher
from aiogram.methods import CreateInvoiceLink
from aiogram.utils.web_app import safe_parse_webapp_init_data
from telegram_patterns import InvalidInitData, OperationConflict, PermissionDenied, ValidationFailure
from telegram_shop_example.api import create_app, invoice
from telegram_shop_example.offline import TOKEN, TERMS, SUPPORT, signed, stub, update
from telegram_shop_example.payments import payment_router
from telegram_shop_example.storage import connection
from telegram_shop_example.store import Store, UnknownInvoice


class ShopTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='shop-tests-');self.root=Path(self.temp.name)
        self.database=self.root/'shop.sqlite';self.clock=[int(time.time())]
        self.store=Store(self.database,TOKEN,terms_version='demo-v1',now=lambda:self.clock[0])
    def tearDown(self):self.temp.cleanup()
    def create(self,*,actor=42,key=None,items=None):return self.store.create(actor,key or str(uuid.uuid4()),items or ['bot-kit','ui-guide'],'demo-v1')
    def prepared(self):
        row=self.create();self.store.claim_invoice(42,row['id']);self.store.finish_invoice(42,row['id'],'https://t.me/$fixture');return row
    def payment(self,row,*,charge='charge-1'):
        return self.store.paid(100,42,self.store.payload(row['id']),'XTR',row['total'],charge)

    async def test_launch_validation_crosschecks_sdk_and_hashes_session_secrets(self):
        raw=signed(42,timestamp=self.clock[0]);self.assertEqual(safe_parse_webapp_init_data(TOKEN,raw).user.id,42)
        session=self.store.session(raw);self.assertEqual(self.store.authenticate(session['token'],session['csrf']),42)
        for invalid in (raw.replace('offline-launch','tampered'),raw+'&auth_date=1',signed(42,timestamp=self.clock[0]-3600),signed(42,timestamp=self.clock[0]+60),signed(42,token='101:WRONG_BOT'),'user=x'):
            with self.assertRaises(InvalidInitData):self.store.session(invalid)
        with connection(self.database) as db:
            data=str(tuple(db.execute('SELECT * FROM shop_sessions').fetchone()))
        self.assertNotIn(session['token'],data);self.assertNotIn(session['csrf'],data);self.assertNotIn(raw,data)

    async def test_session_expiry_and_wrong_csrf_refuse_access(self):
        s=self.store.session(signed(42,timestamp=self.clock[0]))
        with self.assertRaises(PermissionDenied):self.store.authenticate(s['token'],'wrong')
        self.clock[0]+=600
        with self.assertRaises(PermissionDenied):self.store.authenticate(s['token'],s['csrf'])

    async def test_order_price_replay_conflict_and_owner_scope_survive_restart(self):
        key=str(uuid.uuid4());row=self.create(key=key)
        self.assertEqual(row['total'],65);self.assertEqual(row['currency'],'XTR')
        newer=Store(self.database,TOKEN,terms_version='demo-v1')
        self.assertEqual(newer.create(42,key,['ui-guide','bot-kit'],'demo-v1')['id'],row['id'])
        with self.assertRaises(OperationConflict):self.create(key=key,items=['bot-kit'])
        with self.assertRaises(PermissionDenied):self.store.order(77,row['id'])
        self.assertIsNone(self.store.operation(77,key))
        for items in ([],['bot-kit','bot-kit'],['unlisted']):
            with self.assertRaises(ValidationFailure):self.store.create(42,str(uuid.uuid4()),items,'demo-v1')
        with self.assertRaises(ValidationFailure):self.store.create(42,str(uuid.uuid4()),['bot-kit'],'stale-terms')

    async def test_concurrent_same_operation_creates_one_order_and_result(self):
        key=str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda _:self.create(key=key),range(2)))
        self.assertEqual(rows[0]['id'],rows[1]['id'])
        with connection(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shop_orders').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM telegram_pattern_operations').fetchone()[0],1)

    async def test_invoice_single_request_and_unknown_result_never_auto_reissued(self):
        row=self.create();session=stub()
        async with Bot(TOKEN,session=session) as bot:
            url=await invoice(self.store,bot,42,row['id']);self.assertEqual(await invoice(self.store,bot,42,row['id']),url)
            self.assertEqual(sum(isinstance(c,CreateInvoiceLink) for c in session.calls),1)
            other=self.create(items=['bot-kit'])
            def fail(method):raise TimeoutError('PRIVATE_CANARY')
            session.respond(CreateInvoiceLink,fail)
            with self.assertRaises(UnknownInvoice):await invoice(self.store,bot,42,other['id'])
            with self.assertRaises(UnknownInvoice):await invoice(self.store,bot,42,other['id'])
            self.assertEqual(sum(isinstance(c,CreateInvoiceLink) for c in session.calls),2)
            self.assertEqual(self.store.order(42,other['id'])['invoice_state'],'unknown')

    async def test_precheckout_checks_owner_bot_amount_currency_and_one_query(self):
        row=self.prepared();p=self.store.payload(row['id'])
        for bot,actor,currency,amount in ((101,42,'XTR',65),(100,77,'XTR',65),(100,42,'USD',65),(100,42,'XTR',1),(100,42,'XTR',True)):
            with self.assertRaises(PermissionDenied):self.store.precheckout(bot,actor,'query',p,currency,amount)
        self.store.precheckout(100,42,'query',p,'XTR',65);self.store.precheckout(100,42,'query',p,'XTR',65)
        with self.assertRaises(PermissionDenied):self.store.precheckout(100,42,'another',p,'XTR',65)
        with self.assertRaises(PermissionDenied):self.store.content(42,'bot-kit')

    async def test_receipt_duplicate_and_second_charge_do_not_repeat_access(self):
        row=self.prepared();self.assertFalse(self.payment(row)['replayed']);self.assertTrue(self.payment(row)['replayed'])
        newer=Store(self.database,TOKEN,terms_version='demo-v1');self.assertIn('Памятка',newer.content(42,'bot-kit')['text'])
        with self.assertRaises(PermissionDenied):newer.content(77,'bot-kit')
        self.assertTrue(self.payment(row,charge='charge-2')['review'])
        with connection(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shop_access').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT sum(review) FROM shop_receipts').fetchone()[0],1)

    async def test_failure_between_receipt_and_grant_rolls_back_entire_payment(self):
        row=self.prepared()
        with connection(self.database,write=True) as db:db.execute("CREATE TRIGGER fault BEFORE INSERT ON shop_access BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError,'^fixture$'):self.payment(row)
        with connection(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shop_receipts').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM shop_access').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT status FROM shop_orders').fetchone()[0],'awaiting')
        with connection(self.database,write=True) as db:db.execute('DROP TRIGGER fault')
        self.payment(row);self.assertEqual(self.store.order(42,row['id'])['status'],'paid')

    async def test_already_owned_product_rejects_checkout_and_late_charge_requires_review(self):
        first=self.prepared();other=self.create(items=['bot-kit'])
        self.store.claim_invoice(42,other['id']);self.store.finish_invoice(42,other['id'],'https://t.me/$other')
        self.payment(first)
        with self.assertRaises(PermissionDenied):self.store.precheckout(100,42,'other-query',self.store.payload(other['id']),'XTR',25)
        self.assertTrue(self.payment(other,charge='late-charge')['review'])
        self.assertEqual(self.store.order(42,other['id'])['status'],'review')
        with self.assertRaises(ValidationFailure):self.create(items=['bot-kit'])

    async def test_http_api_has_real_sessions_csrf_price_acl_and_no_receipt_ingress(self):
        frontend=self.root/'frontend';(frontend/'assets').mkdir(parents=True);(frontend/'index.html').write_text('<html><!-- telegram-sdk --></html>')
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.listen();sock.setblocking(False)
        origin=f'http://127.0.0.1:{port}';session=stub();bot=Bot(TOKEN,session=session);dp=Dispatcher();runner=None
        try:
            dp.include_router(payment_router(self.store,shop_url='https://fixture.invalid/',terms=TERMS,support=SUPPORT))
            app=create_app(self.store,bot,frontend,origin=origin,terms=TERMS,support=SUPPORT,loopback_dev=True)
            runner=web.AppRunner(app,access_log=None);await runner.setup();await web.SockSite(runner,sock).start()
            async with ClientSession(cookie_jar=CookieJar(unsafe=True)) as client:
                async with client.get(origin+'/api/content/bot-kit') as response:self.assertEqual(response.status,401)
                async with client.post(origin+'/api/session',json={'initData':signed(42)},headers={'Origin':'https://foreign.invalid'}) as response:self.assertEqual(response.status,403)
                async with client.post(origin+'/api/session',json={'initData':signed(42)},headers={'Origin':origin}) as response:
                    self.assertEqual(response.status,200);csrf=(await response.json())['csrf'];self.assertIn('HttpOnly',response.headers['Set-Cookie'])
                payload={'operation':str(uuid.uuid4()),'items':['bot-kit'],'terms':'demo-v1'};headers={'Origin':origin,'X-Shop-CSRF':csrf}
                async with client.post(origin+'/api/orders',json=payload,headers={'Origin':origin}) as response:self.assertEqual(response.status,401)
                for extra in ({'price':1},{'user_id':77},{'paid':True}):
                    async with client.post(origin+'/api/orders',json=payload|extra,headers=headers) as response:self.assertEqual(response.status,422)
                async with client.post(origin+'/api/orders',json=payload,headers=headers) as response:self.assertEqual(response.status,200);row=await response.json()
                async with client.post(origin+'/api/orders/'+row['id']+'/invoice',json={},headers=headers) as response:self.assertEqual(response.status,200)
                async with client.get(origin+'/api/content/bot-kit') as response:self.assertEqual(response.status,403)
                async with client.post(origin+'/api/receipt',json={'paid':True},headers=headers) as response:self.assertEqual(response.status,404)
                await dp.feed_update(bot,update(self.store,row))
                async with client.get(origin+'/api/content/bot-kit') as response:self.assertEqual(response.status,200)
                async with client.post(origin+'/api/session',json={'initData':signed(77)},headers={'Origin':origin}) as response:self.assertEqual(response.status,200)
                async with client.get(origin+'/api/orders/'+row['id']) as response:self.assertEqual(response.status,403)
                async with client.get(origin+'/api/content/bot-kit') as response:self.assertEqual(response.status,403)
        finally:
            if runner is not None:await runner.cleanup()
            else:sock.close()
            await dp.fsm.close();await session.close()


if __name__=='__main__':unittest.main()
