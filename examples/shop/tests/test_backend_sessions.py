"""Real loopback aiohttp/SQLite session and recovery boundaries; Telegram transport is synthetic."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import json
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
import time
import unittest
from urllib.parse import parse_qsl, urlencode
import uuid

from aiohttp import ClientConnectionError, ClientSession, web
from aiogram import Bot
from aiogram.methods import CreateInvoiceLink
from telegram_patterns import PermissionDenied
from telegram_shop_example.api import create_app
from telegram_shop_example.offline import TOKEN, TERMS, SUPPORT, signed, stub
from telegram_shop_example.storage import connection
from telegram_shop_example.store import Store


class BackendSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='shop-backend-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.database=self.root/'shop.sqlite'
        self.clock=[int(time.time())]
        self.store=self.reopen()
        self.frontend=self.root/'frontend';(self.frontend/'assets').mkdir(parents=True)
        (self.frontend/'index.html').write_text('<html><!-- telegram-sdk --></html>',encoding='utf-8')
        self.client=ClientSession();self.addAsyncCleanup(self.client.close)

    def reopen(self, token=TOKEN):
        return Store(self.database,token,terms_version='demo-v1',now=lambda:self.clock[0])

    @asynccontextmanager
    async def running(self, store=None):
        sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen();sock.setblocking(False)
        origin=f'http://127.0.0.1:{sock.getsockname()[1]}'
        transport=stub();bot=Bot(TOKEN,session=transport);runner=None
        try:
            app=create_app(store or self.store,bot,self.frontend,origin=origin,terms=TERMS,support=SUPPORT,loopback_dev=True)
            @web.middleware
            async def drop_reply(request,handler):
                response=await handler(request)
                # Test-only fault: abort the actual TCP connection AFTER the DB handler commits.
                if request.headers.get('X-Fixture-Drop-Reply')=='yes' and response.status==200:
                    request.transport.abort()
                return response
            app.middlewares.append(drop_reply)
            runner=web.AppRunner(app,access_log=None);await runner.setup()
            await web.SockSite(runner,sock).start()
            yield origin,transport
        finally:
            if runner is not None:await runner.cleanup()
            else:sock.close()
            await transport.close()

    async def call(self, origin, method, path, *, token=None, body=None, status=200, headers=None):
        auth={'Origin':origin}
        if token:auth['Authorization']='Bearer '+token
        auth.update(headers or {})
        async with self.client.request(method,origin+path,json=body,headers=auth) as response:
            self.assertEqual(response.status,status,f'{method} {path}')
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertNotIn('Access-Control-Allow-Origin',response.headers)
            self.assertNotIn('Set-Cookie',response.headers)
            return await response.json()

    async def login(self, origin, actor=42):
        return await self.call(origin,'POST','/api/session',body={'initData':signed(actor,timestamp=self.clock[0])})

    @asynccontextmanager
    async def process_running(self):
        # The existing offline runtime owns ProcessLock and denies external network/real SDK HTTP.
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
        process=await asyncio.create_subprocess_exec(
            sys.executable,'-m','telegram_shop_example.offline','--database',str(self.database),
            '--frontend',str(self.frontend),'--port',str(port),
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            ready=json.loads(await asyncio.wait_for(process.stdout.readline(),20))
            self.assertEqual(ready['phase'],'ready')
            yield f'http://127.0.0.1:{port}',process,ready
        finally:
            if process.returncode is None:
                process.stdin.write(b'{"action":"stop"}\n');await process.stdin.drain()
                try:
                    out,err=await asyncio.wait_for(process.communicate(),10)
                except BaseException:
                    if process.returncode is None:process.kill()
                    await process.wait()
                    raise
                self.assertEqual(process.returncode,0,err.decode('utf-8',errors='replace'))
                closed=json.loads(out.splitlines()[-1])
                self.assertTrue(closed['session_closed'] and closed['lock_released'])
                self.assertEqual(closed['external_network_attempts'],0)
                self.assertFalse(closed['telegram_requests'])

    async def test_rotation_and_current_session_revoke_are_durable_and_actor_bound(self):
        async with self.running() as (origin,_):
            first=await self.login(origin);companion=await self.login(origin);other=await self.login(origin,77)
            self.clock[0]+=30
            rotated=await self.call(origin,'POST','/api/session/rotate',token=first['token'],body={})
            self.assertNotEqual(first['token'],rotated['token'])
            self.assertEqual((rotated['scope'],rotated['expires_in']),('100:42',600))
            await self.call(origin,'GET','/api/orders',token=first['token'],status=401)
            await self.call(origin,'POST','/api/session/rotate',token=first['token'],body={},status=401)
        newer=self.reopen()
        self.assertEqual(newer.authenticate(rotated['token']),42)
        with self.assertRaises(PermissionDenied):self.reopen('101:OTHER_BOT').authenticate(rotated['token'])
        async with self.running(newer) as (origin,_):
            self.assertEqual(await self.call(origin,'POST','/api/session/revoke',token=rotated['token'],body={}),{'revoked':True})
            await self.call(origin,'POST','/api/session/revoke',token=rotated['token'],body={},status=401)
            await self.call(origin,'GET','/api/orders',token=rotated['token'],status=401)
            await self.call(origin,'GET','/api/orders',token=companion['token'])
            await self.call(origin,'GET','/api/orders',token=other['token'])
        restarted=self.reopen()
        with self.assertRaises(PermissionDenied):restarted.authenticate(rotated['token'])
        self.assertEqual(restarted.authenticate(companion['token']),42)
        self.assertEqual(restarted.authenticate(other['token']),77)
        with connection(self.database) as db:
            rows=str([tuple(row) for row in db.execute('SELECT * FROM shop_sessions')])
            self.assertEqual(db.execute('SELECT version FROM shop_schema').fetchone()[0],2)
        for secret in (first['token'],rotated['token'],companion['token'],other['token']):self.assertNotIn(secret,rows)

    async def test_rotation_renews_ttl_and_expired_sessions_cannot_rotate_or_revoke(self):
        async with self.running() as (origin,_):
            first=await self.login(origin);issued=self.clock[0]
            self.clock[0]+=599
            replacement=await self.call(origin,'POST','/api/session/rotate',token=first['token'],body={})
            self.clock[0]=issued+1198
            await self.call(origin,'GET','/api/orders',token=replacement['token'])
            self.clock[0]+=1
            for method,path,body in [('GET','/api/orders',None),('POST','/api/session/rotate',{}),('POST','/api/session/revoke',{})]:
                await self.call(origin,method,path,token=replacement['token'],body=body,status=401)

    async def test_concurrent_rotation_consumes_token_once_and_failed_insert_rolls_back(self):
        first=self.store.session(signed(42,timestamp=self.clock[0]))
        def rotate(_):
            try:return self.reopen().rotate_session(first['token'])
            except PermissionDenied:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(rotate,range(2)))
        winners=[result for result in results if result is not None]
        self.assertEqual(len(winners),1)
        with self.assertRaises(PermissionDenied):self.store.authenticate(first['token'])
        replacement=winners[0]['token']
        with connection(self.database,write=True) as db:
            db.execute("CREATE TRIGGER session_fault BEFORE INSERT ON shop_sessions BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError,'^fixture$'):self.store.rotate_session(replacement)
        self.assertEqual(self.reopen().authenticate(replacement),42)
        with connection(self.database) as db:self.assertEqual(db.execute('SELECT count(*) FROM shop_sessions').fetchone()[0],1)

    async def test_http_launch_refuses_forgery_wrong_bot_expiry_ambiguity_and_client_identity(self):
        raw=signed(42,timestamp=self.clock[0]);fields=dict(parse_qsl(raw))
        cases={
            'forged':raw.replace('offline-launch','forged-launch'),
            'wrong_bot':signed(42,timestamp=self.clock[0],token='101:WRONG_BOT'),
            'expired':signed(42,timestamp=self.clock[0]-3600),
            'future':signed(42,timestamp=self.clock[0]+31),
            'duplicate_field':raw+'&auth_date='+fields['auth_date'],
            'missing_hash':urlencode({k:v for k,v in fields.items() if k!='hash'}),
            'missing_date':urlencode({k:v for k,v in fields.items() if k!='auth_date'}),
            'malformed_encoding':raw+'&bad=%ZZ',
            'malformed_user':'user=x',
            'boolean_actor':signed(True,timestamp=self.clock[0]),
            'non_string':{'user_id':42},
        }
        async with self.running() as (origin,_):
            for label,value in cases.items():
                with self.subTest(case=label):
                    response=await self.call(origin,'POST','/api/session',body={'initData':value},status=401)
                    self.assertEqual(response,{'error':'authentication-required'})
            await self.call(origin,'POST','/api/session',body={'initData':raw,'user_id':77},status=422)
            duplicate='{'+f'"initData":{json.dumps(raw)},"initData":{json.dumps(raw)}'+'}'
            async with self.client.post(origin+'/api/session',data=duplicate,headers={'Origin':origin,'Content-Type':'application/json'}) as response:
                self.assertEqual(response.status,422)
            with connection(self.database) as db:self.assertEqual(db.execute('SELECT count(*) FROM shop_sessions').fetchone()[0],0)
            self.assertEqual((await self.login(origin))['scope'],'100:42')

    async def test_http_origin_headers_content_type_and_body_limits_fail_closed(self):
        async with self.running() as (origin,_):
            token=(await self.login(origin))['token']
            for path,body in [('/api/session',{'initData':signed(42,timestamp=self.clock[0])}),('/api/session/rotate',{}),('/api/session/revoke',{})]:
                for label,headers in [('missing',{'Authorization':'Bearer '+token}),
                                      ('foreign',{'Authorization':'Bearer '+token,'Origin':'https://foreign.invalid'}),
                                      ('null',{'Authorization':'Bearer '+token,'Origin':'null'}),
                                      ('duplicate',[('Authorization','Bearer '+token),('Origin',origin),('Origin',origin)])]:
                    with self.subTest(path=path,case=label):
                        async with self.client.post(origin+path,json=body,headers=headers) as response:self.assertEqual(response.status,403)
            await self.call(origin,'GET','/api/orders',token=token,headers={'Origin':'https://foreign.invalid'},status=403)
            async with self.client.get(origin+'/api/orders',headers={'Authorization':'Bearer '+token}) as response:self.assertEqual(response.status,200)
            async with self.client.get(origin+'/api/orders',headers=[('Authorization','Bearer '+token),('Authorization','Bearer '+token)]) as response:self.assertEqual(response.status,401)
            async with self.client.options(origin+'/api/session/rotate',headers={'Origin':'https://foreign.invalid','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization'}) as response:
                self.assertEqual(response.status,405);self.assertNotIn('Access-Control-Allow-Origin',response.headers)
            async with self.client.post(origin+'/api/session/rotate',data='{}',headers={'Origin':origin,'Authorization':'Bearer '+token}) as response:self.assertEqual(response.status,422)
            async with self.client.post(origin+'/api/session',json={'initData':'x'*32768},headers={'Origin':origin}) as response:self.assertEqual(response.status,413)
            await self.call(origin,'POST','/api/session/rotate',token=token,body={'actor_id':77},status=422)
            await self.call(origin,'POST','/api/session/revoke',token=token,body={'scope':'100:77'},status=422)
            self.assertEqual(self.store.authenticate(token),42,'refused body/origin never consumes a live token')

    async def test_every_private_object_route_uses_server_actor_and_owner_acl(self):
        async with self.running() as (origin,transport):
            owner=(await self.login(origin))['token'];other=(await self.login(origin,77))['token']
            operation=str(uuid.uuid4());payload={'operation':operation,'items':['bot-kit'],'terms':'demo-v1'}
            for extra in ({'actor_id':77},{'user_id':77},{'role':'admin'},{'total':1}):
                await self.call(origin,'POST','/api/orders',token=owner,body=payload|extra,status=422)
            row=await self.call(origin,'POST','/api/orders',token=owner,body=payload)
            self.assertEqual((row['total'],row['currency']),(25,'XTR'))
            await self.call(origin,'GET','/api/orders/'+row['id']+'?user_id=42',token=other,status=403)
            await self.call(origin,'GET','/api/operations/'+operation,token=other,status=404)
            self.assertEqual(await self.call(origin,'GET','/api/orders',token=other),{'orders':[]})
            await self.call(origin,'POST','/api/orders/'+row['id']+'/invoice',token=other,body={},status=403)
            self.assertEqual(len(transport.calls),0)
            await self.call(origin,'POST','/api/orders/'+row['id']+'/invoice',token=owner,body={})
            # Trusted receipt fixture, never an HTTP grant route.
            self.store.paid(100,42,self.store.payload(row['id']),'XTR',25,'acl-fixture-charge')
            await self.call(origin,'GET','/api/content/bot-kit',token=other,status=403)
            self.assertIn('text',await self.call(origin,'GET','/api/content/bot-kit',token=owner))
            other_row=await self.call(origin,'POST','/api/orders',token=other,body=payload)
            self.assertNotEqual(other_row['id'],row['id'],'operation identity is scoped to verified actor')
            for method,path,body in [('GET','/api/orders',None),('GET','/api/orders/'+row['id'],None),
                                     ('GET','/api/operations/'+operation,None),('GET','/api/content/bot-kit',None),
                                     ('POST','/api/orders',payload),('POST','/api/orders/'+row['id']+'/invoice',{})]:
                await self.call(origin,method,path,body=body,status=401)
            await self.call(origin,'POST','/api/receipt',token=owner,body={'paid':True},status=404)

    async def test_current_roles_gate_reads_writes_invoice_and_saved_replay(self):
        operation=str(uuid.uuid4());payload={'operation':operation,'items':['bot-kit'],'terms':'demo-v1'}
        async with self.running() as (origin,transport):
            owner=(await self.login(origin))['token']
            row=await self.call(origin,'POST','/api/orders',token=owner,body=payload)
            await self.call(origin,'POST','/api/orders/'+row['id']+'/invoice',token=owner,body={})
            self.reopen().configure_role(42,'viewer')
            await self.call(origin,'GET','/api/orders/'+row['id'],token=owner)
            await self.call(origin,'GET','/api/operations/'+operation,token=owner)
            for body in (payload,payload|{'operation':str(uuid.uuid4())}):
                await self.call(origin,'POST','/api/orders',token=owner,body=body,status=403)
            await self.call(origin,'POST','/api/orders/'+row['id']+'/invoice',token=owner,body={},status=403)
            with self.assertRaises(PermissionDenied):self.store.precheckout(100,42,'denied-role',self.store.payload(row['id']),'XTR',25)
            self.assertEqual(sum(isinstance(call,CreateInvoiceLink) for call in transport.calls),1)
            self.store.configure_role(42,'customer')
            self.store.paid(100,42,self.store.payload(row['id']),'XTR',25,'role-paid')
            self.store.configure_role(42,'viewer')
            await self.call(origin,'GET','/api/content/bot-kit',token=owner)
            self.store.configure_role(42,'blocked')
            for path in ('/api/orders','/api/orders/'+row['id'],'/api/operations/'+operation,'/api/content/bot-kit'):
                await self.call(origin,'GET',path,token=owner,status=403)
            # A valid token/launch or client role override never restores a server role.
            await self.call(origin,'POST','/api/orders',token=owner,body=payload,status=403)
            new_token=(await self.login(origin))['token']
            await self.call(origin,'GET','/api/orders',token=new_token,status=403)
            await self.call(origin,'POST','/api/session/revoke',token=new_token,body={})
        with connection(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shop_orders').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM telegram_pattern_operations').fetchone()[0],1)

    async def test_role_revocation_precedes_queued_writer_and_late_receipt_is_reviewed(self):
        import threading
        started=threading.Event();operation=str(uuid.uuid4())
        def create_queued():
            started.set();return self.reopen().create(42,operation,['bot-kit'],'demo-v1')
        with ThreadPoolExecutor(max_workers=1) as pool:
            with connection(self.database,write=True) as db:
                queued=pool.submit(create_queued);self.assertTrue(started.wait(2))
                db.execute("INSERT INTO shop_roles VALUES(100,42,'blocked')")
            with self.assertRaises(PermissionDenied):queued.result(timeout=5)
        with connection(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shop_orders').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM telegram_pattern_operations').fetchone()[0],0)
        self.store.configure_role(42,'customer')
        row=self.store.create(42,operation,['bot-kit'],'demo-v1');self.store.claim_invoice(42,row['id'])
        self.store.configure_role(42,'blocked')
        # Do not discard the fact of an already-started external effect after revocation.
        self.store.finish_invoice(42,row['id'],'https://t.me/$started-before-revocation')
        receipt=self.store.paid(100,42,self.store.payload(row['id']),'XTR',25,'late-after-role-revocation')
        self.assertEqual(receipt,{'replayed':False,'review':True})
        self.assertEqual(self.store.paid(100,42,self.store.payload(row['id']),'XTR',25,'late-after-role-revocation'),{'replayed':True,'review':True})
        with connection(self.database) as db:
            self.assertEqual(db.execute('SELECT status FROM shop_orders').fetchone()[0],'review')
            self.assertEqual(db.execute('SELECT count(*) FROM shop_receipts').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM shop_access').fetchone()[0],0)

    async def test_additive_v1_role_migration_preserves_sessions_orders_and_access(self):
        session=self.store.session(signed(42,timestamp=self.clock[0]))
        operation=str(uuid.uuid4());row=self.store.create(42,operation,['bot-kit'],'demo-v1');self.store.claim_invoice(42,row['id'])
        self.store.paid(100,42,self.store.payload(row['id']),'XTR',25,'migration-charge')
        with connection(self.database,write=True) as db:
            db.execute('DROP TABLE shop_roles');db.execute('UPDATE shop_schema SET version=1')
        migrated=self.reopen()
        self.assertEqual(migrated.authenticate(session['token']),42)
        self.assertEqual(migrated.operation(42,operation)['id'],row['id'])
        self.assertIn('text',migrated.content(42,'bot-kit'))
        self.assertEqual(migrated.create(42,operation,['bot-kit'],'demo-v1')['id'],row['id'])
        with connection(self.database) as db:
            self.assertEqual(db.execute('SELECT version FROM shop_schema').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT count(*) FROM shop_roles').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM shop_receipts').fetchone()[0],1)
        migrated.configure_role(42,'viewer');self.assertEqual(self.reopen().order(42,row['id'])['id'],row['id'])
        with self.assertRaises(PermissionDenied):self.reopen().create(42,operation,['bot-kit'],'demo-v1')
        with connection(self.database,write=True) as db:db.execute('UPDATE shop_schema SET version=999')
        with self.assertRaisesRegex(ValueError,'migration'):self.reopen()
        with connection(self.database) as db:self.assertEqual(db.execute('SELECT version FROM shop_schema').fetchone()[0],999)

    async def test_lost_order_and_rotation_replies_reconcile_same_operation_after_restart(self):
        operation=str(uuid.uuid4());payload={'operation':operation,'items':['bot-kit'],'terms':'demo-v1'}
        async with self.running() as (origin,_):
            token=(await self.login(origin))['token']
            with self.assertRaises(ClientConnectionError):
                async with self.client.post(origin+'/api/orders',json=payload,headers={'Origin':origin,'Authorization':'Bearer '+token,'X-Fixture-Drop-Reply':'yes'}) as response:await response.read()
            stored=self.store.operation(42,operation)
            self.assertIsNotNone(stored)
            with self.assertRaises(ClientConnectionError):
                async with self.client.post(origin+'/api/session/rotate',json={},headers={'Origin':origin,'Authorization':'Bearer '+token,'X-Fixture-Drop-Reply':'yes'}) as response:await response.read()
            await self.call(origin,'POST','/api/session/rotate',token=token,body={},status=401)
            self.store.claim_invoice(42,stored['id'])  # crash during remote invoice request: no automatic second send
        newer=self.reopen();self.assertEqual(newer.recover(),1)
        async with self.running(newer) as (origin,transport):
            new_token=(await self.login(origin))['token']
            recovered=await self.call(origin,'GET','/api/operations/'+operation,token=new_token)
            self.assertEqual((recovered['id'],recovered['operation'],recovered['invoice_state']),(stored['id'],operation,'unknown'))
            replay=await self.call(origin,'POST','/api/orders',token=new_token,body=payload)
            self.assertEqual(replay,recovered)
            await self.call(origin,'POST','/api/orders',token=new_token,body=payload|{'items':['ui-guide']},status=409)
            await self.call(origin,'POST','/api/orders/'+stored['id']+'/invoice',token=new_token,body={},status=503)
            self.assertFalse(any(isinstance(call,CreateInvoiceLink) for call in transport.calls))
        with connection(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shop_orders').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM telegram_pattern_operations').fetchone()[0],1)

    async def test_http_session_order_and_revoke_survive_actual_process_death(self):
        operation=str(uuid.uuid4());payload={'operation':operation,'items':['bot-kit'],'terms':'demo-v1'}
        async with self.process_running() as (origin,process,ready):
            first=await self.call(origin,'POST','/api/session',body={'initData':ready['launch']['42']})
            replacement=await self.call(origin,'POST','/api/session/rotate',token=first['token'],body={})
            row=await self.call(origin,'POST','/api/orders',token=replacement['token'],body=payload)
            self.store.claim_invoice(42,row['id'])
            process.kill();await asyncio.wait_for(process.wait(),10)
        async with self.process_running() as (origin,process,ready):
            self.assertEqual(ready['recovered'],1)
            await self.call(origin,'GET','/api/orders',token=first['token'],status=401)
            recovered=await self.call(origin,'GET','/api/operations/'+operation,token=replacement['token'])
            self.assertEqual((recovered['id'],recovered['invoice_state']),(row['id'],'unknown'))
            self.assertEqual((await self.call(origin,'POST','/api/orders',token=replacement['token'],body=payload))['id'],row['id'])
            await self.call(origin,'POST','/api/session/revoke',token=replacement['token'],body={})
            process.kill();await asyncio.wait_for(process.wait(),10)
        async with self.process_running() as (origin,_,ready):
            self.assertEqual(ready['recovered'],0)
            await self.call(origin,'GET','/api/orders',token=replacement['token'],status=401)
            fresh=await self.call(origin,'POST','/api/session',body={'initData':ready['launch']['42']})
            self.assertEqual((await self.call(origin,'GET','/api/operations/'+operation,token=fresh['token']))['id'],row['id'])
        with connection(self.database) as db:self.assertEqual(db.execute('SELECT count(*) FROM shop_orders').fetchone()[0],1)


if __name__=='__main__':unittest.main()
