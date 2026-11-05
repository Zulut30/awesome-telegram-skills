import test from 'node:test';
import assert from 'node:assert/strict';
import {ScopedAsyncState} from '../dist/async-state.js';
import {AuthenticationRequired,ValidationFailure} from '../dist/errors.js';

function deferred(){let resolve,reject;const promise=new Promise((ok,fail)=>{resolve=ok;reject=fail;});return {promise,resolve,reject};}

test('latest response wins even when the earlier loader ignores abort',async()=>{
  const state=new ScopedAsyncState();state.setScope('100:42');const first=deferred();let oldSignal;
  const old=state.read('orders',({signal})=>{oldSignal=signal;return first.promise;});
  assert.deepEqual(state.snapshot('orders'),{status:'loading'});
  const current=await state.read('orders',async()=>({orders:['new']}));
  assert.equal(oldSignal.aborted,true);assert.deepEqual(await old,{status:'stale'});
  first.resolve({orders:['old']});await first.promise;
  assert.deepEqual(current,{status:'ready',value:{orders:['new']}});
  assert.deepEqual(state.snapshot('orders'),current);
});

test('late failure cannot replace success or leak a private error',async()=>{
  const state=new ScopedAsyncState();state.setScope('100:42');const first=deferred();
  const old=state.read('order',()=>first.promise);
  await state.read('order',async()=>({id:'new'}));await old;
  first.reject(new Error('PRIVATE_INITDATA'));await new Promise(resolve=>setTimeout(resolve,0));
  assert.deepEqual(state.snapshot('order'),{status:'ready',value:{id:'new'}});
});

test('account switch clears cached values and suppresses old account results',async()=>{
  const state=new ScopedAsyncState();state.setScope('100:42');
  await state.read('profile',async({scope})=>({scope,name:'first'}));
  const first=deferred();let signal;
  const pending=state.read('order',context=>{signal=context.signal;assert.equal(context.scope,'100:42');return first.promise;});
  state.setScope('100:77');assert.equal(signal.aborted,true);
  assert.deepEqual(state.snapshot('profile'),{status:'idle'});assert.deepEqual(state.snapshot('order'),{status:'idle'});
  assert.deepEqual(await pending,{status:'stale'});
  first.resolve({owner:42});await first.promise;
  const next=await state.read('order',async({scope})=>({owner:scope}));
  assert.deepEqual(next,{status:'ready',value:{owner:'100:77'}});
  state.setScope('100:77');assert.equal(state.snapshot('order'),next,'same-account token renewal preserves read state');
});

test('clear and cancel settle ignored-abort reads without affecting other keys',async()=>{
  const state=new ScopedAsyncState();state.setScope('100:42');const a=deferred(),b=deferred();
  const first=state.read('a',()=>a.promise),second=state.read('b',()=>b.promise);
  state.cancel('a');assert.deepEqual(await first,{status:'stale'});
  b.resolve({id:'b'});assert.equal((await second).status,'ready');
  const never=state.read('a',()=>new Promise(()=>{}));state.clear();
  assert.deepEqual(await never,{status:'stale'});assert.equal(state.scope,'100:42');
  assert.deepEqual(state.snapshot('b'),{status:'idle'});
  a.resolve({id:'late'});await a.promise;assert.deepEqual(state.snapshot('a'),{status:'idle'});
});

test('logout and repeated dispose erase cache and prevent new account work',async()=>{
  const state=new ScopedAsyncState();state.setScope('100:42');await state.read('profile',async()=>({private:true}));
  state.setScope(null);assert.deepEqual(state.snapshot('profile'),{status:'idle'});
  await assert.rejects(state.read('profile',async()=>({})),AuthenticationRequired);
  state.setScope('100:77');const pending=state.read('order',()=>new Promise(()=>{}));
  state.dispose();state.dispose();assert.deepEqual(await pending,{status:'stale'});assert.equal(state.scope,null);
  assert.deepEqual(state.snapshot('order'),{status:'idle'});
  assert.throws(()=>state.setScope('100:42'),ValidationFailure);
  await assert.rejects(state.read('order',async()=>({})),ValidationFailure);
});

test('snapshots detach and deep freeze nested DTOs without prototype mutation',async()=>{
  const state=new ScopedAsyncState();state.setScope('100:42');
  const original=JSON.parse('{"items":[{"id":"kept"}],"__proto__":{"polluted":true}}');
  const snapshot=await state.read('order',async()=>original);
  original.items[0].id='changed';original.items.push({id:'extra'});
  assert.deepEqual(snapshot.value.items,[{id:'kept'}]);assert.notEqual(snapshot.value,original);
  assert.equal({}.polluted,undefined);assert.equal(Object.getPrototypeOf(snapshot.value),Object.prototype);
  assert.throws(()=>{snapshot.status='idle';},TypeError);
  assert.throws(()=>{snapshot.value.items[0].id='mutated';},TypeError);
  assert.throws(()=>snapshot.value.items.push({id:'mutated'}),TypeError);
  assert.equal(state.snapshot('order'),snapshot);
});

test('unsafe DTO classes accessors cycles and excessive nesting fail without exposing data',async()=>{
  const state=new ScopedAsyncState();state.setScope('100:42');let reads=0;
  const accessor={get secret(){reads++;return 'PRIVATE_TOKEN';}};
  const cyclic={};cyclic.self=cyclic;
  let deep={};for(let index=0;index<66;index++)deep={child:deep};
  const values=[accessor,cyclic,deep,new Map([['token','PRIVATE_TOKEN']]),{bad:undefined},{bad:NaN},[,,],Array.from({length:10000},()=>0)];
  for(const [index,value] of values.entries()){
    const result=await state.read('data',async()=>value);
    assert.equal(result.status,'failed',`partition ${index}`);
    assert.equal(JSON.stringify(result).includes('PRIVATE_TOKEN'),false);
    assert.equal(result.error.code,'validation-failed');
  }
  assert.equal(reads,0,'cache rejects accessors without invoking them');
});

test('failed reads publish safe reports and a subsequent read can recover',async()=>{
  const state=new ScopedAsyncState();state.setScope('100:42');
  const result=await state.read('data',()=>{throw new Error('PRIVATE_BEARER');});
  assert.equal(result.status,'failed');assert.equal(result.error.outcome,'read-failed');
  assert.equal(JSON.stringify(state.snapshot('data')).includes('PRIVATE_BEARER'),false);
  assert.throws(()=>{result.error.message='PRIVATE_BEARER';},TypeError);
  assert.deepEqual(await state.read('data',async()=>({ok:true})),{status:'ready',value:{ok:true}});
});

test('bounded cache evicts and aborts oldest work while preserving independent newer keys',async()=>{
  const options={maxEntries:2};const state=new ScopedAsyncState(options);options.maxEntries=512;state.setScope('100:42');
  let signal;const first=state.read('old',context=>{signal=context.signal;return new Promise(()=>{});});
  await state.read('middle',async()=>({id:'middle'}));await state.read('new',async()=>({id:'new'}));
  assert.equal(signal.aborted,true);assert.deepEqual(await first,{status:'stale'});
  assert.deepEqual(state.snapshot('old'),{status:'idle'});
  assert.equal(state.snapshot('middle').status,'ready');assert.equal(state.snapshot('new').status,'ready');
});

test('configuration keys and scope are validated before starting a loader',async()=>{
  for(const value of [0,-1,513,NaN,1.5,true])assert.throws(()=>new ScopedAsyncState({maxEntries:value}),ValidationFailure);
  const state=new ScopedAsyncState();let calls=0;
  for(const value of ['',undefined,7,'x'.repeat(257)])assert.throws(()=>state.setScope(value),ValidationFailure);
  state.setScope('100:42');
  for(const value of ['',null,'x'.repeat(257)])await assert.rejects(state.read(value,async()=>{calls++;return {};}),ValidationFailure);
  assert.equal(calls,0);
});
