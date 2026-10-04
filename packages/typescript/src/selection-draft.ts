export interface SelectionDraft { readonly serviceId: string | null; readonly slotId: string | null }
type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
export type DraftRead =
  | {status: 'restored'; value: SelectionDraft}
  | {status: 'missing' | 'expired' | 'corrupt' | 'unavailable'};
export interface DraftOptions { namespace: string; scope: string; ttlMs: number; now?: () => number }
function draft(value: unknown): SelectionDraft {
  if (!value || typeof value !== 'object') throw new Error('Invalid selection');
  const object = value as Record<string, unknown>;
  for (const key of ['serviceId', 'slotId']) {
    const item = object[key];
    if (item !== null && (typeof item !== 'string' || item.length > 128)) throw new Error('Invalid selection ID');
  }
  // Explicit allowlist: no names, contacts, auth, prices or pending operation IDs.
  return { serviceId: object.serviceId as string | null, slotId: object.slotId as string | null };
}

/** Server-derived account/tenant scope; schema 1 and only selection identifiers. */
export class SelectionDraftStore {
  readonly key: string;
  private readonly now: () => number;
  private readonly scope: string;
  private readonly ttlMs: number;
  constructor(private readonly storage: () => StorageLike, options: DraftOptions) {
    if (typeof options.scope !== 'string' || typeof options.namespace !== 'string' || !options.scope || !options.namespace || options.scope.length > 256 || options.namespace.length > 128 || !Number.isFinite(options.ttlMs) || options.ttlMs <= 0) {
      throw new Error('Configure namespace, verified scope and positive draft TTL');
    }
    this.key = `tg-selection:${encodeURIComponent(options.namespace)}:${encodeURIComponent(options.scope)}:v1`;
    this.scope = options.scope;
    this.ttlMs = options.ttlMs;
    this.now = options.now ?? Date.now;
  }
  write(value: SelectionDraft): boolean {
    const filtered = draft(value);
    try {
      this.storage().setItem(this.key, JSON.stringify({schema: 1, scope: this.scope, expires: this.now() + this.ttlMs, value: filtered}));
      return true;
    } catch { return false; }
  }
  read(): DraftRead {
    let raw: string | null;
    try { raw = this.storage().getItem(this.key); } catch { return {status: 'unavailable'}; }
    if (raw === null) return {status: 'missing'};
    try {
      const saved = JSON.parse(raw) as Record<string, unknown>;
      if (!saved || saved.schema !== 1 || saved.scope !== this.scope || typeof saved.expires !== 'number' || !Number.isFinite(saved.expires)) throw new Error('Invalid envelope');
      if (saved.expires <= this.now()) { this.clear(); return {status: 'expired'}; }
      return {status: 'restored', value: draft(saved.value)};
    } catch { this.clear(); return {status: 'corrupt'}; }
  }
  clear(): boolean {
    try { this.storage().removeItem(this.key); return true; } catch { return false; }
  }
}
