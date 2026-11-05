import {ScopedAsyncState,PendingOperationStore,AuthenticationRequired,ValidationFailure,ApiError,safeErrorReport,
  type AsyncReadResult,type PendingOperationRead,type PendingOperationReservation,type StorageFactory} from '@awesome-telegram/patterns';
import type {Order,Session,Content} from './api-types.js';

export type ShopSession=Pick<Session,'token'|'scope'>;
export interface ShopOrderReader {
  /** Caller retains HTTP/decoding; this immutable session is captured before the request starts. */
  operation(session: Readonly<ShopSession>,operation: string,signal: AbortSignal): Promise<Order>;
  order?(session: Readonly<ShopSession>,id: string,signal: AbortSignal): Promise<Order>;
  orders?(session: Readonly<ShopSession>,signal: AbortSignal): Promise<readonly Order[]>;
  content?(session: Readonly<ShopSession>,sku: string,signal: AbortSignal): Promise<Content>;
  create?(session: Readonly<ShopSession>,intent: PendingIntent): Promise<Order>;
  invoice?(session: Readonly<ShopSession>,id: string): Promise<{readonly url:string}>;
  rotate?(session: Readonly<ShopSession>): Promise<Session>;
  revoke?(session: Readonly<ShopSession>): Promise<{readonly revoked:boolean}>;
}
export interface PendingIntent {readonly operation:string;readonly items:readonly string[];readonly terms:string}
export type ShopResult<T>=(AsyncReadResult<T>&{readonly revision?:number})|{readonly status:'blocked'};
export interface ShopDomainSnapshot {
  readonly scope: string|null;
  readonly cart: readonly string[];
  readonly order: Order|null;
  readonly pending: PendingOperationRead|null;
  readonly intent: PendingIntent|null;
  readonly orders: readonly Order[];
  readonly consent: boolean;
  readonly busy: boolean;
  readonly blocked: boolean;
  readonly closingNeeded: boolean;
  readonly retryAvailable: boolean;
  readonly revision: number;
}

/** Headless composition example. It owns no Telegram globals, listeners, timers, auth transport or UI.
 * setSession accepts only a session returned/decoded from the backend, never initDataUnsafe/user_id.
 * View and native lifecycle remain owned by main.ts; all account/business transitions live here.
 */
export class ShopDomainState {
  private session: Readonly<ShopSession>|null=null;
  private readonly reads=new ScopedAsyncState<Order>();
  private readonly cart=new Set<string>();
  private pointer: PendingOperationStore|null=null;
  private order: Order|null=null;
  private disposed=false;
  private accountGeneration=0;
  private readonly extraReads=new ScopedAsyncState<unknown>();
  private intent:PendingIntent|null=null;
  private orders:readonly Order[]=Object.freeze([]);
  private consent=false;
  private blocked=false;
  private busyOwner:symbol|null=null;
  private catalog:ReadonlySet<string>|null=null;
  private termsVersion='';
  private retryAvailable=false;
  constructor(private readonly storage: StorageFactory,private readonly reader: ShopOrderReader) {}
  get revision():number {return this.accountGeneration;}
  configureCatalog(ids:readonly string[],termsVersion=''):void {this.catalog=new Set(ids);this.termsVersion=termsVersion;}
  setSession(session: ShopSession): void {
    this.active();
    if (!session || typeof session.token!=='string' || !session.token || session.token.length>128 || typeof session.scope!=='string' || !session.scope || session.scope.length>256) throw new ValidationFailure('Use a decoded backend session');
    const changed=this.session?.scope!==session.scope,renewed=this.session?.token!==session.token;
    this.session=Object.freeze({token:session.token,scope:session.scope});
    if (renewed) {this.accountGeneration++;this.reads.clear();this.extraReads.clear();}
    if (changed) {
      this.order=null;this.orders=Object.freeze([]);this.cart.clear();this.consent=false;this.intent=null;this.blocked=false;this.busyOwner=null;this.retryAvailable=false;
      this.pointer=new PendingOperationStore(this.storage,{namespace:'shop',scope:session.scope});
      this.reads.setScope(session.scope);this.extraReads.setScope(session.scope);this.restoreIntent();
    }
  }
  clearSession(): void {
    this.active();this.accountGeneration++;this.session=null;this.pointer=null;this.order=null;this.orders=Object.freeze([]);this.intent=null;this.retryAvailable=false;this.consent=false;this.blocked=false;this.busyOwner=null;this.cart.clear();this.reads.setScope(null);this.extraReads.setScope(null);
  }
  setCart(items: readonly string[]): void {
    this.active();
    if (!Array.isArray(items) || items.length>2 || items.some(item=>typeof item!=='string' || !item || item.length>128) || new Set(items).size!==items.length) throw new ValidationFailure('Use unique catalog identifiers');
    this.cart.clear();for (const item of items) this.cart.add(item);
    this.saveCart();
  }
  snapshot(): ShopDomainSnapshot {
    const pending=this.pointer?.read()??null;
    return Object.freeze({scope:this.session?.scope??null,cart:Object.freeze([...this.cart]),order:this.order,pending,
      intent:this.intent,orders:this.orders,consent:this.consent,busy:this.busyOwner!==null,blocked:this.blocked,
      retryAvailable:this.retryAvailable,closingNeeded:this.busyOwner!==null||pending?.status==='restored'||(!this.order&&this.cart.size>0),revision:this.revision});
  }
  setConsent(value:boolean):void {this.active();this.consent=value===true;this.saveCart();}
  toggleCart(id:string):void {if (this.busyOwner||this.order||this.pointer?.read().status==='restored')return;this.setCart(this.cart.has(id)?[...this.cart].filter(item=>item!==id):[...this.cart,id]);}
  newSelection():void {if (!this.order||!['paid','refunded'].includes(this.order.status))return;this.order=null;this.cart.clear();this.consent=false;this.saveCart();}
  selectOrder(id:string):boolean {const order=this.orders.find(item=>item.id===id);if(!order||this.busyOwner)return false;this.order=order;return true;}
  cancelReads():void {this.reads.clear();this.extraReads.clear();}
  reserveOrder(operation: string): PendingOperationReservation {
    this.requireSession();return this.pointer!.reserve(operation);
  }
  markUnknown(operation: string): boolean {
    this.requireSession();return this.pointer!.markUnknown(operation);
  }
  async reconcile(): Promise<ShopResult<Order>> {
    const session=this.requireSession(),pending=this.pointer!.read(),generation=this.accountGeneration;
    if (this.busyOwner || (!this.order&&pending.status!=='restored')) return Object.freeze({status:'blocked'});
    const selected=this.order,operation=selected?.operation??(pending.status==='restored'?pending.value.operation:'');let missing=false;
    const result=await this.reads.read('order',async({signal,scope})=>{
      if (scope!==session.scope) throw new AuthenticationRequired();
      let order:Order;
      try {order=selected&&this.reader.order?await this.reader.order(session,selected.id,signal):await this.reader.operation(session,operation,signal);}
      catch(error){missing=error instanceof ApiError&&error.status===404;throw error;}
      if (order.operation!==operation) throw new ValidationFailure('Server operation differs from recovery pointer');
      return order;
    });
    if (this.disposed || generation!==this.accountGeneration) return Object.freeze({status:'stale'});
    if (result.status==='failed'&&missing&&!selected&&this.intent?.operation===operation) this.retryAvailable=true;
    if (result.status==='ready') this.acceptOrder(result.value);
    return {...result,revision:generation};
  }
  /** Explicit user action after a missing server result; reconciliation itself is read-only. */
  async retrySavedIntent():Promise<ShopResult<Order>> {
    this.requireSession();
    if(!this.retryAvailable||!this.intent||this.busyOwner||this.blocked||this.order||this.intent.terms!==this.termsVersion)return {status:'blocked'};
    this.retryAvailable=false;
    return this.sendIntent(this.intent);
  }
  /** Only after this verified server order was reconciled; exact ID cannot erase another operation. */
  completeOrder(operation: string): boolean {
    this.requireSession();return this.order?.operation===operation && this.pointer!.complete(operation);
  }
  async submit(terms:string,id:string):Promise<ShopResult<Order>> {
    this.requireSession();
    if(this.busyOwner||this.blocked||this.order||!this.consent||!this.cart.size)return {status:'blocked'};
    if(!this.intent){
      const reservation=this.pointer!.reserve(id);
      if(reservation.status!=='reserved'){this.blocked=reservation.status==='blocked';return {status:'blocked'};}
      const intent=Object.freeze({operation:id,items:Object.freeze([...this.cart].sort()),terms});
      try{this.storage().setItem(this.intentKey(),JSON.stringify(intent));this.intent=intent;}
      catch{this.blocked=true;return {status:'blocked'};}
    }
    return this.sendIntent(this.intent);
  }
  async loadOrders():Promise<ShopResult<readonly Order[]>> {
    const result=await this.readExtra('orders',(session,signal)=>{if(!this.reader.orders)throw new ValidationFailure();return this.reader.orders(session,signal);});
    if(result.status==='ready'&&result.revision===this.revision)this.orders=result.value;
    return result;
  }
  async readContent(sku:string):Promise<ShopResult<Content>> {
    return this.readExtra('content:'+sku,(session,signal)=>{if(!this.reader.content)throw new ValidationFailure();return this.reader.content(session,sku,signal);});
  }
  async invoice():Promise<ShopResult<{readonly url:string}>> {
    const id=this.order?.id;
    if(!id||this.order?.status!=='awaiting'||['unknown','creating'].includes(this.order.invoice_state))return {status:'blocked'};
    const result=await this.write(session=>{if(!this.reader.invoice)throw new ValidationFailure();return this.reader.invoice(session,id);});
    if(result.status==='failed'&&result.revision===this.revision&&result.error.outcome==='unknown'&&this.order?.id===id){
      this.order=Object.freeze({...this.order,invoice_state:'unknown' as const});
    }
    return result;
  }
  async rotate():Promise<ShopResult<Session>> {
    return this.write(session=>{if(!this.reader.rotate)throw new ValidationFailure();return this.reader.rotate(session);},value=>this.setSession(value));
  }
  async revoke():Promise<ShopResult<{readonly revoked:boolean}>> {
    const session=this.requireSession();if(this.busyOwner)return {status:'blocked'};
    // Local logout is immediate; server revocation still uses the captured old credential.
    this.clearSession();const revision=this.revision;
    try{
      if(!this.reader.revoke)throw new ValidationFailure();const value=await this.reader.revoke(session);
      if(this.disposed||revision!==this.revision)return {status:'stale'};
      return {status:'ready',value,revision};
    }catch(error){if(this.disposed||revision!==this.revision)return {status:'stale'};return {status:'failed',error:safeErrorReport(error,'write'),revision};}
  }
  private async readExtra<T>(key:string,loader:(session:Readonly<ShopSession>,signal:AbortSignal)=>Promise<T>):Promise<ShopResult<T>> {
    const session=this.requireSession(),revision=this.revision;
    const result=await this.extraReads.read(key,({signal})=>loader(session,signal));
    if(this.disposed||revision!==this.revision)return {status:'stale'};
    return {...result,revision} as ShopResult<T>;
  }
  private async write<T>(effect:(session:Readonly<ShopSession>)=>Promise<T>,accept?:(value:T)=>void):Promise<ShopResult<T>> {
    const session=this.requireSession();if(this.busyOwner)return {status:'blocked'};
    const owner=Symbol();this.busyOwner=owner;this.accountGeneration++;this.cancelReads();const revision=this.revision;
    try {
      const value=await effect(session);
      if(this.disposed||revision!==this.revision)return {status:'stale'};
      accept?.(value);return {status:'ready',value,revision:this.revision};
    }catch(error){if(this.disposed||revision!==this.revision)return {status:'stale'};return {status:'failed',error:safeErrorReport(error,'write'),revision};}
    finally{if(this.busyOwner===owner)this.busyOwner=null;}
  }
  private async sendIntent(intent:PendingIntent):Promise<ShopResult<Order>> {
    const result=await this.write(session=>{if(!this.reader.create)throw new ValidationFailure();return this.reader.create(session,intent);},order=>{
      if(order.operation!==intent.operation)throw new ValidationFailure('Server returned a different operation');this.acceptOrder(order);
    });
    if(result.status==='failed'&&result.revision===this.revision)this.pointer?.markUnknown(intent.operation);
    return result;
  }
  private acceptOrder(order:Order):void {
    this.retryAvailable=false;this.order=Object.freeze({...order,items:Object.freeze([...order.items])});
    if(['paid','refunded'].includes(order.status)&&this.pointer?.read().status==='restored'&&this.completeOrder(order.operation)){
      try{this.storage().removeItem(this.intentKey());this.intent=null;this.cart.clear();this.consent=false;this.saveCart();}catch{this.blocked=true;}
    }
  }
  private intentKey():string {return `telegram-shop:pending:${this.requireSession().scope}:v1`;}
  private cartKey():string {return `telegram-shop:cart:${this.requireSession().scope}:v1`;}
  private saveCart():void {
    if(!this.session)return;
    try{this.storage().setItem(this.cartKey(),JSON.stringify({schema:1,scope:this.session.scope,expires:Date.now()+15*60_000,items:[...this.cart],consent:this.consent,terms:this.termsVersion}));}catch{/* Checkout still requires a durable recovery pointer before dispatch. */}
  }
  private restoreCart():void {
    try{
      const raw=this.storage().getItem(this.cartKey());if(raw===null)return;
      const saved=JSON.parse(raw) as Record<string,unknown>;
      if(!saved||saved.schema!==1||saved.scope!==this.session!.scope||typeof saved.expires!=='number'||!Number.isFinite(saved.expires)||saved.expires<=Date.now()||!Array.isArray(saved.items)||saved.items.length>2||new Set(saved.items).size!==saved.items.length||saved.items.some(s=>typeof s!=='string'||!s||s.length>128||(this.catalog&&!this.catalog.has(s)))){this.storage().removeItem(this.cartKey());return;}
      for(const item of saved.items as string[])this.cart.add(item);
      this.consent=saved.consent===true&&saved.terms===this.termsVersion;
    }catch{/* A failed/corrupt draft never clears an independent pending operation. */}
  }
  private restoreIntent():void {
    try{
      this.restoreCart();
      const raw=this.storage().getItem(this.intentKey());const pointer=this.pointer!.read();
      if(!['missing','restored'].includes(pointer.status)){this.blocked=true;return;}
      if(raw===null)return;
      const saved=JSON.parse(raw) as PendingIntent;
      if(!saved||Object.keys(saved).sort().join(',')!=='items,operation,terms'||typeof saved.operation!=='string'||!Array.isArray(saved.items)||!saved.items.length||saved.items.length>2||new Set(saved.items).size!==saved.items.length||saved.items.some(s=>typeof s!=='string'||s.length>128||(this.catalog&&!this.catalog.has(s)))||typeof saved.terms!=='string'||!saved.terms||saved.terms.length>64)throw new ValidationFailure();
      const reserved=this.pointer!.reserve(saved.operation);
      if(reserved.status==='blocked'||reserved.value.operation!==saved.operation)throw new ValidationFailure();
      this.intent=Object.freeze({operation:saved.operation,items:Object.freeze([...saved.items]),terms:saved.terms});
      this.setCart(saved.items);this.consent=saved.terms===this.termsVersion;this.saveCart();
    }catch{this.blocked=true;}
  }
  dispose(): void {
    if (this.disposed) return;
    this.disposed=true;this.accountGeneration++;this.session=null;this.pointer=null;this.order=null;this.orders=Object.freeze([]);this.intent=null;this.retryAvailable=false;this.busyOwner=null;this.cart.clear();this.reads.dispose();this.extraReads.dispose();
  }
  private active(): void {if (this.disposed) throw new ValidationFailure('Shop state is disposed');}
  private requireSession(): Readonly<ShopSession> {
    this.active();if (!this.session) throw new AuthenticationRequired();return this.session;
  }
}
