/** Positive/negative compile consumer for async state, versioned drafts and recovery pointers. */
import {ScopedAsyncState,SelectionDraftStore,PendingOperationStore,
  type StorageFactory,type AsyncReadSnapshot,type PendingOperationRead} from '@awesome-telegram/patterns';

export async function typedState(storage: StorageFactory): Promise<AsyncReadSnapshot<{id: string}>> {
  const reads=new ScopedAsyncState<{id: string}>({maxEntries:2});reads.setScope('100:42');
  const result=await reads.read('order',async({scope,signal})=>{signal.throwIfAborted();return {id:scope};});
  if (result.status==='ready') result.value.id.toUpperCase();
  // @ts-expect-error loader output must match the declared DTO
  await reads.read('order',async()=>({id:123}));
  // @ts-expect-error context is immutable
  await reads.read('order',async context=>{context.scope='forged';return {id:'x'};});
  // @ts-expect-error snapshots cannot be assigned arbitrary states
  reads.snapshot('order').status='invented';
  const draft=new SelectionDraftStore(storage,{namespace:'b',scope:'100:42',ttlMs:100,schemaVersion:2,
    migrateFrom:{1:value=>{const previous=value as {service:string};return {serviceId:previous.service,slotId:null};}}});
  draft.write({serviceId:'x',slotId:null});
  // @ts-expect-error draft API does not accept auth or pending operation fields
  draft.write({serviceId:'x',slotId:null,token:'private'});
  const pending=new PendingOperationStore(storage,{namespace:'b',scope:'100:42'});
  pending.reserve('123e4567-e89b-42d3-a456-426614174000');
  const restored: PendingOperationRead=pending.read();
  if (restored.status==='restored') {
    // @ts-expect-error pointer identity is immutable
    restored.value.operation='different';
    restored.value.state satisfies 'pending'|'unknown';
  }
  // @ts-expect-error storing a write payload is not a recovery-pointer API
  pending.reserve({operation:'x',payload:{price:1}});
  reads.dispose();return reads.snapshot('order');
}
