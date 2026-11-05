import {ValidationFailure} from './errors.js';
import type {StorageFactory} from './adapters.js';
export interface SelectionDraft { readonly serviceId: string | null; readonly slotId: string | null }
export type DraftRead =
  | {status: 'restored'; value: SelectionDraft}
  | {status: 'missing' | 'expired' | 'corrupt' | 'unavailable'};
export interface DraftOptions {
  namespace: string; scope: string; ttlMs: number; now?: () => number;
  /** Default 1 preserves existing keys and data. Migration requires an explicit decoder per old version. */
  schemaVersion?: number;
  migrateFrom?: Readonly<Record<number, (value: unknown) => SelectionDraft>>;
}
function draft(value: unknown): SelectionDraft {
  if (!value || typeof value !== 'object') throw new ValidationFailure('Invalid selection');
  const object = value as Record<string, unknown>;
  for (const key of ['serviceId', 'slotId']) {
    const item = object[key];
    if (item !== null && (typeof item !== 'string' || item.length > 128)) throw new ValidationFailure('Invalid selection ID');
  }
  // Explicit allowlist: no names, contacts, auth, prices or pending operation IDs.
  return { serviceId: object.serviceId as string | null, slotId: object.slotId as string | null };
}

function configure(namespace: string, scope: string): void {
  if (typeof scope!=='string' || typeof namespace!=='string' || !scope || !namespace || scope.length>256 || namespace.length>128) throw new ValidationFailure('Configure namespace and verified scope');
}
function clock(now: ()=>number): number {
  const value=now();
  if (typeof value!=='number' || !Number.isFinite(value) || value<0) throw new ValidationFailure('Configure finite nonnegative clock');
  return value;
}
function version(value: number): void {
  if (!Number.isSafeInteger(value) || value<1) throw new ValidationFailure('Configure a positive integer schema version');
}

/** Server-derived account/tenant scope; only selection identifiers, never operation identity. */
export class SelectionDraftStore {
  readonly key: string;
  private readonly now: () => number;
  private readonly scope: string;
  private readonly ttlMs: number;
  private readonly schemaVersion: number;
  private readonly migrations: ReadonlyMap<number,(value: unknown)=>SelectionDraft>;
  private readonly prefix: string;
  constructor(private readonly storage: StorageFactory, options: DraftOptions) {
    configure(options.namespace,options.scope);
    if (!Number.isFinite(options.ttlMs) || options.ttlMs<=0) throw new ValidationFailure('Configure positive draft TTL');
    this.schemaVersion=options.schemaVersion??1;version(this.schemaVersion);
    const migrations=new Map<number,(value: unknown)=>SelectionDraft>();
    if (options.migrateFrom!==undefined && (!options.migrateFrom || typeof options.migrateFrom!=='object' || Array.isArray(options.migrateFrom))) throw new ValidationFailure('Configure an explicit migration map');
    for (const [key,decoder] of Object.entries(options.migrateFrom??{})) {
      const from=Number(key);version(from);
      if (String(from)!==key || from>=this.schemaVersion || typeof decoder!=='function') throw new ValidationFailure('Configure explicit older-version draft decoder');
      migrations.set(from,decoder);
    }
    this.migrations=migrations;
    this.prefix=`tg-selection:${encodeURIComponent(options.namespace)}:${encodeURIComponent(options.scope)}:v`;
    this.key = this.prefix+this.schemaVersion;
    this.scope = options.scope;
    this.ttlMs = options.ttlMs;
    this.now = options.now ?? Date.now;
  }
  write(value: SelectionDraft): boolean {
    const filtered = draft(value);
    try {
      const expires=clock(this.now)+this.ttlMs;
      if (!Number.isFinite(expires)) return false;
      this.storage().setItem(this.key, JSON.stringify({schema: this.schemaVersion, scope: this.scope, expires, value: filtered}));
      return true;
    } catch { return false; }
  }
  read(): DraftRead {
    let raw: string | null;
    try { raw = this.storage().getItem(this.key); } catch { return {status: 'unavailable'}; }
    if (raw === null) return this.migrate();
    let now: number;
    try {now=clock(this.now);} catch {return {status:'unavailable'};}
    try {
      const saved = JSON.parse(raw) as Record<string, unknown>;
      if (!saved || saved.schema !== this.schemaVersion || saved.scope !== this.scope || typeof saved.expires !== 'number' || !Number.isFinite(saved.expires)) throw new ValidationFailure('Invalid envelope');
      if (saved.expires <= now) { this.clear(); return {status: 'expired'}; }
      return {status: 'restored', value: draft(saved.value)};
    } catch { this.clear(); return {status: 'corrupt'}; }
  }
  clear(): boolean {
    let cleared=true;
    for (const key of [this.key,...[...this.migrations.keys()].map(from=>this.prefix+from)]) {
      try {this.storage().removeItem(key);} catch {cleared=false;}
    }
    return cleared;
  }
  private migrate(): DraftRead {
    for (const from of [...this.migrations.keys()].sort((a,b)=>b-a)) {
      const key=this.prefix+from;
      let raw: string|null;
      try {raw=this.storage().getItem(key);} catch {return {status:'unavailable'};}
      if (raw===null) continue;
      let now: number;
      try {now=clock(this.now);} catch {return {status:'unavailable'};}
      let filtered: SelectionDraft;let expires: number;
      try {
        const saved=JSON.parse(raw) as Record<string,unknown>;
        if (!saved || saved.schema!==from || saved.scope!==this.scope || typeof saved.expires!=='number' || !Number.isFinite(saved.expires)) return {status:'corrupt'};
        if (saved.expires<=now) {
          try {this.storage().removeItem(key);} catch {/* Expired draft is never restored even if removal fails. */}
          return {status:'expired'};
        }
        filtered=draft(this.migrations.get(from)!(saved.value));
        expires=Math.min(saved.expires,now+this.ttlMs);
      } catch {return {status:'corrupt'};} // Preserve legacy data when decoding fails.
      try {
        this.storage().setItem(this.key,JSON.stringify({schema:this.schemaVersion,scope:this.scope,expires,value:filtered}));
      } catch {return {status:'unavailable'};}
      // New current data is durable before old data is removed. Quota/failed write never destroys legacy.
      try {this.storage().removeItem(key);} catch {/* Current version is already stored. */}
      return {status:'restored',value:filtered};
    }
    return {status:'missing'};
  }
}

export interface PendingOperation {readonly operation: string; readonly createdAt: number; readonly state: 'pending'|'unknown'}
export type PendingOperationRead =
  | {readonly status:'restored'; readonly value:PendingOperation}
  | {readonly status:'missing'|'corrupt'|'unsupported'|'unavailable'};
export type PendingOperationReservation =
  | {readonly status:'reserved'|'existing'; readonly value:PendingOperation}
  | {readonly status:'blocked'; readonly reason:'corrupt'|'unsupported'|'unavailable'};
export interface PendingOperationOptions {readonly namespace: string; readonly scope: string; readonly now?: ()=>number}
const OPERATION=/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
function operation(value: string): void {
  if (typeof value!=='string' || !OPERATION.test(value)) throw new ValidationFailure('Use a stable UUID v4 operation ID');
}

/** Minimal recovery pointer, separate from expiring form fields. Single owner, not cross-tab CAS.
 * No payload/auth/payment proof or automatic TTL deletion. Only a verified server result permits complete().
 */
export class PendingOperationStore {
  readonly key: string;
  private readonly scope: string;
  private readonly now: ()=>number;
  constructor(private readonly storage: StorageFactory, options: PendingOperationOptions) {
    configure(options.namespace,options.scope);
    this.key=`tg-pending:${encodeURIComponent(options.namespace)}:${encodeURIComponent(options.scope)}:v1`;
    this.scope=options.scope;this.now=options.now??Date.now;
  }
  read(): PendingOperationRead {
    let raw: string|null;
    try {raw=this.storage().getItem(this.key);} catch {return {status:'unavailable'};}
    if (raw===null) return {status:'missing'};
    try {
      const saved=JSON.parse(raw) as Record<string,unknown>;
      if (!saved || Array.isArray(saved) || saved.scope!==this.scope) return {status:'corrupt'};
      if (saved.schema!==1) return {status:'unsupported'};
      if (typeof saved.createdAt!=='number' || !Number.isFinite(saved.createdAt) || saved.createdAt<0 || (saved.state!=='pending' && saved.state!=='unknown')) return {status:'corrupt'};
      operation(saved.operation as string);
      return Object.freeze({status:'restored',value:Object.freeze({operation:saved.operation as string,createdAt:saved.createdAt,state:saved.state})});
    } catch {return {status:'corrupt'};} // Never erase the sole pointer to an unknown server operation.
  }
  reserve(id: string): PendingOperationReservation {
    operation(id);
    const saved=this.read();
    if (saved.status==='restored') return Object.freeze({status:'existing',value:saved.value});
    if (saved.status!=='missing') return {status:'blocked',reason:saved.status};
    let value: PendingOperation;
    try {value=Object.freeze({operation:id,createdAt:clock(this.now),state:'pending'});}
    catch {return {status:'blocked',reason:'unavailable'};}
    return this.write(value)?Object.freeze({status:'reserved',value}):{status:'blocked',reason:'unavailable'};
  }
  markUnknown(id: string): boolean {
    operation(id);const saved=this.read();
    if (saved.status!=='restored' || saved.value.operation!==id) return false;
    if (saved.value.state==='unknown') return true;
    return this.write({...saved.value,state:'unknown'});
  }
  complete(id: string): boolean {
    operation(id);const saved=this.read();
    if (saved.status!=='restored' || saved.value.operation!==id) return false;
    try {this.storage().removeItem(this.key);return true;} catch {return false;}
  }
  private write(value: PendingOperation): boolean {
    try {this.storage().setItem(this.key,JSON.stringify({schema:1,scope:this.scope,...value}));return true;} catch {return false;}
  }
}
