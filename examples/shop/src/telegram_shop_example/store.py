"""Real SQLite orders, hashed sessions, receipt ledger and owned access."""
from __future__ import annotations
from collections.abc import Callable
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid
from typing import TypedDict

from telegram_patterns import Money, PaymentBinding, PaymentConflict, PermissionDenied, SQLiteOnce, SQLitePaymentLedger, ValidationFailure, validate_init_data
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
SESSION_SECONDS = 600


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
            if versions and [r[0] for r in versions] not in ([1],[2],[3]):raise ValueError('Shop schema requires migration')
            if not versions:db.execute('INSERT INTO shop_schema VALUES(3)')
            for sql in (
                # csrf_hash stays NULL since bearer sessions (no cookie); existing v1 rows stay compatible.
                'CREATE TABLE IF NOT EXISTS shop_sessions(token_hash TEXT PRIMARY KEY,bot_id INTEGER,actor_id INTEGER,csrf_hash TEXT,expires INTEGER)',
                'CREATE TABLE IF NOT EXISTS shop_orders(id TEXT PRIMARY KEY,bot_id INTEGER,actor_id INTEGER,operation TEXT,items TEXT,total INTEGER,currency TEXT,status TEXT,terms TEXT,invoice_state TEXT,invoice_url TEXT,precheckout TEXT,UNIQUE(bot_id,actor_id,operation))',
                'CREATE TABLE IF NOT EXISTS shop_receipts(bot_id INTEGER,charge TEXT,order_id TEXT,actor_id INTEGER,amount INTEGER,currency TEXT,review INTEGER,PRIMARY KEY(bot_id,charge))',
                'CREATE TABLE IF NOT EXISTS shop_access(bot_id INTEGER,actor_id INTEGER,sku TEXT,order_id TEXT,PRIMARY KEY(bot_id,actor_id,sku))',
                "CREATE TABLE IF NOT EXISTS shop_roles(bot_id INTEGER NOT NULL,actor_id INTEGER NOT NULL,role TEXT NOT NULL CHECK(role IN ('customer','viewer','blocked')),PRIMARY KEY(bot_id,actor_id))",
                'CREATE TABLE IF NOT EXISTS shop_operators(bot_id INTEGER NOT NULL,actor_id INTEGER NOT NULL,enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),PRIMARY KEY(bot_id,actor_id))',
                'CREATE TABLE IF NOT EXISTS shop_payment_links(bot_id INTEGER NOT NULL,charge TEXT NOT NULL,order_id TEXT NOT NULL,actor_id INTEGER NOT NULL,amount INTEGER NOT NULL,currency TEXT NOT NULL,payload TEXT NOT NULL,invoice_operation TEXT NOT NULL,financial_order TEXT NOT NULL,financial_ready INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(bot_id,charge))',
                'CREATE TABLE IF NOT EXISTS shop_payment_ingress(id INTEGER PRIMARY KEY AUTOINCREMENT,bot_id INTEGER NOT NULL,charge TEXT NOT NULL,kind TEXT NOT NULL,event_json TEXT NOT NULL,event_hash TEXT NOT NULL,processed INTEGER NOT NULL DEFAULT 0,UNIQUE(bot_id,charge,kind))',
                'CREATE TABLE IF NOT EXISTS shop_refund_intents(bot_id INTEGER NOT NULL,operation TEXT NOT NULL,order_id TEXT NOT NULL,charge TEXT NOT NULL,actor_id INTEGER NOT NULL,created_at INTEGER NOT NULL,PRIMARY KEY(bot_id,operation))',
                'CREATE TABLE IF NOT EXISTS shop_operator_audit(sequence INTEGER PRIMARY KEY AUTOINCREMENT,bot_id INTEGER NOT NULL,actor_id INTEGER NOT NULL,order_id TEXT NOT NULL,operation TEXT,action TEXT NOT NULL,outcome TEXT NOT NULL,recorded_at INTEGER NOT NULL)',
                'CREATE TABLE IF NOT EXISTS shop_refund_facts(bot_id INTEGER NOT NULL,charge TEXT NOT NULL,order_id TEXT NOT NULL,PRIMARY KEY(bot_id,charge))',
            ):db.execute(sql)
            db.execute('UPDATE shop_schema SET version=3')  # Additive v1 migration; existing rows are preserved.
        self.once=SQLiteOnce(database,timeout=1);self.once.initialize()
        self.financial=SQLitePaymentLedger(database,timeout=1);self.financial.initialize()

    def actor(self, value: int) -> int:
        if type(value) is not int or value<=0:raise PermissionDenied()
        return value

    def configure_role(self, actor: int, role: str) -> None:
        """Trusted owner configuration only; never exposed as a browser/body-controlled route.

        Missing overrides mean the ordinary customer role. A viewer can inspect
        their own orders/content but cannot create orders/invoices or pre-checkout.
        A blocked actor cannot read or write private business objects. Sessions
        remain revocable; trusted payment facts are recorded for operator review.
        """
        self.actor(actor)
        if not isinstance(role,str) or role not in {'customer','viewer','blocked'}:raise ValidationFailure()
        with connection(self.database,write=True) as db:
            db.execute('INSERT INTO shop_roles VALUES(?,?,?) ON CONFLICT(bot_id,actor_id) DO UPDATE SET role=excluded.role',(self.bot_id,actor,role))

    def configure_operator(self, actor: int, enabled: bool) -> None:
        """Trusted owner-only capability configuration; never accepts a browser role claim."""
        self.actor(actor)
        if type(enabled) is not bool:raise ValidationFailure()
        with connection(self.database,write=True) as db:
            db.execute('INSERT INTO shop_operators VALUES(?,?,?) ON CONFLICT(bot_id,actor_id) DO UPDATE SET enabled=excluded.enabled',(self.bot_id,actor,int(enabled)))

    def _operator(self, db: sqlite3.Connection, actor: int) -> None:
        if self._role(db,actor)=='blocked' or not db.execute('SELECT 1 FROM shop_operators WHERE bot_id=? AND actor_id=? AND enabled=1',(self.bot_id,actor)).fetchone():raise PermissionDenied()

    def operator_identity(self, token: str) -> int:
        with connection(self.database) as db:
            actor=self._session_actor(db,token,int(self.now()));self._operator(db,actor);return actor

    def operator_order(self, token: str, order_id: str) -> dict:
        with connection(self.database) as db:
            actor=self._session_actor(db,token,int(self.now()));self._operator(db,actor)
            row=db.execute('SELECT * FROM shop_orders WHERE id=? AND bot_id=?',(order_id,self.bot_id)).fetchone()
            if row is None:raise PermissionDenied()
            return dict(row)

    def refund_check(self, token: str, actor: int):
        """The ledger runs this exact session/current-capability check inside reserve/start/replay writer."""
        def check(db,operation,replayed):
            if self._session_actor(db,token,int(self.now()))!=actor or operation.actor_id!=actor or operation.binding.bot_id!=self.bot_id or operation.kind!='refund':return False
            self._operator(db,actor)
            link=db.execute('SELECT order_id,actor_id,amount,currency,financial_order FROM shop_payment_links WHERE bot_id=? AND charge=? AND financial_ready=1',(self.bot_id,operation.charge_id)).fetchone()
            if link is None:return False
            return (link['actor_id'],link['amount'],link['currency'],link['financial_order'])==(operation.binding.user_id,operation.amount.minor_units,operation.amount.currency,operation.binding.order_id)
        return check

    def _role(self, db: sqlite3.Connection, actor: int) -> str:
        self.actor(actor)
        row=db.execute('SELECT role FROM shop_roles WHERE bot_id=? AND actor_id=?',(self.bot_id,actor)).fetchone()
        return row[0] if row else 'customer'

    def _authorize(self, db: sqlite3.Connection, actor: int, *, write: bool = False) -> None:
        if self._role(db,actor) not in ({'customer'} if write else {'customer','viewer'}):raise PermissionDenied()

    def _owned(self, db: sqlite3.Connection, actor: int, order_id: str, *, write: bool = False) -> dict:
        self._authorize(db,actor,write=write)
        row=db.execute('SELECT * FROM shop_orders WHERE id=? AND bot_id=? AND actor_id=?',(order_id,self.bot_id,actor)).fetchone()
        if row is None:raise PermissionDenied()
        return dict(row)

    def session(self, raw: str) -> dict:
        """Bearer session for the Authorization header: the client keeps the token in memory only.

        No cookie: inside Telegram Web the Mini App is a cross-site iframe, where SameSite cookies are not sent.
        A header the browser never attaches on its own also needs no CSRF token.
        """
        launch=validate_init_data(raw,self.token,max_age_seconds=3600,now=int(self.now()))
        with connection(self.database,write=True) as db:
            return self._issue_session(db,launch.user_id,int(self.now()))

    def _issue_session(self, db: sqlite3.Connection, actor: int, now: int) -> dict:
        self.actor(actor)
        token=secrets.token_urlsafe(32)
        db.execute('DELETE FROM shop_sessions WHERE bot_id=? AND expires<=?',(self.bot_id,now))
        db.execute('INSERT INTO shop_sessions(token_hash,bot_id,actor_id,expires) VALUES(?,?,?,?)',(digest(token),self.bot_id,actor,now+SESSION_SECONDS))
        return {'token':token,'scope':f'{self.bot_id}:{actor}'}

    def _session_actor(self, db: sqlite3.Connection, token: str, now: int) -> int:
        if not isinstance(token,str) or not token or len(token)>128:raise PermissionDenied()
        row=db.execute('SELECT actor_id FROM shop_sessions WHERE token_hash=? AND bot_id=? AND expires>?',(digest(token),self.bot_id,now)).fetchone()
        if not row:raise PermissionDenied()
        return self.actor(row['actor_id'])

    def authenticate(self, token: str) -> int:
        with connection(self.database) as db:
            return self._session_actor(db,token,int(self.now()))

    def rotate_session(self, token: str) -> dict:
        """Consume one live token and issue a replacement atomically; no grace/replay token.

        A lost response requires a new initData exchange. Orders/operation IDs are
        independent of sessions and remain reconcilable by the same verified actor.
        """
        with connection(self.database,write=True) as db:
            now=int(self.now());actor=self._session_actor(db,token,now)
            db.execute('DELETE FROM shop_sessions WHERE token_hash=? AND bot_id=?',(digest(token),self.bot_id))
            return self._issue_session(db,actor,now)

    def revoke_session(self, token: str) -> None:
        """Revoke only the supplied live session; other devices/accounts remain intact."""
        with connection(self.database,write=True) as db:
            self._session_actor(db,token,int(self.now()))
            db.execute('DELETE FROM shop_sessions WHERE token_hash=? AND bot_id=?',(digest(token),self.bot_id))

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
        def check(db: sqlite3.Connection, replayed: bool) -> bool:
            self._authorize(db,actor,write=True)
            return True
        result=self.once.run_guarded(f'shop:{self.bot_id}:actor:{actor}',operation,{'items':items,'terms':terms},apply,check=check)
        return self.order(actor,result.value['id'])

    def order(self, actor: int, order_id: str) -> dict:
        self.actor(actor)
        with connection(self.database) as db:
            return self._owned(db,actor,order_id)

    def operation(self, actor: int, operation: str) -> dict | None:
        self.actor(actor)
        with connection(self.database) as db:
            self._authorize(db,actor)
            row=db.execute('SELECT id FROM shop_orders WHERE bot_id=? AND actor_id=? AND operation=?',(self.bot_id,actor,operation)).fetchone()
        return self.order(actor,row[0]) if row else None

    def orders(self, actor: int) -> list[dict]:
        self.actor(actor)
        with connection(self.database) as db:
            self._authorize(db,actor)
            return [dict(r) for r in db.execute('SELECT * FROM shop_orders WHERE bot_id=? AND actor_id=? ORDER BY rowid DESC',(self.bot_id,actor))]

    def view(self, row: dict) -> dict:
        # No session secrets, raw personal data or charge identifiers in frontend DTO.
        return {k:row[k] for k in ('id','operation','total','currency','status','invoice_state')} | {'items':json.loads(row['items'])}

    def claim_invoice(self, actor: int, order_id: str) -> dict:
        with connection(self.database,write=True) as db:
            row=self._owned(db,actor,order_id,write=True)
            if row['status']!='awaiting':raise ValidationFailure()
            if row['invoice_state']=='ready':return row
            if row['invoice_state']!='none':raise UnknownInvoice()
            db.execute("UPDATE shop_orders SET invoice_state='creating' WHERE id=?",(order_id,))
            return row

    def finish_invoice(self, actor: int, order_id: str, url: str | None) -> None:
        # Recording an already-started remote result must survive a concurrent role revocation.
        with connection(self.database,write=True) as db:
            if not db.execute('SELECT 1 FROM shop_orders WHERE id=? AND bot_id=? AND actor_id=?',(order_id,self.bot_id,actor)).fetchone():raise PermissionDenied()
            db.execute('UPDATE shop_orders SET invoice_state=?,invoice_url=? WHERE id=? AND bot_id=? AND actor_id=?',('ready' if url else 'unknown',url,order_id,self.bot_id,actor))

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
            self._authorize(db,actor,write=True)
            row=self.payment_order(db,bot_id,actor,payload,currency,amount)
            if row['status']!='awaiting' or (row['precheckout'] and row['precheckout']!=query_id):raise PermissionDenied()
            if any(db.execute('SELECT 1 FROM shop_access WHERE bot_id=? AND actor_id=? AND sku=?',(self.bot_id,actor,s)).fetchone() for s in json.loads(row['items'])):raise PermissionDenied()
            # One accepted checkout query per order. Unknown earlier payment is reconciled,
            # never silently reopened for a second charge.
            db.execute('UPDATE shop_orders SET precheckout=? WHERE id=?',(query_id,row['id']))

    def paid(self, bot_id: int, actor: int, payload: str, currency: str, amount: int, charge: str) -> dict:
        if not isinstance(charge,str) or not charge or len(charge)>512:raise PermissionDenied()
        with connection(self.database,write=True) as db:
            return self._paid(db,bot_id,actor,payload,currency,amount,charge)

    def _paid(self, db: sqlite3.Connection, bot_id: int, actor: int, payload: str, currency: str, amount: int, charge: str) -> dict:
        row=self.payment_order(db,bot_id,actor,payload,currency,amount)
        old=db.execute('SELECT * FROM shop_receipts WHERE bot_id=? AND charge=?',(self.bot_id,charge)).fetchone()
        if old:
            if old['order_id']!=row['id'] or old['actor_id']!=actor or old['amount']!=amount or old['currency']!=currency:raise PermissionDenied()
            return {'replayed':True,'review':bool(old['review'])}
        refunded=db.execute('SELECT 1 FROM shop_refund_facts WHERE bot_id=? AND charge=?',(self.bot_id,charge)).fetchone() is not None
        review=refunded or self._role(db,actor)!='customer' or row['status'] in {'paid','review','refunded'} or any(db.execute('SELECT 1 FROM shop_access WHERE bot_id=? AND actor_id=? AND sku=?',(self.bot_id,actor,s)).fetchone() for s in json.loads(row['items']))
        db.execute('INSERT INTO shop_receipts VALUES(?,?,?,?,?,?,?)',(self.bot_id,charge,row['id'],actor,amount,currency,int(review)))
        if not review:
            # Authenticated receipt may arrive after restart or without a retained
            # precheckout update. Never require browser callback as proof.
            db.execute("UPDATE shop_orders SET status='paid' WHERE id=?",(row['id'],))
            for sku in json.loads(row['items']):
                db.execute('INSERT OR IGNORE INTO shop_access VALUES(?,?,?,?)',(self.bot_id,actor,sku,row['id']))
        elif refunded:
            db.execute("UPDATE shop_orders SET status='refunded' WHERE id=?",(row['id'],))
        elif row['status'] not in {'paid','refunded'}:
            db.execute("UPDATE shop_orders SET status='review' WHERE id=?",(row['id'],))
        return {'replayed':False,'review':review}


    def content(self, actor: int, sku: str) -> dict:
        self.actor(actor)
        with connection(self.database) as db:
            self._authorize(db,actor)
            allowed=db.execute("SELECT a.order_id FROM shop_access a JOIN shop_orders o ON o.id=a.order_id AND o.actor_id=a.actor_id AND o.bot_id=a.bot_id WHERE a.bot_id=? AND a.actor_id=? AND a.sku=? AND o.status='paid'",(self.bot_id,actor,sku)).fetchone()
        if not allowed or sku not in CONTENT:raise PermissionDenied()
        with connection(self.database) as db:
            closed=db.execute('SELECT 1 FROM shop_receipts r JOIN shop_refund_facts f ON f.bot_id=r.bot_id AND f.charge=r.charge WHERE r.bot_id=? AND r.order_id=? AND r.actor_id=? AND r.review=0',(self.bot_id,allowed['order_id'],actor)).fetchone()
            if closed is not None:raise PermissionDenied()
            linked=db.execute('SELECT l.* FROM shop_receipts r JOIN shop_payment_links l ON l.bot_id=r.bot_id AND l.charge=r.charge WHERE r.bot_id=? AND r.order_id=? AND r.actor_id=? AND r.review=0 AND l.financial_ready=1',(self.bot_id,allowed['order_id'],actor)).fetchone()
        if linked is not None:
            try:active=self.financial.has_access(self.link_binding(dict(linked)),now=int(self.now())).active
            except PaymentConflict:raise PermissionDenied() from None
            if not active:raise PermissionDenied()
        return {'id':sku,'title':CATALOG[sku]['title'],'text':CONTENT[sku]}

    @staticmethod
    def link_binding(link: dict) -> PaymentBinding:
        return PaymentBinding(f"shop:{link['bot_id']}",link['bot_id'],link['actor_id'],link['financial_order'],'telegram-stars',Money(link['amount'],link['currency'],0),route='telegram-stars')

    def receipt_target(self, actor: int, payload: str, currency: str, amount: int) -> dict:
        with connection(self.database) as db:return self.payment_order(db,self.bot_id,actor,payload,currency,amount)

    def payment_link(self, order_id: str, charge: str) -> dict | None:
        with connection(self.database) as db:
            row=db.execute('SELECT * FROM shop_payment_links WHERE bot_id=? AND charge=? AND order_id=?',(self.bot_id,charge,order_id)).fetchone()
            return None if row is None else dict(row)

    def record_financial_ingress(self, order: dict, charge: str, kind: str, event: dict) -> int:
        """Trusted SDK/history ingress only. Commit native facts before ledger/projection work or ack."""
        if kind not in {'paid','refunded'} or not isinstance(charge,str) or not charge or len(charge)>512:raise ValidationFailure()
        encoded=json.dumps(event,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        if len(encoded.encode('utf-8'))>16384:raise ValidationFailure()
        fingerprint=digest(encoded)
        tag=digest(charge)
        with connection(self.database,write=True) as db:
            current=self.payment_order(db,self.bot_id,order['actor_id'],self.payload(order['id']),'XTR',order['total'])
            link=(self.bot_id,charge,current['id'],current['actor_id'],current['total'],'XTR',self.payload(current['id']),'shop-import:'+current['operation']+':'+tag[:16],current['id']+':charge:'+tag)
            old=db.execute('SELECT * FROM shop_payment_links WHERE bot_id=? AND charge=?',(self.bot_id,charge)).fetchone()
            if old is None:db.execute('INSERT INTO shop_payment_links(bot_id,charge,order_id,actor_id,amount,currency,payload,invoice_operation,financial_order) VALUES(?,?,?,?,?,?,?,?,?)',link)
            elif tuple(old[name] for name in ('bot_id','charge','order_id','actor_id','amount','currency','payload','invoice_operation','financial_order'))!=link:raise PaymentConflict('Native charge already belongs to another immutable shop order')
            if kind=='refunded':
                db.execute('INSERT OR IGNORE INTO shop_refund_facts VALUES(?,?,?)',(self.bot_id,charge,current['id']))
                db.execute('UPDATE shop_payment_links SET financial_ready=1 WHERE bot_id=? AND charge=?',(self.bot_id,charge))
            old=db.execute('SELECT id,event_hash,event_json FROM shop_payment_ingress WHERE bot_id=? AND charge=? AND kind=?',(self.bot_id,charge,kind)).fetchone()
            if old is not None:
                if digest(old['event_json'])!=old['event_hash']:raise PaymentConflict('Financial ingress record changed')
                original=json.loads(old['event_json'])
                financial=lambda value:{k:v for k,v in value.items() if k not in {'origin','evidence_ref','provider_state'}}
                if financial(original)!=financial(event):raise PaymentConflict('Native charge has conflicting financial data')
                return old['id']
            identifier=db.execute('INSERT INTO shop_payment_ingress(bot_id,charge,kind,event_json,event_hash) VALUES(?,?,?,?,?)',(self.bot_id,charge,kind,encoded,fingerprint)).lastrowid
            assert identifier is not None
            return identifier

    def financial_ingress(self, identifier: int) -> dict:
        with connection(self.database) as db:
            row=db.execute('SELECT * FROM shop_payment_ingress WHERE id=? AND bot_id=?',(identifier,self.bot_id)).fetchone()
            if row is None:raise PermissionDenied()
            result=dict(row)
            if digest(result['event_json'])!=result['event_hash']:raise PaymentConflict('Financial ingress record changed')
            return result

    def pending_financial_ingress(self, *, limit: int = 100) -> list[int]:
        if type(limit) is not int or not 1<=limit<=1000:raise ValidationFailure()
        with connection(self.database) as db:return [r[0] for r in db.execute('SELECT id FROM shop_payment_ingress WHERE bot_id=? AND processed=0 ORDER BY id LIMIT ?',(self.bot_id,limit))]

    def complete_financial_ingress(self, identifier: int) -> dict:
        """Projection + handled marker commit together; the ledger was already independently committed."""
        with connection(self.database,write=True) as db:
            row=db.execute('SELECT * FROM shop_payment_ingress WHERE id=? AND bot_id=?',(identifier,self.bot_id)).fetchone()
            if row is None:raise PermissionDenied()
            event=json.loads(row['event_json']);link=db.execute('SELECT * FROM shop_payment_links WHERE bot_id=? AND charge=?',(self.bot_id,row['charge'])).fetchone()
            if link is None:raise PaymentConflict('Missing immutable financial binding')
            if row['processed']:return {'replayed':True,'review':False}
            if row['kind']=='paid':
                result=self._paid(db,self.bot_id,link['actor_id'],link['payload'],'XTR',link['amount'],row['charge'])
            else:
                db.execute('INSERT OR IGNORE INTO shop_refund_facts VALUES(?,?,?)',(self.bot_id,row['charge'],link['order_id']))
                primary=db.execute('SELECT charge FROM shop_receipts WHERE bot_id=? AND order_id=? AND actor_id=? AND review=0',(self.bot_id,link['order_id'],link['actor_id'])).fetchone()
                if primary is None or primary['charge']==row['charge']:
                    db.execute('DELETE FROM shop_access WHERE bot_id=? AND actor_id=? AND order_id=?',(self.bot_id,link['actor_id'],link['order_id']))
                    db.execute("UPDATE shop_orders SET status='refunded' WHERE id=? AND bot_id=?",(link['order_id'],self.bot_id))
                result={'replayed':False,'review':False}
            db.execute('UPDATE shop_payment_links SET financial_ready=1 WHERE bot_id=? AND charge=?',(self.bot_id,row['charge']))
            db.execute('UPDATE shop_payment_ingress SET processed=1 WHERE id=?',(identifier,))
            return result

    def operator_receipts(self, token: str, order_id: str) -> list[dict]:
        self.operator_order(token,order_id)
        with connection(self.database) as db:return [dict(r) for r in db.execute('SELECT charge,amount,currency,review FROM shop_receipts WHERE bot_id=? AND order_id=?',(self.bot_id,order_id))]

    def begin_refund_intent(self, token: str, order_id: str, charge: str, operation: str) -> dict:
        if not isinstance(operation,str) or not UUID.fullmatch(operation) or not isinstance(charge,str) or not charge or len(charge)>512:raise ValidationFailure()
        with connection(self.database,write=True) as db:
            actor=self._session_actor(db,token,int(self.now()));self._operator(db,actor)
            if not db.execute('SELECT 1 FROM shop_orders WHERE id=? AND bot_id=?',(order_id,self.bot_id)).fetchone():raise PermissionDenied()
            old=db.execute('SELECT * FROM shop_refund_intents WHERE bot_id=? AND operation=?',(self.bot_id,operation)).fetchone()
            if old is not None:
                if (old['order_id'],old['charge'],old['actor_id'])!=(order_id,charge,actor):raise PaymentConflict('Refund operation already has another immutable intent')
                return dict(old)
            db.execute('INSERT INTO shop_refund_intents VALUES(?,?,?,?,?,?)',(self.bot_id,operation,order_id,charge,actor,int(self.now())))
            db.execute('INSERT INTO shop_operator_audit(bot_id,actor_id,order_id,operation,action,outcome,recorded_at) VALUES(?,?,?,?,?,?,?)',(self.bot_id,actor,order_id,operation,'refund-request','intent-saved',int(self.now())))
            return dict(db.execute('SELECT * FROM shop_refund_intents WHERE bot_id=? AND operation=?',(self.bot_id,operation)).fetchone())

    def refund_intent(self, token: str, order_id: str, operation: str) -> dict | None:
        self.operator_order(token,order_id)
        with connection(self.database) as db:
            row=db.execute('SELECT * FROM shop_refund_intents WHERE bot_id=? AND order_id=? AND operation=?',(self.bot_id,order_id,operation)).fetchone()
            return None if row is None else dict(row)

    def refund_intents(self, token: str, order_id: str) -> list[dict]:
        self.operator_order(token,order_id)
        with connection(self.database) as db:return [dict(r) for r in db.execute('SELECT * FROM shop_refund_intents WHERE bot_id=? AND order_id=? ORDER BY created_at,operation LIMIT 200',(self.bot_id,order_id))]

    def record_operator_result(self, actor: int, order_id: str, operation: str | None, action: str, outcome: str) -> None:
        """Trusted completion audit for an already-authorized action; revocation cannot erase its result."""
        self.actor(actor)
        if action not in {'refund-dispatch','refund-reconcile'} or outcome not in {'pending','sending','unknown','confirmed','failed','canceled','operator-review'}:raise ValidationFailure()
        with connection(self.database,write=True) as db:
            db.execute('INSERT INTO shop_operator_audit(bot_id,actor_id,order_id,operation,action,outcome,recorded_at) VALUES(?,?,?,?,?,?,?)',(self.bot_id,actor,order_id,operation,action,outcome,int(self.now())))
