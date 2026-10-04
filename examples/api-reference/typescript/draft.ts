import {SelectionDraftStore, type SelectionDraft, type DraftRead, type DraftOptions,
  type KeyValueStorage, type StorageFactory} from '@awesome-telegram/patterns';
import {check} from './check.js';

/** Только ID выбора; scope — заранее выбранная public fixture, без контактов. */
export function referenceDraft(): void {
  const values = new Map<string, string>(); let now = 1000;
  const storage: KeyValueStorage = {getItem: key => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); }, removeItem: key => { values.delete(key); }};
  const factory: StorageFactory = () => storage;
  const options: DraftOptions = {namespace: 'reference', scope: 'fixture-actor:42', ttlMs: 10, now: () => now};
  const store = new SelectionDraftStore(factory, options);
  const draft: SelectionDraft = {serviceId: 'public-id', slotId: null};
  check(store.read().status === 'missing'); check(store.write(draft));
  const result: DraftRead = store.read(); check(result.status === 'restored' && result.value.serviceId === 'public-id');
  now = 1011; check(store.read().status === 'expired' && !values.has(store.key));
  storage.setItem(store.key, 'invalid-json'); check(store.read().status === 'corrupt');
  check(store.clear());
  const unavailable = new SelectionDraftStore(() => { throw Error('Storage blocked'); }, options);
  check(unavailable.read().status === 'unavailable' && !unavailable.write(draft) && !unavailable.clear());
  // Настоящий account scope получает host; server pending identity хранится отдельно.
}
