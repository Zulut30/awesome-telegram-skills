import {ScopedAsyncState,PendingOperationStore,AuthenticationRequired,ValidationFailure,
  type AsyncReadResult,type PendingOperationRead,type PendingOperationReservation,type StorageFactory} from '@awesome-telegram/patterns';
import type {Order,Session} from './api-types.js';

export type ShopSession=Pick<Session,'token'|'scope'>;
export interface ShopOrderReader {
  /** Caller retains HTTP/decoding; this immutable session is captured before the request starts. */
  operation(session: Readonly<ShopSession>,operation: string,signal: AbortSignal): Promise<Order>;
}
export interface ShopDomainSnapshot {
  readonly scope: string|null;
  readonly cart: readonly string[];
  readonly order: Order|null;
  readonly pending: PendingOperationRead|null;
}

/** Headless composition example. It owns no Telegram globals, listeners, timers, auth transport or UI.
 * setSession accepts only a session returned/decoded from the backend, never initDataUnsafe/user_id.
 * The current main.ts is unchanged; callers can adopt this state without a framework migration.
 */
export class ShopDomainState {
  private session: Readonly<ShopSession>|null=null;
  private readonly reads=new ScopedAsyncState<Order>();
  private readonly cart=new Set<string>();
  private pointer: PendingOperationStore|null=null;
  private order: Order|null=null;
  private disposed=false;
  private accountGeneration=0;
  constructor(private readonly storage: StorageFactory,private readonly reader: ShopOrderReader) {}
  setSession(session: ShopSession): void {
    this.active();
    if (!session || typeof session.token!=='string' || !session.token || session.token.length>128 || typeof session.scope!=='string' || !session.scope || session.scope.length>256) throw new ValidationFailure('Use a decoded backend session');
    const changed=this.session?.scope!==session.scope;
    this.session=Object.freeze({token:session.token,scope:session.scope});
    if (changed) {
      this.accountGeneration++;
      this.order=null;this.cart.clear();
      this.pointer=new PendingOperationStore(this.storage,{namespace:'shop',scope:session.scope});
      this.reads.setScope(session.scope);
    }
  }
  clearSession(): void {
    this.active();this.accountGeneration++;this.session=null;this.pointer=null;this.order=null;this.cart.clear();this.reads.setScope(null);
  }
  setCart(items: readonly string[]): void {
    this.active();
    if (!Array.isArray(items) || items.length>2 || items.some(item=>typeof item!=='string' || !item || item.length>128) || new Set(items).size!==items.length) throw new ValidationFailure('Use unique catalog identifiers');
    this.cart.clear();for (const item of items) this.cart.add(item);
  }
  snapshot(): ShopDomainSnapshot {
    return Object.freeze({scope:this.session?.scope??null,cart:Object.freeze([...this.cart]),order:this.order,pending:this.pointer?.read()??null});
  }
  reserveOrder(operation: string): PendingOperationReservation {
    this.requireSession();return this.pointer!.reserve(operation);
  }
  markUnknown(operation: string): boolean {
    this.requireSession();return this.pointer!.markUnknown(operation);
  }
  async reconcile(): Promise<AsyncReadResult<Order>|{readonly status:'blocked'}> {
    const session=this.requireSession(),pending=this.pointer!.read(),generation=this.accountGeneration;
    if (pending.status!=='restored') return Object.freeze({status:'blocked'});
    const operation=pending.value.operation;
    const result=await this.reads.read('order',async({signal,scope})=>{
      if (scope!==session.scope) throw new AuthenticationRequired();
      const order=await this.reader.operation(session,operation,signal);
      if (order.operation!==operation) throw new ValidationFailure('Server operation differs from recovery pointer');
      return order;
    });
    if (this.disposed || generation!==this.accountGeneration) return Object.freeze({status:'stale'});
    if (result.status==='ready') this.order=result.value;
    return result;
  }
  /** Only after this verified server order was reconciled; exact ID cannot erase another operation. */
  completeOrder(operation: string): boolean {
    this.requireSession();return this.order?.operation===operation && this.pointer!.complete(operation);
  }
  dispose(): void {
    if (this.disposed) return;
    this.disposed=true;this.accountGeneration++;this.session=null;this.pointer=null;this.order=null;this.cart.clear();this.reads.dispose();
  }
  private active(): void {if (this.disposed) throw new ValidationFailure('Shop state is disposed');}
  private requireSession(): Readonly<ShopSession> {
    this.active();if (!this.session) throw new AuthenticationRequired();return this.session;
  }
}
