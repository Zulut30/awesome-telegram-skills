"""Real SQLite orders, hashed sessions, receipt ledger and owned access."""
from __future__ import annotations
from collections.abc import Callable
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid
from typing import TypedDict

from telegram_patterns import PermissionDenied, SQLiteOnce, ValidationFailure, validate_init_data
from .storage import connection

class Product(TypedDict):
    id: str
    title: str
    description: str
    stars: int
    category: str


CATALOG: dict[str, Product] = {
    'bot-kit': {'id':'bot-kit','title':'Бот без путаницы','description':'Учебная памятка: команды, формы и повторные запросы.','stars':25,'category':'Python'},
    'ui-guide': {'id':'ui-guide','title':'Mini App на любом экране','description':'Учебная памятка: темы, навигация и доступные действия.','stars':40,'category':'TypeScript'},
}
CONTENT = {
    'bot-kit':'Памятка: проверяйте автора и владельца до эффекта и replay. ACK не означает успех. Сохраняйте operation ID при неизвестном результате. Выбирайте persistent storage по сценарию.',
    'ui-guide':'Памятка: не стирайте ввод при theme/resize/back. Цена и доступ приходят с backend. Проверяйте узкие и широкие экраны, focus, touch и error/empty/loading. invoiceClosed не подтверждает выдачу.',
}
UUID = re.compile(r'[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}')


class UnknownInvoice(RuntimeError):
    pass


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, database: Path, token: str, *, terms_version: str, now: Callable[[], float] = time.time):
        self.database, self.token, self.now, self.terms_version = database, token, now, terms_version
        self.bot_id = int(token.split(':',1)[0])
        if self.bot_id <= 0 or not terms_version or len(terms_version)>64: raise ValidationFailure()
        with connection(database, write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS shop_schema(version INTEGER NOT NULL)')
            versions=db.execute('SELECT version FROM shop_schema').fetchall()
            if versions and [r[0] for r in versions]!=[1]:raise ValueError('Shop schema requires migration')
            if not versions:db.execute('INSERT INTO shop_schema VALUES(1)')
            for sql in (
                'CREATE TABLE IF NOT EXISTS shop_sessions(token_hash TEXT PRIMARY KEY,bot_id INTEGER,actor_id INTEGER,csrf_hash TEXT,expires INTEGER)',
                'CREATE TABLE IF NOT EXISTS shop_orders(id TEXT PRIMARY KEY,bot_id INTEGER,actor_id INTEGER,operation TEXT,items TEXT,total INTEGER,currency TEXT,status TEXT,terms TEXT,invoice_state TEXT,invoice_url TEXT,precheckout TEXT,UNIQUE(bot_id,actor_id,operation))',
                'CREATE TABLE IF NOT EXISTS shop_receipts(bot_id INTEGER,charge TEXT,order_id TEXT,actor_id INTEGER,amount INTEGER,currency TEXT,review INTEGER,PRIMARY KEY(bot_id,charge))',
                'CREATE TABLE IF NOT EXISTS shop_access(bot_id INTEGER,actor_id INTEGER,sku TEXT,order_id TEXT,PRIMARY KEY(bot_id,actor_id,sku))',
            ):db.execute(sql)
        self.once=SQLiteOnce(database,timeout=1);self.once.initialize()

    def actor(self, value: int) -> int:
        if type(value) is not int or value<=0:raise PermissionDenied()
        return value

    def session(self, raw: str) -> dict:
        launch=validate_init_data(raw,self.token,max_age_seconds=3600,now=int(self.now()))
        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        with connection(self.database,write=True) as db:
            db.execute('DELETE FROM shop_sessions WHERE expires<=?',(int(self.now()),))
            db.execute('INSERT INTO shop_sessions VALUES(?,?,?,?,?)',(digest(token),self.bot_id,launch.user_id,digest(csrf),int(self.now())+600))
        return {'token':token,'csrf':csrf,'scope':f'{self.bot_id}:{launch.user_id}'}

    def authenticate(self, token: str, csrf: str | None = None) -> int:
        if not isinstance(token,str) or not token or len(token)>128:raise PermissionDenied()
        with connection(self.database) as db:
            row=db.execute('SELECT * FROM shop_sessions WHERE token_hash=? AND bot_id=? AND expires>?',(digest(token),self.bot_id,int(self.now()))).fetchone()
            if not row or (csrf is not None and not hmac.compare_digest(row['csrf_hash'],digest(csrf))):raise PermissionDenied()
            return self.actor(row['actor_id'])

    def create(self, actor: int, operation: str, skus: list[str], terms: str) -> dict:
        self.actor(actor)
        if not isinstance(operation,str) or not UUID.fullmatch(operation):raise ValidationFailure()
        if not isinstance(skus,list) or not 1<=len(skus)<=2 or any(type(s) is not str or s not in CATALOG for s in skus) or len(set(skus))!=len(skus):raise ValidationFailure()
        if terms!=self.terms_version:raise ValidationFailure()
        items=sorted(skus)
        def apply(db: sqlite3.Connection):
            if any(db.execute('SELECT 1 FROM shop_access WHERE bot_id=? AND actor_id=? AND sku=?',(self.bot_id,actor,s)).fetchone() for s in items):raise ValidationFailure('Product already owned')
            order_id=str(uuid.uuid4());total=sum(CATALOG[s]['stars'] for s in items)
            db.execute("INSERT INTO shop_orders VALUES(?,?,?,?,?,?,?,'awaiting',?,'none',NULL,NULL)",(order_id,self.bot_id,actor,operation,json.dumps(items),total,'XTR',terms))
            return {'id':order_id}
        result=self.once.run(f'shop:{self.bot_id}:actor:{actor}',operation,{'items':items,'terms':terms},apply)
        return self.order(actor,result.value['id'])

    def order(self, actor: int, order_id: str) -> dict:
        self.actor(actor)
        with connection(self.database) as db:
            row=db.execute('SELECT * FROM shop_orders WHERE id=? AND bot_id=? AND actor_id=?',(order_id,self.bot_id,actor)).fetchone()
            if row is None:raise PermissionDenied()
            return dict(row)

    def operation(self, actor: int, operation: str) -> dict | None:
        self.actor(actor)
        with connection(self.database) as db:
            row=db.execute('SELECT id FROM shop_orders WHERE bot_id=? AND actor_id=? AND operation=?',(self.bot_id,actor,operation)).fetchone()
        return self.order(actor,row[0]) if row else None

    def orders(self, actor: int) -> list[dict]:
        self.actor(actor)
        with connection(self.database) as db:
            ids=[r[0] for r in db.execute('SELECT id FROM shop_orders WHERE bot_id=? AND actor_id=? ORDER BY rowid DESC',(self.bot_id,actor))]
        return [self.order(actor,i) for i in ids]

    def view(self, row: dict) -> dict:
        # No session secrets, raw personal data or charge identifiers in frontend DTO.
        return {k:row[k] for k in ('id','operation','total','currency','status','invoice_state')} | {'items':json.loads(row['items'])}

    def claim_invoice(self, actor: int, order_id: str) -> dict:
        self.order(actor,order_id)
        with connection(self.database,write=True) as db:
            row=dict(db.execute('SELECT * FROM shop_orders WHERE id=?',(order_id,)).fetchone())
            if row['status']!='awaiting':raise ValidationFailure()
            if row['invoice_state']=='ready':return row
            if row['invoice_state']!='none':raise UnknownInvoice()
            db.execute("UPDATE shop_orders SET invoice_state='creating' WHERE id=?",(order_id,))
            return row

    def finish_invoice(self, actor: int, order_id: str, url: str | None) -> None:
        self.order(actor,order_id)
        with connection(self.database,write=True) as db:
            db.execute('UPDATE shop_orders SET invoice_state=?,invoice_url=? WHERE id=?',('ready' if url else 'unknown',url,order_id))

    def recover(self) -> int:
        with connection(self.database,write=True) as db:
            return db.execute("UPDATE shop_orders SET invoice_state='unknown' WHERE bot_id=? AND invoice_state='creating'",(self.bot_id,)).rowcount

    def payload(self, order_id: str) -> str:
        return f'shop:{self.bot_id}:{order_id}'

    def payment_order(self, db: sqlite3.Connection, bot_id: int, actor: int, payload: str, currency: str, amount: int) -> dict:
        self.actor(actor)
        if type(bot_id) is not int or bot_id!=self.bot_id or type(amount) is not int or amount<=0 or currency!='XTR':raise PermissionDenied()
        prefix=f'shop:{self.bot_id}:'
        if not isinstance(payload,str) or not payload.startswith(prefix) or not UUID.fullmatch(payload[len(prefix):]):raise PermissionDenied()
        row=db.execute('SELECT * FROM shop_orders WHERE id=? AND bot_id=? AND actor_id=?',(payload[len(prefix):],self.bot_id,actor)).fetchone()
        if not row or row['total']!=amount or row['currency']!=currency or row['invoice_state']=='none':raise PermissionDenied()
        return dict(row)

    def precheckout(self, bot_id: int, actor: int, query_id: str, payload: str, currency: str, amount: int) -> None:
        if not isinstance(query_id,str) or not query_id or len(query_id)>256:raise PermissionDenied()
        with connection(self.database,write=True) as db:
            row=self.payment_order(db,bot_id,actor,payload,currency,amount)
            if row['status']!='awaiting' or (row['precheckout'] and row['precheckout']!=query_id):raise PermissionDenied()
            if any(db.execute('SELECT 1 FROM shop_access WHERE bot_id=? AND actor_id=? AND sku=?',(self.bot_id,actor,s)).fetchone() for s in json.loads(row['items'])):raise PermissionDenied()
            # One accepted checkout query per order. Unknown earlier payment is reconciled,
            # never silently reopened for a second charge.
            db.execute('UPDATE shop_orders SET precheckout=? WHERE id=?',(query_id,row['id']))

    def paid(self, bot_id: int, actor: int, payload: str, currency: str, amount: int, charge: str) -> dict:
        if not isinstance(charge,str) or not charge or len(charge)>512:raise PermissionDenied()
        with connection(self.database,write=True) as db:
            row=self.payment_order(db,bot_id,actor,payload,currency,amount)
            old=db.execute('SELECT * FROM shop_receipts WHERE bot_id=? AND charge=?',(self.bot_id,charge)).fetchone()
            if old:
                if old['order_id']!=row['id'] or old['actor_id']!=actor or old['amount']!=amount or old['currency']!=currency:raise PermissionDenied()
                return {'replayed':True,'review':bool(old['review'])}
            review=row['status'] in {'paid','review'} or any(db.execute('SELECT 1 FROM shop_access WHERE bot_id=? AND actor_id=? AND sku=?',(self.bot_id,actor,s)).fetchone() for s in json.loads(row['items']))
            db.execute('INSERT INTO shop_receipts VALUES(?,?,?,?,?,?,?)',(self.bot_id,charge,row['id'],actor,amount,currency,int(review)))
            if not review:
                # Authenticated receipt may arrive after restart or without a retained
                # precheckout update. Never require browser callback as proof.
                db.execute("UPDATE shop_orders SET status='paid' WHERE id=?",(row['id'],))
                for sku in json.loads(row['items']):
                    db.execute('INSERT OR IGNORE INTO shop_access VALUES(?,?,?,?)',(self.bot_id,actor,sku,row['id']))
            elif row['status']!='paid':
                db.execute("UPDATE shop_orders SET status='review' WHERE id=?",(row['id'],))
            return {'replayed':False,'review':review}

    def content(self, actor: int, sku: str) -> dict:
        self.actor(actor)
        with connection(self.database) as db:
            allowed=db.execute("SELECT 1 FROM shop_access a JOIN shop_orders o ON o.id=a.order_id AND o.actor_id=a.actor_id AND o.bot_id=a.bot_id WHERE a.bot_id=? AND a.actor_id=? AND a.sku=? AND o.status='paid'",(self.bot_id,actor,sku)).fetchone()
        if not allowed or sku not in CONTENT:raise PermissionDenied()
        return {'id':sku,'title':CATALOG[sku]['title'],'text':CONTENT[sku]}
