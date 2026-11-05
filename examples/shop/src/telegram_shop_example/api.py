"""Same-origin API. No public endpoint accepts a payment or grants access."""
from __future__ import annotations
import json
import base64
import hashlib
from pathlib import Path
import re
from urllib.parse import urlsplit

from aiohttp import web
from aiogram import Bot
from telegram_patterns import InvalidInitData, OperationConflict, PaymentConflict, PermissionDenied, ValidationFailure
from telegram_patterns.aiogram import stars_invoice
from .storage import io_call
from .refunds import ShopRefunds
from .store import CATALOG, SESSION_SECONDS, Store, UnknownInvoice
from .recovery_state import RecoveryMaintenance


async def invoice(store: Store, bot: Bot, actor: int, order_id: str) -> str:
    if bot.id!=store.bot_id:raise PermissionDenied()
    row=await io_call(store.claim_invoice,actor,order_id)
    if row['invoice_state']=='ready':return row['invoice_url']
    try:
        url=await bot(stars_invoice('Учебные материалы','Доступ к выбранным памяткам',store.payload(order_id),row['total']))
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.netloc!='t.me' or not re.fullmatch(r'/\$[a-zA-Z0-9_-]{1,256}',parsed.path) or parsed.query or parsed.fragment:raise UnknownInvoice()
    except BaseException as error:
        await io_call(store.finish_invoice,actor,order_id,None)
        if not isinstance(error,Exception):raise
        raise UnknownInvoice() from None
    await io_call(store.finish_invoice,actor,order_id,url)
    return url


def create_app(store: Store, bot: Bot, frontend: Path, *, origin: str, terms: str, support: str, loopback_dev: bool = False) -> web.Application:
    url=urlsplit(origin)
    if not url.netloc or url.path or url.query or url.fragment or url.username or url.password or (url.scheme!='https' and not (loopback_dev and url.scheme=='http' and url.hostname=='127.0.0.1')):raise ValueError('Configure exact HTTPS origin; loopback fixture is explicit')
    if not terms or len(terms)>3500 or not support or len(support)>1000:raise ValueError('Configure terms and operator support')
    if bot.id!=store.bot_id:raise PermissionDenied()
    html=(frontend/'index.html').read_text(encoding='utf-8')
    importmap=re.search(r'<script type="importmap">(.*?)</script>',html,re.S)
    script_hash=" 'sha256-"+base64.b64encode(hashlib.sha256(importmap[1].encode()).digest()).decode()+"'" if importmap else ''

    @web.middleware
    async def boundary(request: web.Request, handler):
        try:
            if request.path != '/api/readiness':
                await io_call(store.require_operational)
            response=await handler(request)
        except RecoveryMaintenance:response=web.json_response({'error':'recovery-maintenance'},status=503)
        except InvalidInitData:response=web.json_response({'error':'authentication-required'},status=401)
        except PermissionDenied:response=web.json_response({'error':'permission-denied'},status=403)
        # Before ValueError: OperationConflict is a ConflictFailure, which is also a ValueError.
        except (OperationConflict,PaymentConflict):response=web.json_response({'error':'operation-conflict'},status=409)
        except (ValidationFailure,ValueError,TypeError,json.JSONDecodeError):response=web.json_response({'error':'validation-failed'},status=422)
        except UnknownInvoice:response=web.json_response({'error':'invoice-outcome-unknown'},status=503)
        except web.HTTPException as error:response=web.json_response({'error':'request-rejected'},status=error.status)
        except Exception:response=web.json_response({'error':'service-unavailable'},status=503)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' https://telegram.org"+script_hash+"; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; object-src 'none'"
        return response

    app=web.Application(middlewares=[boundary],client_max_size=32768)
    async def guarded_request(make_request, request_bot, method):
        await io_call(store.require_operational)
        return await make_request(request_bot,method)
    guard_released=False
    async def release_guard(application):
        nonlocal guard_released
        if not guard_released:
            bot.session.middleware.unregister(guarded_request)
            guard_released=True
    app.on_cleanup.append(release_guard)
    def same_origin(request: web.Request) -> None:
        if request.headers.getall('Origin',[])!=[origin]:raise PermissionDenied()
    def bearer(request: web.Request, *, write: bool = False) -> str:
        # Bearer token from memory, not a cookie: Telegram Web runs the Mini App in a cross-site iframe.
        # Reads permit no Origin (same-origin GET), but an explicitly foreign Origin is refused.
        if write or 'Origin' in request.headers:same_origin(request)
        if len(request.headers.getall('Authorization',[]))!=1:raise web.HTTPUnauthorized()
        scheme,_,token=request.headers.get('Authorization','').partition(' ')
        if scheme!='Bearer' or not token:raise web.HTTPUnauthorized()
        return token
    async def session_call(action, token: str):
        try:return await io_call(action,token)
        except PermissionDenied:raise web.HTTPUnauthorized() from None
    async def identity(request: web.Request, *, write: bool = False) -> int:
        return await session_call(store.authenticate,bearer(request,write=write))
    def unique_fields(pairs):
        result={}
        for name,value in pairs:
            if name in result:raise ValidationFailure()
            result[name]=value
        return result
    async def body(request: web.Request, fields: set[str]) -> dict:
        if request.content_type!='application/json':raise ValidationFailure()
        value=await request.json(loads=lambda raw:json.loads(raw,object_pairs_hook=unique_fields))
        if not isinstance(value,dict) or set(value)!=fields:raise ValidationFailure()
        return value

    async def session(request: web.Request):
        same_origin(request);data=await body(request,{'initData'})
        result=await io_call(store.session,data['initData'])
        return web.json_response(result|{'expires_in':SESSION_SECONDS})
    async def ready(request: web.Request):
        status=await io_call(store.recovery_status)
        return web.json_response(status,status=200 if status['ready'] else 503)
    async def rotate_session(request: web.Request):
        token=bearer(request,write=True);await body(request,set())
        result=await session_call(store.rotate_session,token)
        return web.json_response(result|{'expires_in':SESSION_SECONDS})
    async def revoke_session(request: web.Request):
        token=bearer(request,write=True);await body(request,set())
        await session_call(store.revoke_session,token)
        return web.json_response({'revoked':True})
    async def catalog(request):return web.json_response({'items':list(CATALOG.values()),'currency':'XTR'})
    async def policy(request):return web.json_response({'version':store.terms_version,'terms':terms,'support':support})
    async def create(request):
        actor=await identity(request,write=True);data=await body(request,{'operation','items','terms'})
        row=await io_call(store.create,actor,data['operation'],data['items'],data['terms'])
        return web.json_response(store.view(row))
    async def lookup(request):
        actor=await identity(request)
        row=await io_call(store.operation,actor,request.match_info['operation'])
        if row is None:raise web.HTTPNotFound()
        return web.json_response(store.view(row))
    async def order(request):return web.json_response(store.view(await io_call(store.order,await identity(request),request.match_info['id'])))
    async def orders(request):return web.json_response({'orders':[store.view(row) for row in await io_call(store.orders,await identity(request))]})
    async def create_invoice(request):
        actor=await identity(request,write=True);await body(request,set())
        return web.json_response({'url':await invoice(store,bot,actor,request.match_info['id'])})
    async def content(request):return web.json_response(await io_call(store.content,await identity(request),request.match_info['sku']))
    financial=ShopRefunds(store,bot)
    async def operator_order(request):
        await identity(request)
        return web.json_response(await financial.overview(bearer(request),request.match_info['id']))
    async def operator_refund(request):
        await identity(request,write=True);data=await body(request,{'operation','charge'})
        return web.json_response(await financial.request(bearer(request,write=True),request.match_info['id'],data['charge'],data['operation']))
    async def operator_refund_status(request):
        await identity(request)
        result=await financial.status(bearer(request),request.match_info['id'],request.match_info['operation'])
        if result is None:raise web.HTTPNotFound()
        return web.json_response(result)
    async def operator_refund_reconcile(request):
        await identity(request,write=True);await body(request,set())
        result=await financial.reconcile(bearer(request,write=True),request.match_info['id'],request.match_info['operation'])
        if result is None:raise web.HTTPNotFound()
        return web.json_response(result)
    async def index(request):
        text=(frontend/'index.html').read_text(encoding='utf-8')
        sdk='' if loopback_dev else '<script src="https://telegram.org/js/telegram-web-app.js"></script>'
        return web.Response(text=text.replace('<!-- telegram-sdk -->',sdk),content_type='text/html')
    app.add_routes([web.get('/api/readiness',ready),web.post('/api/session',session),web.post('/api/session/rotate',rotate_session),web.post('/api/session/revoke',revoke_session),web.get('/api/catalog',catalog),web.get('/api/policy',policy),web.post('/api/orders',create),web.get('/api/operations/{operation}',lookup),web.get('/api/orders',orders),web.get('/api/orders/{id}',order),web.post('/api/orders/{id}/invoice',create_invoice),web.get('/api/content/{sku}',content),web.get('/api/operator/orders/{id}',operator_order),web.post('/api/operator/orders/{id}/refunds',operator_refund),web.get('/api/operator/orders/{id}/refunds/{operation}',operator_refund_status),web.post('/api/operator/orders/{id}/refunds/{operation}/reconcile',operator_refund_reconcile),web.get('/',index)])
    app.router.add_static('/assets/',frontend/'assets',follow_symlinks=False)
    bot.session.middleware.register(guarded_request)
    return app
