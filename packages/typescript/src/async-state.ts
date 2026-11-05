import {AuthenticationRequired, ValidationFailure, safeErrorReport, type ErrorReport} from './errors.js';

export type AsyncReadSnapshot<T> =
  | {readonly status: 'idle'}
  | {readonly status: 'loading'}
  | {readonly status: 'ready'; readonly value: T}
  | {readonly status: 'failed'; readonly error: ErrorReport};
export type AsyncReadResult<T> =
  | {readonly status: 'ready'; readonly value: T}
  | {readonly status: 'failed'; readonly error: ErrorReport}
  | {readonly status: 'stale'};
export interface AsyncReadContext {readonly scope: string; readonly signal: AbortSignal}
export interface AsyncStateOptions {readonly maxEntries?: number}

const IDLE = Object.freeze({status: 'idle'} as const);
const LOADING = Object.freeze({status: 'loading'} as const);
const STALE = Object.freeze({status: 'stale'} as const);

/** Copy only plain JSON DTOs; neither caller mutation nor accessors/classes enter the cache. */
function detached<T>(value: T): T {
  const seen=new WeakSet<object>();let budget=10000;
  function copy(item: unknown, depth: number): unknown {
    if (--budget<0 || depth>64) throw new ValidationFailure('Read DTO exceeds cache limits');
    if (item===null || typeof item==='string' || typeof item==='boolean') return item;
    if (typeof item==='number' && Number.isFinite(item)) return item;
    if (typeof item!=='object' || seen.has(item)) throw new ValidationFailure('Read DTO must be plain JSON');
    const proto=Object.getPrototypeOf(item);
    if (!Array.isArray(item) && proto!==Object.prototype && proto!==null) throw new ValidationFailure('Read DTO must be plain JSON');
    seen.add(item);
    const descriptors=Object.getOwnPropertyDescriptors(item);
    if (Object.getOwnPropertySymbols(item).length || Object.values(descriptors).some(d=>'get' in d || 'set' in d)) throw new ValidationFailure('Read DTO must be plain JSON');
    let result: unknown;
    if (Array.isArray(item)) {
      const values=[];
      if (Object.keys(item).length!==item.length) throw new ValidationFailure('Read DTO arrays must be dense');
      for (let index=0;index<item.length;index++) values.push(copy(descriptors[String(index)]?.value,depth+1));
      result=Object.freeze(values);
    } else {
      const values: Record<string,unknown>={};
      for (const [key,descriptor] of Object.entries(descriptors)) {
        if (!descriptor.enumerable) throw new ValidationFailure('Read DTO must use enumerable fields');
        Object.defineProperty(values,key,{value:copy(descriptor.value,depth+1),enumerable:true});
      }
      result=Object.freeze(values);
    }
    seen.delete(item);
    return result;
  }
  return copy(value,0) as T;
}

interface Entry<T> {readonly controller: AbortController; readonly generation: number; state: AsyncReadSnapshot<T>}

/** Bounded, account-scoped read state. No transport, retries, tokens, timers or UI framework.
 * Loader cancellation is best effort; generation identity also rejects transports ignoring abort.
 * Cache DTOs and snapshots are detached/deep-frozen; private errors/payloads never become error text.
 */
export class ScopedAsyncState<T> {
  private readonly entries=new Map<string,Entry<T>>();
  private readonly maxEntries: number;
  private currentScope: string|null=null;
  private generation=0;
  private disposed=false;
  constructor(options: AsyncStateOptions={}) {
    this.maxEntries=options.maxEntries??32;
    if (!Number.isSafeInteger(this.maxEntries) || this.maxEntries<1 || this.maxEntries>512) throw new ValidationFailure('Configure cache size in 1..512');
  }
  get scope(): string|null {return this.currentScope;}
  setScope(scope: string|null): void {
    this.active();
    if (scope!==null && (typeof scope!=='string' || !scope || scope.length>256)) throw new ValidationFailure('Use server-verified scope or null');
    if (scope===this.currentScope) return;
    this.currentScope=scope;this.clear();
  }
  snapshot(key: string): AsyncReadSnapshot<T> {
    this.key(key);
    return this.entries.get(key)?.state??IDLE;
  }
  async read(key: string, loader: (context: AsyncReadContext)=>Promise<T>): Promise<AsyncReadResult<T>> {
    this.active();this.key(key);
    const scope=this.currentScope;
    if (scope===null) throw new AuthenticationRequired('Read state requires a server-verified scope');
    if (typeof loader!=='function') throw new ValidationFailure('Configure read loader');
    const previous=this.entries.get(key);
    const entry: Entry<T>={controller:new AbortController(),generation:++this.generation,state:LOADING};
    this.entries.delete(key);this.entries.set(key,entry);previous?.controller.abort();
    while (this.entries.size>this.maxEntries) {
      const oldest=this.entries.keys().next().value as string;
      const evicted=this.entries.get(oldest);this.entries.delete(oldest);evicted?.controller.abort();
    }
    const current=()=>!this.disposed && this.currentScope===scope && this.entries.get(key)?.generation===entry.generation;
    if (!current()) return STALE;
    let abort: ()=>void=()=>{};
    const cancelled=new Promise<{kind:'cancelled'}>(resolve=>{
      abort=()=>resolve({kind:'cancelled'});
      entry.controller.signal.addEventListener('abort',abort,{once:true});
    });
    // Catch both synchronous throw and late rejection, even after cancellation wins the race.
    let work: Promise<T>;
    try {work=Promise.resolve(loader(Object.freeze({scope,signal:entry.controller.signal})));}
    catch (error) {work=Promise.reject(error);}
    try {
      const result=await Promise.race([cancelled,work.then(value=>({kind:'value' as const,value}),error=>({kind:'error' as const,error}))]);
      if (!current() || result.kind==='cancelled') return STALE;
      const state: AsyncReadResult<T>=result.kind==='error'
        ? Object.freeze({status:'failed',error:safeErrorReport(result.error)})
        : Object.freeze({status:'ready',value:detached(result.value)});
      entry.state=state;
      return state;
    } catch (error) {
      if (!current()) return STALE;
      const state=Object.freeze({status:'failed' as const,error:safeErrorReport(error)});
      entry.state=state;return state;
    } finally {
      entry.controller.signal.removeEventListener('abort',abort);
    }
  }
  cancel(key: string): void {
    this.key(key);const entry=this.entries.get(key);
    this.entries.delete(key);this.generation++;entry?.controller.abort();
  }
  clear(): void {
    const entries=[...this.entries.values()];this.entries.clear();this.generation++;
    for (const entry of entries) entry.controller.abort();
  }
  dispose(): void {
    if (this.disposed) return;
    this.disposed=true;this.currentScope=null;this.clear();
  }
  private active(): void {if (this.disposed) throw new ValidationFailure('Read state is disposed');}
  private key(value: string): void {if (typeof value!=='string' || !value || value.length>256) throw new ValidationFailure('Configure bounded read key');}
}
