import {ScopedAsyncState, PendingOperationStore, type AsyncStateOptions, type AsyncReadContext,
  type AsyncReadResult, type AsyncReadSnapshot, type PendingOperationOptions, type PendingOperation,
  type PendingOperationRead, type PendingOperationReservation} from '@awesome-telegram/patterns';
import {check} from './check.js';

export async function referenceState(): Promise<void> {
  const options: AsyncStateOptions={maxEntries:2};
  const cache=new ScopedAsyncState<{label:string}>(options);
  cache.setScope('server-verified:100:42');
  let late!: (value:{label:string})=>void;
  const old=cache.read('order',()=>new Promise(resolve=>{late=resolve;}));
  const result: AsyncReadResult<{label:string}>=await cache.read('order',async(context:AsyncReadContext)=>{
    check(context.scope==='server-verified:100:42' && !context.signal.aborted);
    return {label:'current'};
  });
  check(result.status==='ready' && result.value.label==='current');
  check((await old).status==='stale');late({label:'obsolete'});
  await Promise.resolve();
  const snapshot: AsyncReadSnapshot<{label:string}>=cache.snapshot('order');
  check(snapshot.status==='ready' && snapshot.value.label==='current');
  cache.setScope('server-verified:100:77');
  check(cache.snapshot('order').status==='idle');cache.dispose();

  const values=new Map<string,string>();
  const storage=()=>({getItem:(key:string)=>values.get(key)??null,
    setItem:(key:string,value:string)=>{values.set(key,value);},removeItem:(key:string)=>{values.delete(key);}});
  const pendingOptions: PendingOperationOptions={namespace:'reference',scope:'server-verified:100:42',now:()=>1000};
  const pending=new PendingOperationStore(storage,pendingOptions);
  const id='01234567-1234-4123-8123-0123456789ab';
  const reserved: PendingOperationReservation=pending.reserve(id);
  check(reserved.status==='reserved');
  if(reserved.status!=='reserved') throw Error('Fixture reservation failed');
  const pointer: PendingOperation=reserved.value;check(pointer.operation===id);
  check(pending.markUnknown(id));
  const reopened=new PendingOperationStore(storage,pendingOptions);
  const read: PendingOperationRead=reopened.read();
  check(read.status==='restored' && read.value.state==='unknown');
  const reused=reopened.reserve('11234567-1234-4123-8123-0123456789ab');
  check(reused.status==='existing' && reused.value.operation===id);
  // Host first verifies this exact server operation. Completing a draft or closing invoice is insufficient.
  check(reopened.complete(id) && reopened.read().status==='missing');
}
